"""Connettore che crea bozze ``sale.order`` a partire da un VOF."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ventureorder.connectors.odoo.client import OdooClient
from ventureorder.connectors.odoo.exceptions import (
    CustomerNotFoundError,
    DuplicatePurchaseOrderError,
    OdooAuthError,
    OdooDataError,
    OdooTransientError,
    ProductNotFoundError,
)
from ventureorder.connectors.odoo.mapping import (
    build_line_vals,
    build_order_vals,
    client_order_ref_from_header,
    origin_from_order_id,
)

SleepFn = Callable[[float], None]

_ORDER_READ_FIELDS = [
    "id",
    "name",
    "state",
    "origin",
    "client_order_ref",
    "partner_id",
    "amount_untaxed",
    "order_line",
]


@dataclass(frozen=True)
class PostedSaleOrder:
    """Esito della pubblicazione di una bozza in Odoo."""

    odoo_id: int
    name: str
    state: str
    origin: str
    client_order_ref: str
    partner_id: int
    amount_untaxed: float | None
    reused: bool
    line_ids: tuple[int, ...]

    def to_erp_ref(self, *, posted_at: str | None = None) -> dict[str, Any]:
        """Blocco ``erp_ref`` da attaccare al VOF."""
        when = posted_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "system": "ODOO",
            "external_id": str(self.odoo_id),
            "name": self.name,
            "posted_at": when,
        }


class OdooSaleOrderConnector:
    """Crea una bozza ``sale.order`` da un ordine canonico (VOF).

    Idempotenza e duplicati:
    1. cerca ``origin = VO:<order_id>`` e, se presente, restituisce l'esistente
       (unica riconciliazione: ``reused=True``);
    2. cerca ``client_order_ref`` + cliente (non cancellati) come controllo
       DUP-01: se trovato con origin diverso solleva
       :class:`DuplicatePurchaseOrderError` (non è un riuso);
    3. in caso di timeout dopo la create, riconcilia di nuovo il passo 1
       prima di ritentare (nessun duplicato se Odoo ha già committato).

    Non chiama mai ``action_confirm``: l'ordine resta in bozza.
    """

    def __init__(
        self,
        client: OdooClient,
        *,
        use_po_price: bool = True,
        max_attempts: int = 5,
        backoff_seconds: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0),
        jitter: bool = True,
        sleep: SleepFn = time.sleep,
    ) -> None:
        self.client = client
        self.use_po_price = use_po_price
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds or (2.0,)
        self.jitter = jitter
        self.sleep = sleep

    def post_draft(self, order: Mapping[str, Any]) -> PostedSaleOrder:
        """Crea (o riconcilia) la bozza ``sale.order`` per il VOF dato."""
        self._validate_order(order)
        partner = self._resolve_partner(order)
        lines = self._resolve_lines(order)
        origin = origin_from_order_id(str(order["order_id"]))
        po_ref = client_order_ref_from_header(order.get("header") or {})

        existing = self._find_by_origin(origin)
        if existing:
            return self._to_posted(existing, reused=True)
        duplicate = self._find_by_po(partner, po_ref)
        if duplicate:
            self._raise_duplicate_po(duplicate, po_ref)

        vals = build_order_vals(
            order,
            partner_id=int(partner["id"]),
            invoice_partner_id=self._optional_partner(order.get("bill_to")),
            shipping_partner_id=self._optional_partner(order.get("ship_to")),
            order_lines=lines,
        )
        return self._create_with_retry(vals, origin)

    def _validate_order(self, order: Mapping[str, Any]) -> None:
        if not order.get("order_id"):
            raise OdooDataError("VOF senza order_id: impossibile garantire l'idempotenza")
        header = order.get("header") or {}
        if not header.get("po_number"):
            raise OdooDataError("VOF senza header.po_number")
        lines = order.get("lines") or []
        if not lines:
            raise OdooDataError("VOF senza righe: impossibile creare sale.order")

    def _resolve_partner(self, order: Mapping[str, Any]) -> dict[str, Any]:
        buyer = order.get("buyer") or {}
        resolved = buyer.get("resolved") or {}
        partner_id = resolved.get("erp_partner_id")
        partner_ref = resolved.get("erp_partner_ref")
        if partner_id:
            found = self._read_one(
                "res.partner",
                [("id", "=", int(partner_id))],
                ["id", "name", "ref", "commercial_partner_id", "parent_id"],
            )
            if found:
                return found
            raise CustomerNotFoundError(f"Cliente Odoo id={partner_id} non esiste.")
        if partner_ref:
            found = self._read_one(
                "res.partner",
                [("ref", "=", str(partner_ref))],
                ["id", "name", "ref", "commercial_partner_id", "parent_id"],
            )
            if found:
                return found
            raise CustomerNotFoundError(f"Cliente con ref={partner_ref!r} non esiste in Odoo.")
        name = buyer.get("name") or "sconosciuto"
        raise CustomerNotFoundError(
            f"Cliente non risolto ({name!r}): mancano buyer.resolved.erp_partner_id "
            "e buyer.resolved.erp_partner_ref."
        )

    def _optional_partner(self, party: Mapping[str, Any] | None) -> int | None:
        if not party:
            return None
        resolved = party.get("resolved") or {}
        partner_id = resolved.get("erp_partner_id")
        if not partner_id:
            return None
        found = self._read_one("res.partner", [("id", "=", int(partner_id))], ["id"])
        return int(found["id"]) if found else None

    def _resolve_lines(self, order: Mapping[str, Any]) -> list[dict[str, Any]]:
        built: list[dict[str, Any]] = []
        for line in order.get("lines") or []:
            product = self._resolve_product(line)
            uom_id = self._resolve_uom_id(line, product)
            built.append(
                build_line_vals(
                    line,
                    product_id=int(product["id"]),
                    uom_id=uom_id,
                    major_version=self.client.major_version,
                    use_po_price=self.use_po_price,
                )
            )
        return built

    def _resolve_product(self, line: Mapping[str, Any]) -> dict[str, Any]:
        resolution = line.get("resolution") or {}
        line_no = line.get("line_no") or "?"
        product_id = resolution.get("erp_product_id")
        sku = resolution.get("sku") or line.get("seller_item_code")
        fields = ["id", "name", "default_code", "uom_id"]
        if product_id:
            found = self._read_one("product.product", [("id", "=", int(product_id))], fields)
            if found:
                return found
            raise ProductNotFoundError(f"Prodotto Odoo id={product_id} (riga {line_no}) non esiste.")
        if sku:
            found = self._read_one("product.product", [("default_code", "=", str(sku))], fields)
            if found:
                return found
            raise ProductNotFoundError(f"Prodotto SKU={sku!r} (riga {line_no}) non esiste in Odoo.")
        raise ProductNotFoundError(
            f"Riga {line_no}: prodotto non risolto (mancano resolution.erp_product_id e sku)."
        )

    def _resolve_uom_id(self, line: Mapping[str, Any], product: Mapping[str, Any]) -> int | None:
        resolution = line.get("resolution") or {}
        if resolution.get("erp_uom_id"):
            return int(resolution["erp_uom_id"])
        uom = product.get("uom_id")
        if isinstance(uom, list | tuple) and uom:
            return int(uom[0])
        if isinstance(uom, int):
            return uom
        return None

    def _find_by_origin(self, origin: str) -> dict[str, Any] | None:
        return self._read_one(
            "sale.order",
            [("origin", "=", origin)],
            _ORDER_READ_FIELDS,
        )

    def _find_by_po(self, partner: Mapping[str, Any], po_ref: str) -> dict[str, Any] | None:
        commercial = partner.get("commercial_partner_id") or partner.get("id")
        if isinstance(commercial, list | tuple):
            commercial = commercial[0]
        return self._read_one(
            "sale.order",
            [
                ("partner_id", "child_of", commercial),
                ("client_order_ref", "=", po_ref),
                ("state", "!=", "cancel"),
            ],
            _ORDER_READ_FIELDS,
        )

    def _raise_duplicate_po(self, existing: Mapping[str, Any], po_ref: str) -> None:
        odoo_id = int(existing["id"])
        name = str(existing.get("name") or "")
        existing_origin = str(existing.get("origin") or "")
        raise DuplicatePurchaseOrderError(
            f"DUP-01: esiste già sale.order {name or odoo_id} "
            f"(id={odoo_id}, origin={existing_origin!r}) "
            f"con lo stesso PO {po_ref!r} e cliente",
            odoo_id=odoo_id,
            name=name,
            origin=existing_origin,
            client_order_ref=po_ref,
        )

    def _create_with_retry(self, vals: dict[str, Any], origin: str) -> PostedSaleOrder:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                if attempt > 0:
                    reconciled = self._find_by_origin(origin)
                    if reconciled:
                        return self._to_posted(reconciled, reused=True)
                new_id = self.client.create("sale.order", vals)
                record = self._read_created(new_id, origin)
                return self._to_posted(record, reused=False)
            except OdooAuthError:
                raise
            except OdooDataError:
                raise
            except OdooTransientError as exc:
                last_error = exc
                try:
                    reconciled = self._find_by_origin(origin)
                except OdooTransientError as reconcile_exc:
                    last_error = reconcile_exc
                    reconciled = None
                if reconciled:
                    return self._to_posted(reconciled, reused=True)
                if attempt >= self.max_attempts - 1:
                    break
                self.sleep(self._backoff(attempt))
        raise OdooTransientError(
            f"Impossibile creare la bozza sale.order dopo {self.max_attempts} tentativi: {last_error}"
        )

    def _read_created(self, new_id: int, origin: str) -> dict[str, Any]:
        rows = self.client.read("sale.order", [new_id], _ORDER_READ_FIELDS)
        if rows:
            return rows[0]
        found = self._find_by_origin(origin)
        if found:
            return found
        raise OdooDataError(f"sale.order id={new_id} creato ma non leggibile")

    def _read_one(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
    ) -> dict[str, Any] | None:
        rows = self.client.search_read(model, domain, fields, limit=1)
        return rows[0] if rows else None

    def _to_posted(self, record: Mapping[str, Any], *, reused: bool) -> PostedSaleOrder:
        partner = record.get("partner_id")
        if isinstance(partner, list | tuple):
            partner_id = int(partner[0])
        else:
            partner_id = int(partner or 0)
        line_ids = record.get("order_line") or ()
        amount = record.get("amount_untaxed")
        return PostedSaleOrder(
            odoo_id=int(record["id"]),
            name=str(record.get("name") or ""),
            state=str(record.get("state") or "draft"),
            origin=str(record.get("origin") or ""),
            client_order_ref=str(record.get("client_order_ref") or ""),
            partner_id=partner_id,
            amount_untaxed=float(amount) if amount is not None else None,
            reused=reused,
            line_ids=tuple(int(x) for x in line_ids),
        )

    def _backoff(self, attempt: int) -> float:
        index = min(attempt, len(self.backoff_seconds) - 1)
        delay = float(self.backoff_seconds[index])
        if self.jitter and delay > 0:
            return delay * (0.5 + random.random() * 0.5)
        return delay
