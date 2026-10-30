"""Pipeline demo: ingest → estrazione deterministica → VOF → regole.

I documenti e il ground truth arrivano da ``synthetic/``; l'anagrafica da
``datagen/master``. L'estrazione usa ``MockBackend`` (nessun LLM a pagamento).
"""

from __future__ import annotations

import copy
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from ventureorder.rules import (
    CustomerRecord,
    DatagenReferenceDataProvider,
    HistoricalOrder,
    ProductRecord,
    ValidationEngine,
)
from ventureorder.rules.access import email_domain, normalize_uom, parse_date

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEMO_AS_OF = date(2026, 4, 2)
CLEAN_PO_DATE = "2026-03-28"
CLEAN_DELIVERY_DATE = "2026-04-10"
REVIEW_PO_DATE = "2026-12-01"

SYNTHETIC_DIR = REPO_ROOT / "synthetic"
GROUND_TRUTH_DIR = SYNTHETIC_DIR / "ground_truth"
DOCUMENTS_DIR = SYNTHETIC_DIR / "documents"

# Otto ordini sintetici con documento (xlsx/eml), più REVIEW e duplicato in inbox.
DEMO_STEMS = (
    "order_008_TIT-PO-01007",
    "order_009_NMC-01008",
    "order_013_NMC-01012",
    "order_014_TIT-PO-01013",
    "order_015_NMC-01014",
    "order_017_QS-01016",
    "order_003_SW-01002",
    "order_028_SW-01027",
)


def repo_root() -> Path:
    """Radice del repository (per ingest/extract e dati sintetici)."""
    return REPO_ROOT


def find_document(stem: str) -> Path | None:
    """Percorso del documento sintetico per uno stem ``order_NNN_PO``."""
    for folder, suffix in (("xlsx", ".xlsx"), ("eml", ".eml"), ("pdf", ".pdf")):
        path = DOCUMENTS_DIR / folder / f"{stem}{suffix}"
        if path.is_file():
            return path
    return None


def load_ground_truth(stem: str) -> dict[str, Any] | None:
    """Carica il VOF di ground truth, se presente."""
    path = GROUND_TRUTH_DIR / f"{stem}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def build_reference_provider() -> DatagenReferenceDataProvider:
    """Anagrafica datagen con tutti i clienti in allowlist (AUTO_POST possibile)."""
    provider = DatagenReferenceDataProvider.from_datagen()
    for customer in provider._customers_by_ref.values():
        customer.allowlisted = True
        customer.approved_orders_without_corrections = 25
    return provider


def build_engine(provider: DatagenReferenceDataProvider) -> ValidationEngine:
    """Motore regole ancorato alla data demo ``2026-04-02``."""
    return ValidationEngine(reference_data=provider, as_of=DEMO_AS_OF)


def _ingest_and_extract(path: Path) -> dict[str, Any] | None:
    """Ingest + estrazione deterministica. ``None`` se il parser fallisce."""
    import importlib

    # importlib: ingest/extract sono fuori da src/, mypy non deve analizzarli.
    ingest_mod = importlib.import_module("ingest")
    extract_mod = importlib.import_module("extract")
    backends_mod = importlib.import_module("extract.backends")
    try:
        normalized = ingest_mod.Ingestor().ingest(path)
        result = extract_mod.OrderExtractor(
            backend=backends_mod.MockBackend(),
            validate_output=False,
        ).extract(normalized.to_dict())
    except Exception:  # noqa: BLE001 — un documento non deve far cadere la demo
        return None
    payload = result.to_dict()
    return payload if isinstance(payload, dict) else None


def load_extracted_vof(stem: str) -> dict[str, Any]:
    """VOF da ground truth (estrazione deterministica del dataset) + ingest.

    Se il ground truth manca, si usa l'output di ingest → MockBackend.
    """
    ground = load_ground_truth(stem)
    document = find_document(stem)
    extracted: dict[str, Any] | None = None
    if document is not None:
        extracted = _ingest_and_extract(document)

    if ground is not None:
        vof = copy.deepcopy(ground)
        if extracted:
            source = dict(vof.get("source") or {})
            extracted_source = extracted.get("source") or {}
            for key in ("channel", "message_id", "from_address", "subject", "received_at"):
                if extracted_source.get(key) and not source.get(key):
                    source[key] = extracted_source[key]
            if extracted_source.get("documents"):
                source["documents"] = extracted_source["documents"]
            vof["source"] = source
            if extracted.get("evidence") and not vof.get("evidence"):
                vof["evidence"] = extracted["evidence"]
        return vof
    if extracted is not None:
        return extracted
    raise FileNotFoundError(f"Nessun VOF sintetico per {stem}")


def _customer_for_vof(
    vof: dict[str, Any], provider: DatagenReferenceDataProvider
) -> CustomerRecord | None:
    buyer = vof.get("buyer") or {}
    resolved = buyer.get("resolved") or {}
    ref = resolved.get("erp_partner_ref") or buyer.get("code_on_document")
    if ref:
        found = provider.get_customer_by_ref(str(ref))
        if found:
            return found
    partner_id = resolved.get("erp_partner_id")
    if partner_id is not None:
        found = provider.get_customer_by_partner_id(int(partner_id))
        if found:
            return found
    email = (buyer.get("contact") or {}).get("email") or (vof.get("source") or {}).get(
        "from_address"
    )
    domain = email_domain(email if isinstance(email, str) else None)
    name = str(buyer.get("name") or "").strip().lower()
    for customer in provider._customers_by_ref.values():
        if domain and customer.email_domain.lower() == domain:
            return customer
        if name and name in customer.name.lower():
            return customer
    return next(iter(provider._customers_by_ref.values()), None)


def _resolve_product(
    line: dict[str, Any],
    provider: DatagenReferenceDataProvider,
    customer_ref: str | None,
) -> tuple[ProductRecord | None, str | None]:
    resolution = line.get("resolution") or {}
    sku = resolution.get("sku") or line.get("seller_item_code")
    if sku:
        product = provider.get_product_by_sku(str(sku))
        if product:
            return product, "SELLER_CODE"
    buyer_code = line.get("buyer_item_code")
    if customer_ref and buyer_code:
        xref = provider.get_xref(customer_ref, str(buyer_code))
        if xref:
            product = provider.get_product_by_sku(xref.sku)
            if product:
                return product, "XREF"
    gtin = line.get("gtin")
    if gtin:
        product = provider.get_product_by_gtin(str(gtin))
        if product:
            return product, "GTIN"
    mpn = line.get("manufacturer_part_number")
    if mpn:
        product = provider.get_product_by_mpn(str(mpn))
        if product:
            return product, "MPN"
    return None, None


def _high_confidence_evidence(vof: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = dict(vof.get("evidence") or {})
    evidence["/header/po_number"] = {"confidence": 0.99, "source": "preprocessor"}
    evidence["/buyer"] = {"confidence": 0.99, "source": "datagen"}
    for index, line in enumerate(vof.get("lines") or []):
        for field in ("quantity", "uom", "uom_raw", "unit_price", "buyer_item_code"):
            if line.get(field) is not None:
                evidence[f"/lines/{index}/{field}"] = {
                    "confidence": 0.99,
                    "source": "preprocessor",
                }
    return evidence


def enrich_vof(
    vof: dict[str, Any],
    provider: DatagenReferenceDataProvider,
    *,
    mode: str = "clean",
) -> dict[str, Any]:
    """Allinea il VOF all'anagrafica datagen e, in ``clean``, lo rende AUTO_POST."""
    order = copy.deepcopy(vof)
    customer = _customer_for_vof(order, provider)
    if customer is not None:
        buyer = dict(order.get("buyer") or {})
        buyer["name"] = buyer.get("name") or customer.name
        buyer["resolved"] = {
            "erp_partner_id": customer.erp_partner_id,
            "erp_partner_ref": customer.erp_partner_ref,
            "method": "EMAIL_DOMAIN",
            "score": 0.99,
        }
        order["buyer"] = buyer

    customer_ref = None
    if customer is not None:
        customer_ref = customer.erp_partner_ref

    new_lines: list[dict[str, Any]] = []
    for line in order.get("lines") or []:
        item = dict(line)
        product, method = _resolve_product(item, provider, customer_ref)
        uom = normalize_uom(item.get("uom") or item.get("uom_raw")) or item.get("uom_raw")
        if uom:
            item["uom"] = uom
            item.setdefault("uom_raw", uom)
        if product is not None:
            qty = float(item.get("quantity") or 1)
            price = float(product.list_price)
            if mode == "clean":
                item["unit_price"] = price
                item["price_uom"] = product.sale_uom
                item["line_amount"] = round(qty * price, 2)
                item["uom"] = product.sale_uom
                item.setdefault("uom_raw", product.sale_uom)
            elif item.get("unit_price") is None:
                item["unit_price"] = price
            item["resolution"] = {
                "sku": product.sku,
                "erp_product_id": product.erp_product_id,
                "erp_uom": product.sale_uom,
                "erp_uom_id": 1,
                "erp_quantity": qty,
                "conversion_factor": 1,
                "method": method or "SELLER_CODE",
                "score": 1.0,
                "candidates": [],
                "erp_list_price": product.list_price,
            }
            if not item.get("description"):
                item["description"] = product.name
            if not item.get("seller_item_code"):
                item["seller_item_code"] = product.sku
        new_lines.append(item)
    order["lines"] = new_lines

    header = dict(order.get("header") or {})
    if mode == "clean":
        header["po_date"] = CLEAN_PO_DATE
        header["requested_delivery_date"] = CLEAN_DELIVERY_DATE
        header["currency"] = header.get("currency") or "USD"
        header["payment_terms_text"] = "Net 30"
        order.pop("ship_to", None)
    elif mode == "review":
        header["po_date"] = REVIEW_PO_DATE
        header["requested_delivery_date"] = "2026-12-15"
        header["currency"] = header.get("currency") or "USD"
        header["payment_terms_text"] = "Net 30"
        order.pop("ship_to", None)
    else:
        parsed = parse_date(header.get("po_date"))
        if parsed is not None:
            header["po_date"] = parsed.isoformat()
        parsed_delivery = parse_date(header.get("requested_delivery_date"))
        if parsed_delivery is not None:
            header["requested_delivery_date"] = parsed_delivery.isoformat()
    order["header"] = header

    computed = 0.0
    for line in order["lines"]:
        amount = line.get("line_amount")
        if amount is None:
            qty = float(line.get("quantity") or 0)
            price = float(line.get("unit_price") or 0)
            amount = qty * price
            line["line_amount"] = round(amount, 2)
        computed += float(amount or 0)
    totals = dict(order.get("totals") or {})
    totals["lines_amount_computed"] = round(computed, 2)
    if mode in {"clean", "review"}:
        totals["lines_amount_declared"] = round(computed, 2)
        totals["total_amount_declared"] = round(computed, 2)
    order["totals"] = totals
    order["charges"] = []
    order["evidence"] = _high_confidence_evidence(order)
    order["status"] = "EXTRACTED"
    return order


def clone_vof(vof: dict[str, Any], *, order_id: str, po_number: str | None = None) -> dict[str, Any]:
    """Copia un VOF con nuovo ``order_id`` (e opzionalmente nuovo PO)."""
    clone = copy.deepcopy(vof)
    clone["order_id"] = order_id
    if po_number is not None:
        header = dict(clone.get("header") or {})
        header["po_number"] = po_number
        clone["header"] = header
    source = dict(clone.get("source") or {})
    documents = list(source.get("documents") or [])
    new_docs = []
    for index, document in enumerate(documents):
        row = dict(document) if isinstance(document, dict) else {}
        row["sha256"] = ("d" * 63) + str(index % 10)
        row["document_id"] = f"doc-dup-{order_id[:8]}"
        new_docs.append(row)
    source["documents"] = new_docs
    source["message_id"] = f"<dup-{order_id[:8]}@synthetic.example>"
    clone["source"] = source
    return clone


def historical_from_vof(vof: dict[str, Any], customer_ref: str) -> HistoricalOrder:
    """Ordine già POSTED, per far scattare DUP-01 sul duplicato."""
    header = vof.get("header") or {}
    source = vof.get("source") or {}
    documents = source.get("documents") or []
    sha = None
    if documents and isinstance(documents[0], dict):
        sha = documents[0].get("sha256")
    lines = []
    for line in vof.get("lines") or []:
        resolution = line.get("resolution") or {}
        lines.append(
            {
                "sku": resolution.get("sku") or line.get("seller_item_code"),
                "quantity": line.get("quantity"),
            }
        )
    return HistoricalOrder(
        order_id=str(vof.get("order_id") or uuid.uuid4()),
        customer_ref=customer_ref,
        po_number=str(header.get("po_number") or ""),
        po_revision=int(header.get("po_revision") or 0),
        po_date=str(header.get("po_date") or CLEAN_PO_DATE),
        status="POSTED",
        sha256=str(sha) if sha else None,
        message_id=source.get("message_id"),
        lines=lines,
    )
