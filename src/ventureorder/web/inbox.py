"""Inbox in memoria: ordini sintetici, stato UI, FakeOdooClient."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ventureorder.connectors.odoo import (
    DuplicatePurchaseOrderError,
    FakeOdooClient,
    OdooConnectorError,
    OdooSaleOrderConnector,
)
from ventureorder.rules import (
    DatagenReferenceDataProvider,
    DecisionRoute,
    ValidationEngine,
    ValidationResult,
)
from ventureorder.web.pipeline import (
    DEMO_STEMS,
    apply_match_if_available,
    build_engine,
    build_reference_provider,
    clone_vof,
    historical_from_vof,
    load_extracted_vof,
)

STATUS_APPROVED = "APPROVATO"
STATUS_REJECTED = "RIFIUTATO"


def _vof_buyer_resolved(vof: dict[str, Any]) -> bool:
    resolved = (vof.get("buyer") or {}).get("resolved") or {}
    return bool(resolved.get("erp_partner_id") or resolved.get("erp_partner_ref"))


@dataclass
class InboxOrder:
    """Ordine in console, con VOF, esito regole e stato UI."""

    id: str
    vof: dict[str, Any]
    result: ValidationResult
    ui_status: str
    draft_name: str | None = None
    draft_id: int | None = None
    error: str | None = None
    is_duplicate: bool = False

    @property
    def customer_name(self) -> str:
        buyer = self.vof.get("buyer") or {}
        name = buyer.get("name")
        return str(name) if name else "n/d"

    @property
    def customer_resolved(self) -> bool:
        resolved = (self.vof.get("buyer") or {}).get("resolved") or {}
        return bool(resolved.get("erp_partner_id") or resolved.get("erp_partner_ref"))

    @property
    def po_number(self) -> str:
        header = self.vof.get("header") or {}
        value = header.get("po_number")
        return str(value) if value else "n/d"

    @property
    def po_date(self) -> str:
        header = self.vof.get("header") or {}
        value = header.get("po_date")
        return str(value) if value else "n/d"

    @property
    def line_count(self) -> int:
        lines = self.vof.get("lines") or []
        return len(lines) if isinstance(lines, list) else 0

    @property
    def total(self) -> float | None:
        totals = self.vof.get("totals") or {}
        declared = totals.get("total_amount_declared")
        if declared is not None:
            return float(declared)
        amount = 0.0
        has_amount = False
        for line in self.vof.get("lines") or []:
            value = line.get("line_amount")
            if value is None:
                qty = line.get("quantity")
                price = line.get("unit_price")
                if qty is None or price is None:
                    continue
                value = float(qty) * float(price)
            amount += float(value or 0)
            has_amount = True
        return round(amount, 2) if has_amount else None


@dataclass
class OrderInbox:
    """Archivio volatile della console (prototipo: una sessione di processo)."""

    orders: dict[str, InboxOrder] = field(default_factory=dict)
    odoo: FakeOdooClient = field(default_factory=FakeOdooClient)
    connector: OdooSaleOrderConnector | None = None

    def __post_init__(self) -> None:
        if self.connector is None:
            self.connector = OdooSaleOrderConnector(
                self.odoo,
                max_attempts=2,
                backoff_seconds=(0.0, 0.0),
                jitter=False,
                sleep=lambda _seconds: None,
            )

    @classmethod
    def for_demo(cls) -> OrderInbox:
        """Carica ~10 ordini sintetici via ingest+extract; uno è duplicato."""
        provider = build_reference_provider()
        engine = build_engine(provider)

        odoo = FakeOdooClient(major_version=19)
        seed_fake_odoo(odoo, provider)
        inbox = cls(odoo=odoo)

        loaded: list[dict[str, Any]] = []
        for stem in DEMO_STEMS:
            vof = load_extracted_vof(stem, provider)
            if vof is not None:
                loaded.append(vof)

        # La console deve poter mostrare un ordine non risolto: non si inventa la bozza.
        if loaded and all(_vof_buyer_resolved(item) for item in loaded):
            buyer = loaded[-1].setdefault("buyer", {})
            buyer.pop("resolved", None)

        for vof in loaded:
            inbox._add_validated(vof, engine)

        if loaded:
            original = loaded[0]
            provider.add_order(historical_from_vof(original))
            duplicate = clone_vof(
                original,
                order_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "vo-demo-duplicate")),
            )
            duplicate = apply_match_if_available(duplicate, provider)
            dup_order = inbox._add_validated(duplicate, engine)
            dup_order.is_duplicate = True
        return inbox

    def _add_validated(self, vof: dict[str, Any], engine: ValidationEngine) -> InboxOrder:
        result = engine.validate(vof)
        order_id = str(vof.get("order_id") or uuid.uuid4())
        vof["order_id"] = order_id
        vof.update(result.to_vof_fields())
        is_dup = any(issue.rule_id in {"DUP-01", "DUP-02"} for issue in result.issues)
        item = InboxOrder(
            id=order_id,
            vof=vof,
            result=result,
            ui_status=result.decision.value,
            is_duplicate=is_dup,
        )
        self.orders[order_id] = item
        return item

    def list_orders(self) -> list[InboxOrder]:
        """Ordini in ordine di inserimento."""
        return list(self.orders.values())

    def get(self, order_id: str) -> InboxOrder | None:
        return self.orders.get(order_id)

    def approve(self, order_id: str) -> InboxOrder:
        """Crea la bozza ``sale.order`` su FakeOdooClient. I duplicati no."""
        order = self._require(order_id)
        if order.ui_status in {STATUS_APPROVED, STATUS_REJECTED}:
            return order
        if order.result.decision == DecisionRoute.REJECT or order.is_duplicate:
            order.error = "Duplicato o REJECT: la bozza sale.order non viene creata."
            return order
        assert self.connector is not None
        try:
            posted = self.connector.post_draft(order.vof)
        except DuplicatePurchaseOrderError as exc:
            order.error = str(exc)
            return order
        except OdooConnectorError as exc:
            order.error = str(exc)
            return order
        order.ui_status = STATUS_APPROVED
        order.draft_name = posted.name
        order.draft_id = posted.odoo_id
        order.error = None
        order.vof["status"] = "POSTED"
        return order

    def reject(self, order_id: str) -> InboxOrder:
        """Segna l'ordine come rifiutato, senza toccare Odoo."""
        order = self._require(order_id)
        if order.ui_status == STATUS_APPROVED:
            order.error = "Ordine già approvato: impossibile rifiutarlo."
            return order
        order.ui_status = STATUS_REJECTED
        order.error = None
        order.vof["status"] = "REJECTED"
        return order

    def _require(self, order_id: str) -> InboxOrder:
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(order_id)
        return order


def seed_fake_odoo(client: FakeOdooClient, provider: DatagenReferenceDataProvider) -> None:
    """Popola partner e prodotti del client finto dall'anagrafica datagen."""
    for customer in provider.iter_customers():
        client.seed_partner(
            id=customer.erp_partner_id,
            name=customer.name,
            ref=customer.erp_partner_ref,
            commercial_partner_id=customer.erp_partner_id,
        )
        for dep_id in customer.delivery_partner_ids:
            client.seed_partner(
                id=dep_id,
                name=f"{customer.name} (ship)",
                parent_id=customer.erp_partner_id,
                commercial_partner_id=customer.erp_partner_id,
            )
    for product in provider.iter_products():
        client.seed_product(
            id=product.erp_product_id,
            name=product.name,
            default_code=product.sku,
            uom_id=1,
        )
