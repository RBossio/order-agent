"""Provider di anagrafica per le regole: protocollo, mock e DatagenLoader."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ventureorder.rules.access import (
    DATAGEN_VALID_UOMS,
    INDIVISIBLE_UOMS,
    normalize_address,
    normalize_uom,
    parse_date,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class CustomerRecord:
    """Snapshot cliente (anagrafica Odoo / dati sintetici)."""

    erp_partner_id: int
    erp_partner_ref: str
    name: str
    email_domain: str
    currency: str = "USD"
    payment_terms: str = "Net 30"
    sale_warn: str = "no-message"
    ship_to: list[dict[str, Any]] = field(default_factory=list)
    peppol_endpoint: str | None = None
    gln: str | None = None
    allowlisted: bool = False
    approved_orders_without_corrections: int = 0
    delivery_partner_ids: list[int] = field(default_factory=list)


@dataclass
class ProductRecord:
    """Snapshot prodotto di catalogo."""

    sku: str
    erp_product_id: int
    name: str
    sale_uom: str
    list_price: float
    gtin: str | None = None
    manufacturer_part_number: str | None = None
    pack: dict[str, Any] | None = None
    conversions: list[dict[str, Any]] = field(default_factory=list)
    active: bool = True
    sale_ok: bool = True
    sale_multiple: float | None = None
    min_order_qty: float | None = None


@dataclass
class XrefRecord:
    """Cross-reference codice cliente → SKU (TRUSTED / CANDIDATE)."""

    customer_ref: str
    customer_item_code: str
    sku: str
    erp_product_id: int | None = None
    uom: str | None = None
    status: str = "TRUSTED"


@dataclass
class HistoricalOrder:
    """Ordine già elaborato, per DUP-01/02/03."""

    order_id: str
    customer_ref: str
    po_number: str
    po_revision: int = 0
    po_date: str | None = None
    status: str = "POSTED"
    sha256: str | None = None
    message_id: str | None = None
    lines: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class ReferenceDataProvider(Protocol):
    """Anagrafica sostituibile (Odoo in produzione, mock/sintetico nei test)."""

    def get_customer_by_partner_id(self, erp_partner_id: int) -> CustomerRecord | None: ...

    def get_customer_by_ref(self, erp_partner_ref: str) -> CustomerRecord | None: ...

    def get_product_by_sku(self, sku: str) -> ProductRecord | None: ...

    def get_product_by_id(self, erp_product_id: int) -> ProductRecord | None: ...

    def get_product_by_gtin(self, gtin: str) -> ProductRecord | None: ...

    def get_product_by_mpn(self, mpn: str) -> ProductRecord | None: ...

    def get_xref(self, customer_ref: str, buyer_item_code: str) -> XrefRecord | None: ...

    def is_valid_uom(self, uom: str) -> bool: ...

    def get_uom_conversion(
        self, from_uom: str, to_uom: str, sku: str | None = None
    ) -> float | None: ...

    def get_existing_orders(
        self, customer_ref: str, po_number: str, po_revision: int
    ) -> list[HistoricalOrder]: ...

    def get_order_by_sha256(self, sha256: str) -> HistoricalOrder | None: ...

    def get_order_by_message_id(self, message_id: str) -> HistoricalOrder | None: ...

    def get_similar_orders(
        self, customer_ref: str, po_date: date, po_number: str, window_days: int
    ) -> list[HistoricalOrder]: ...

    def get_qty_p99(self, customer_ref: str, sku: str) -> float | None: ...

    def get_charge_product(self, charge_type: str) -> str | None: ...

    def map_uom_for_export(self, uom: str, export_target: str) -> str | None: ...

    def get_item_price(self, sku: str, customer_ref: str | None = None) -> float | None: ...


class InMemoryReferenceDataProvider:
    """Implementazione in memoria usata da mock e provider sintetico."""

    def __init__(self) -> None:
        self._customers_by_id: dict[int, CustomerRecord] = {}
        self._customers_by_ref: dict[str, CustomerRecord] = {}
        self._products_by_sku: dict[str, ProductRecord] = {}
        self._products_by_id: dict[int, ProductRecord] = {}
        self._products_by_gtin: dict[str, ProductRecord] = {}
        self._products_by_mpn: dict[str, ProductRecord] = {}
        self._xrefs: dict[tuple[str, str], XrefRecord] = {}
        self._orders: list[HistoricalOrder] = []
        self._qty_p99: dict[tuple[str, str], float] = {}
        self._charge_products: dict[str, str] = {}
        self._valid_uoms: set[str] = set(INDIVISIBLE_UOMS) | {
            "GLL",
            "LTR",
            "KGM",
            "LBR",
        }
        self._uom_export: dict[str, dict[str, str]] = {}
        self._extra_conversions: dict[tuple[str, str, str | None], float] = {}

    def add_customer(self, customer: CustomerRecord) -> None:
        """Registra un cliente per id ERP e ref."""
        self._customers_by_id[customer.erp_partner_id] = customer
        self._customers_by_ref[customer.erp_partner_ref] = customer

    def add_product(self, product: ProductRecord) -> None:
        """Registra un prodotto per SKU, id, GTIN e MPN."""
        self._products_by_sku[product.sku] = product
        self._products_by_id[product.erp_product_id] = product
        if product.gtin:
            self._products_by_gtin[str(product.gtin)] = product
        if product.manufacturer_part_number:
            self._products_by_mpn[product.manufacturer_part_number] = product
        if product.sale_uom:
            self._register_uom(product.sale_uom)
        for conv in product.conversions:
            self._register_uom(conv.get("from_uom"))
            self._register_uom(conv.get("to_uom"))

    def add_xref(self, xref: XrefRecord) -> None:
        """Registra un cross-reference cliente → SKU."""
        key = (xref.customer_ref, xref.customer_item_code)
        self._xrefs[key] = xref

    def add_order(self, order: HistoricalOrder) -> None:
        """Registra un ordine storico per le regole DUP."""
        self._orders.append(order)

    def set_qty_p99(self, customer_ref: str, sku: str, value: float) -> None:
        """Imposta il 99° percentile storico di quantità."""
        self._qty_p99[(customer_ref, sku)] = value

    def set_charge_product(self, charge_type: str, sku: str) -> None:
        """Mappa un tipo di spesa (FREIGHT, …) a uno SKU servizio."""
        self._charge_products[charge_type] = sku

    def set_valid_uoms(self, uoms: set[str]) -> None:
        """Sostituisce l'insieme di UoM riconosciute (codice grezzo e Rec. 20)."""
        accepted: set[str] = set()
        for uom in uoms:
            raw = str(uom).strip().upper()
            if raw:
                accepted.add(raw)
            normalized = normalize_uom(uom)
            if normalized:
                accepted.add(normalized)
        self._valid_uoms = accepted

    def add_uom_export_map(self, uom: str, target: str, mapped: str) -> None:
        """Aggiunge la corrispondenza UoM → codice del formato di export."""
        self._uom_export.setdefault(uom.upper(), {})[target.upper()] = mapped

    def add_conversion(
        self, from_uom: str, to_uom: str, factor: float, sku: str | None = None
    ) -> None:
        """Aggiunge una conversione UoM (opzionalmente per SKU)."""
        src = normalize_uom(from_uom) or from_uom.upper()
        dst = normalize_uom(to_uom) or to_uom.upper()
        self._extra_conversions[(src, dst, sku)] = factor
        self._register_uom(from_uom)
        self._register_uom(to_uom)

    def _register_uom(self, uom: Any) -> None:
        """Accetta un codice UoM (anche alias RL/CA) tra le unità valide."""
        if not uom:
            return
        raw = str(uom).strip().upper()
        if not raw:
            return
        self._valid_uoms.add(raw)
        normalized = normalize_uom(raw)
        if normalized:
            self._valid_uoms.add(normalized)

    def get_customer_by_partner_id(self, erp_partner_id: int) -> CustomerRecord | None:
        return self._customers_by_id.get(erp_partner_id)

    def get_customer_by_ref(self, erp_partner_ref: str) -> CustomerRecord | None:
        return self._customers_by_ref.get(erp_partner_ref)

    def get_product_by_sku(self, sku: str) -> ProductRecord | None:
        return self._products_by_sku.get(sku)

    def get_product_by_id(self, erp_product_id: int) -> ProductRecord | None:
        return self._products_by_id.get(erp_product_id)

    def get_product_by_gtin(self, gtin: str) -> ProductRecord | None:
        return self._products_by_gtin.get(str(gtin))

    def get_product_by_mpn(self, mpn: str) -> ProductRecord | None:
        return self._products_by_mpn.get(mpn)

    def get_xref(self, customer_ref: str, buyer_item_code: str) -> XrefRecord | None:
        return self._xrefs.get((customer_ref, buyer_item_code))

    def is_valid_uom(self, uom: str) -> bool:
        if not uom:
            return False
        raw = str(uom).strip().upper()
        if raw in self._valid_uoms:
            return True
        normalized = normalize_uom(uom)
        if not normalized:
            return False
        return normalized in self._valid_uoms

    def get_uom_conversion(
        self, from_uom: str, to_uom: str, sku: str | None = None
    ) -> float | None:
        src = normalize_uom(from_uom)
        dst = normalize_uom(to_uom)
        if not src or not dst:
            return None
        if src == dst:
            return 1.0
        for key in ((src, dst, sku), (src, dst, None)):
            if key in self._extra_conversions:
                return self._extra_conversions[key]
        product = self._products_by_sku.get(sku) if sku else None
        if product:
            for conv in product.conversions:
                c_from = normalize_uom(str(conv.get("from_uom", "")))
                c_to = normalize_uom(str(conv.get("to_uom", "")))
                factor = conv.get("factor")
                if c_from == src and c_to == dst and factor:
                    return float(factor)
                if c_from == dst and c_to == src and factor:
                    return 1.0 / float(factor)
        return None

    def get_existing_orders(
        self, customer_ref: str, po_number: str, po_revision: int
    ) -> list[HistoricalOrder]:
        return [
            order
            for order in self._orders
            if order.customer_ref == customer_ref
            and order.po_number == po_number
            and order.po_revision == po_revision
            and order.status in {"POSTED", "EXPORTED"}
        ]

    def get_order_by_sha256(self, sha256: str) -> HistoricalOrder | None:
        for order in self._orders:
            if order.sha256 == sha256:
                return order
        return None

    def get_order_by_message_id(self, message_id: str) -> HistoricalOrder | None:
        for order in self._orders:
            if order.message_id == message_id:
                return order
        return None

    def get_similar_orders(
        self, customer_ref: str, po_date: date, po_number: str, window_days: int
    ) -> list[HistoricalOrder]:
        results: list[HistoricalOrder] = []
        for order in self._orders:
            if order.customer_ref != customer_ref or order.po_number == po_number:
                continue
            other_date = parse_date(order.po_date)
            if other_date is None:
                continue
            if abs((other_date - po_date).days) <= window_days:
                results.append(order)
        return results

    def get_qty_p99(self, customer_ref: str, sku: str) -> float | None:
        return self._qty_p99.get((customer_ref, sku))

    def get_charge_product(self, charge_type: str) -> str | None:
        return self._charge_products.get(charge_type)

    def map_uom_for_export(self, uom: str, export_target: str) -> str | None:
        normalized = normalize_uom(uom) or (uom.upper() if uom else None)
        if not normalized:
            return None
        mapped = self._uom_export.get(normalized, {}).get(export_target.upper())
        if mapped:
            return mapped
        # Rec. 20: il codice normalizzato è già il codice Peppol/EDIFACT più comune.
        if export_target.upper() in {"PEPPOL", "EDIFACT"} and self.is_valid_uom(normalized):
            return normalized
        if export_target.upper() == "X12" and self.is_valid_uom(normalized):
            x12_aliases = {
                "DZN": "DZ",
                "CS": "CA",
                "RO": "RL",
                "GLL": "GA",
                "LTR": "LT",
                "KGM": "KG",
                "LBR": "LB",
            }
            return x12_aliases.get(normalized, normalized)
        return None

    def get_item_price(self, sku: str, customer_ref: str | None = None) -> float | None:
        product = self._products_by_sku.get(sku)
        if product is None:
            return None
        return product.list_price


class MockReferenceDataProvider(InMemoryReferenceDataProvider):
    """Provider configurabile per i test: stesse API, dati iniettati a mano."""


class DatagenReferenceDataProvider(InMemoryReferenceDataProvider):
    """Provider di anagrafica alimentato da ``datagen/master`` via ``DatagenLoader``.

    È il provider predefinito per l'esecuzione del motore su dati sintetici
    (vedi ``ValidationEngine.for_synthetic``).
    """

    @classmethod
    def from_loader(
        cls,
        loader: Any,
        uom_path: Path | None = None,
        allowlisted_refs: set[str] | None = None,
    ) -> DatagenReferenceDataProvider:
        """Costruisce il provider da un ``MasterDataLoader`` (DatagenLoader)."""
        provider = cls()
        catalog = loader.load_catalog()
        customers = loader.load_customers(catalog)
        provider._ingest_catalog(catalog)
        provider._ingest_customers(customers, allowlisted_refs=allowlisted_refs or set())
        if uom_path and uom_path.exists():
            provider._ingest_uom_definitions(uom_path)
        for code in DATAGEN_VALID_UOMS:
            provider._register_uom(code)
        return provider

    @classmethod
    def from_datagen(
        cls,
        datagen_path: Path | None = None,
        allowlisted_refs: set[str] | None = None,
    ) -> DatagenReferenceDataProvider:
        """Carica ``datagen/master/`` tramite ``DatagenLoader``."""
        import importlib

        path = datagen_path or _default_datagen_path()
        # importlib evita che mypy analizzi synthetic/ (fuori da src/ventureorder).
        datagen_mod = importlib.import_module("synthetic.loaders.datagen")
        loader = datagen_mod.DatagenLoader(path)
        return cls.from_loader(
            loader,
            uom_path=path / "uom_definitions.json",
            allowlisted_refs=allowlisted_refs,
        )

    def _ingest_catalog(self, catalog: list[dict[str, Any]]) -> None:
        for item in catalog:
            pack = item.get("pack")
            conversions = [
                {
                    "from_uom": conv.get("from_uom"),
                    "to_uom": conv.get("to_uom"),
                    "factor": conv.get("factor"),
                }
                for conv in (item.get("conversions") or [])
                if conv.get("from_uom") and conv.get("to_uom") and conv.get("factor")
            ]
            # Fallback se il loader non espone conversions (catalogo embedded).
            if not conversions and pack and pack.get("inner_count") and pack.get("inner_uom"):
                conversions.append(
                    {
                        "from_uom": item.get("uom"),
                        "to_uom": pack.get("inner_uom"),
                        "factor": pack.get("inner_count"),
                    }
                )
            product = ProductRecord(
                sku=item["sku"],
                erp_product_id=int(item["erp_product_id"]),
                name=item.get("description") or item["sku"],
                sale_uom=item.get("uom") or "EA",
                list_price=float(item.get("price") or 0),
                gtin=item.get("gtin"),
                manufacturer_part_number=item.get("manufacturer_part_number"),
                pack=pack,
                conversions=conversions,
                active=True,
                sale_ok=True,
            )
            self.add_product(product)

    def _ingest_customers(
        self,
        customers: list[dict[str, Any]],
        allowlisted_refs: set[str],
    ) -> None:
        for raw in customers:
            ref = raw["customer_id"]
            style = raw.get("order_style") or {}
            ship_to = raw.get("ship_to") or []
            # Id fittizi per gli indirizzi di consegna, distinti dal partner principale.
            delivery_ids = [raw["erp_partner_id"] + i + 1 for i in range(len(ship_to))]
            customer = CustomerRecord(
                erp_partner_id=int(raw["erp_partner_id"]),
                erp_partner_ref=ref,
                name=raw.get("name") or ref,
                email_domain=str(raw.get("email_domain") or "example.com"),
                currency=str(style.get("currency") or "USD"),
                payment_terms="Net 30",
                sale_warn="no-message",
                ship_to=ship_to,
                allowlisted=ref in allowlisted_refs,
                approved_orders_without_corrections=25 if ref in allowlisted_refs else 0,
                delivery_partner_ids=delivery_ids,
            )
            self.add_customer(customer)
            for xref in raw.get("xref") or []:
                self.add_xref(
                    XrefRecord(
                        customer_ref=ref,
                        customer_item_code=xref["customer_code"],
                        sku=xref["sku"],
                        erp_product_id=xref.get("erp_product_id"),
                        uom=xref.get("uom"),
                        status=xref.get("status") or "TRUSTED",
                    )
                )

    def _ingest_uom_definitions(self, path: Path) -> None:
        import json

        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        codes: set[str] = set(self._valid_uoms)
        for group in payload.values():
            if not isinstance(group, dict):
                continue
            for uom in group.get("uoms") or []:
                code = uom.get("code")
                if code:
                    codes.add(str(code).upper())
                rec20 = uom.get("rec20")
                if rec20:
                    codes.add(str(rec20).upper())
                    if code:
                        self.add_uom_export_map(str(code), "PEPPOL", str(rec20))
                        self.add_uom_export_map(str(code), "EDIFACT", str(rec20))
                x12 = uom.get("x12")
                if x12 and code:
                    self.add_uom_export_map(str(code), "X12", str(x12))
        self.set_valid_uoms(codes)


# Alias conservato: il provider sintetico è quello Datagen.
SyntheticReferenceDataProvider = DatagenReferenceDataProvider


def _default_datagen_path() -> Path:
    """Percorso di ``datagen/master/`` rispetto al repo o al CWD."""
    candidates = [
        Path.cwd() / "datagen" / "master",
        REPO_ROOT / "datagen" / "master",
    ]
    for candidate in candidates:
        if (candidate / "products.json").exists():
            return candidate
    raise FileNotFoundError("datagen/master/ non trovato: generare i dati master sintetici.")


def customer_of(
    ctx_ref: ReferenceDataProvider | None, vof: dict[str, Any]
) -> CustomerRecord | None:
    """Risolve il cliente dal VOF tramite il provider."""
    if ctx_ref is None:
        return None
    resolved = (vof.get("buyer") or {}).get("resolved") or {}
    partner_id = resolved.get("erp_partner_id")
    partner_ref = resolved.get("erp_partner_ref")
    if partner_id is not None:
        found = ctx_ref.get_customer_by_partner_id(int(partner_id))
        if found:
            return found
    if partner_ref:
        return ctx_ref.get_customer_by_ref(str(partner_ref))
    return None


def product_of(ctx_ref: ReferenceDataProvider | None, line: dict[str, Any]) -> ProductRecord | None:
    """Risolve il prodotto di riga dal VOF tramite il provider."""
    if ctx_ref is None:
        return None
    resolution = line.get("resolution") or {}
    sku = resolution.get("sku")
    product_id = resolution.get("erp_product_id")
    if sku:
        found = ctx_ref.get_product_by_sku(str(sku))
        if found:
            return found
    if product_id is not None:
        return ctx_ref.get_product_by_id(int(product_id))
    return None


def addresses_match(ship: dict[str, Any], customer: CustomerRecord) -> bool:
    """True se ``ship_to`` coincide con un indirizzo di consegna del cliente."""
    resolved = ship.get("resolved") or {}
    partner_id = resolved.get("erp_partner_id")
    if partner_id is not None and int(partner_id) in customer.delivery_partner_ids:
        return True
    needle = normalize_address(ship.get("address"))
    if not needle:
        return False
    for entry in customer.ship_to:
        addr = entry.get("address") if isinstance(entry, dict) else None
        if needle == normalize_address(addr):
            return True
    return False


def line_overlap(current: list[dict[str, Any]], historical: HistoricalOrder) -> float:
    """Frazione di righe correnti con lo stesso SKU e quantità in ``historical``."""
    if not current:
        return 0.0
    hist_keys: list[tuple[str, float]] = []
    for line in historical.lines:
        sku = str(line.get("sku") or "")
        qty = float(line.get("quantity") or 0)
        hist_keys.append((sku, qty))
    matched = 0
    used: set[int] = set()
    for line in current:
        resolution = line.get("resolution") or {}
        sku = str(resolution.get("sku") or "")
        qty = float(line.get("quantity") or 0)
        for idx, (h_sku, h_qty) in enumerate(hist_keys):
            if idx in used:
                continue
            if sku and sku == h_sku and abs(qty - h_qty) < 1e-9:
                matched += 1
                used.add(idx)
                break
    return matched / len(current)
