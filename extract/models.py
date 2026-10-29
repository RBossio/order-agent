"""Modelli dati per l'estrazione ordini."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class WarningSeverity(str, Enum):
    """Livelli di severità degli avvisi."""
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class FieldConfidence:
    """Confidenza per un singolo campo estratto."""
    path: str
    confidence: float
    source: str | None = None
    snippet: str | None = None

    def to_dict(self) -> dict:
        d = {"path": self.path, "confidence": self.confidence}
        if self.source:
            d["source"] = self.source
        if self.snippet:
            d["snippet"] = self.snippet
        return d


@dataclass
class ExtractionWarning:
    """Avviso generato durante l'estrazione."""
    code: str
    severity: WarningSeverity
    message: str
    path: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.path:
            d["path"] = self.path
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class ExtractedParty:
    """Parte estratta (buyer, seller, ship_to, bill_to)."""
    name: str | None = None
    code_on_document: str | None = None
    tax_id: str | None = None
    gln: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    address_city: str | None = None
    address_region: str | None = None
    address_postal_code: str | None = None
    address_country: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.name:
            d["name"] = self.name
        if self.code_on_document:
            d["code_on_document"] = self.code_on_document
        if self.tax_id:
            d["tax_id"] = self.tax_id
        if self.gln:
            d["gln"] = self.gln
        
        address = {}
        if self.address_line1:
            address["line1"] = self.address_line1
        if self.address_line2:
            address["line2"] = self.address_line2
        if self.address_city:
            address["city"] = self.address_city
        if self.address_region:
            address["region"] = self.address_region
        if self.address_postal_code:
            address["postal_code"] = self.address_postal_code
        if self.address_country:
            address["country"] = self.address_country
        if address:
            d["address"] = address
        
        contact = {}
        if self.contact_name:
            contact["name"] = self.contact_name
        if self.contact_email:
            contact["email"] = self.contact_email
        if self.contact_phone:
            contact["phone"] = self.contact_phone
        if contact:
            d["contact"] = contact
        
        return d


@dataclass
class ExtractedPack:
    """Struttura confezione estratta."""
    raw: str | None = None
    inner_count: float | None = None
    inner_size: float | None = None
    inner_uom: str | None = None

    def to_dict(self) -> dict | None:
        if not any([self.raw, self.inner_count, self.inner_size, self.inner_uom]):
            return None
        d: dict[str, Any] = {}
        if self.raw:
            d["raw"] = self.raw
        if self.inner_count is not None:
            d["inner_count"] = self.inner_count
        if self.inner_size is not None:
            d["inner_size"] = self.inner_size
        if self.inner_uom:
            d["inner_uom"] = self.inner_uom
        return d


@dataclass
class ExtractedLine:
    """Riga ordine estratta."""
    line_no: int
    description: str
    quantity: float
    uom_raw: str
    buyer_item_code: str | None = None
    seller_item_code: str | None = None
    manufacturer_name: str | None = None
    manufacturer_part_number: str | None = None
    gtin: str | None = None
    uom: str | None = None
    pack: ExtractedPack | None = None
    unit_price: float | None = None
    price_uom: str | None = None
    price_basis_qty: float | None = None
    discount_pct: float | None = None
    line_amount: float | None = None
    requested_delivery_date: str | None = None
    notes: str | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "line_no": self.line_no,
            "description": self.description,
            "quantity": self.quantity,
            "uom_raw": self.uom_raw,
        }
        if self.buyer_item_code:
            d["buyer_item_code"] = self.buyer_item_code
        if self.seller_item_code:
            d["seller_item_code"] = self.seller_item_code
        if self.manufacturer_name:
            d["manufacturer_name"] = self.manufacturer_name
        if self.manufacturer_part_number:
            d["manufacturer_part_number"] = self.manufacturer_part_number
        if self.gtin:
            d["gtin"] = self.gtin
        if self.uom:
            d["uom"] = self.uom
        pack_dict = self.pack.to_dict() if self.pack else None
        if pack_dict:
            d["pack"] = pack_dict
        if self.unit_price is not None:
            d["unit_price"] = self.unit_price
        if self.price_uom:
            d["price_uom"] = self.price_uom
        if self.price_basis_qty is not None:
            d["price_basis_qty"] = self.price_basis_qty
        if self.discount_pct is not None:
            d["discount_pct"] = self.discount_pct
        if self.line_amount is not None:
            d["line_amount"] = self.line_amount
        if self.requested_delivery_date:
            d["requested_delivery_date"] = self.requested_delivery_date
        if self.notes:
            d["notes"] = self.notes
        return d


@dataclass
class ExtractedHeader:
    """Testata ordine estratta."""
    po_number: str
    po_date: str
    currency: str = "USD"
    po_revision: int = 0
    requested_delivery_date: str | None = None
    buyer_reference: str | None = None
    payment_terms_text: str | None = None
    incoterms_code: str | None = None
    incoterms_place: str | None = None
    ship_via: str | None = None
    notes: str | None = None
    language: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "po_number": self.po_number,
            "po_date": self.po_date,
            "currency": self.currency,
            "po_revision": self.po_revision,
        }
        if self.requested_delivery_date:
            d["requested_delivery_date"] = self.requested_delivery_date
        if self.buyer_reference:
            d["buyer_reference"] = self.buyer_reference
        if self.payment_terms_text:
            d["payment_terms_text"] = self.payment_terms_text
        if self.incoterms_code:
            d["incoterms"] = {"code": self.incoterms_code}
            if self.incoterms_place:
                d["incoterms"]["place"] = self.incoterms_place
        if self.ship_via:
            d["ship_via"] = self.ship_via
        if self.notes:
            d["notes"] = self.notes
        if self.language:
            d["language"] = self.language
        return d


@dataclass
class ExtractedTotals:
    """Totali estratti."""
    lines_amount_declared: float | None = None
    tax_amount_declared: float | None = None
    total_amount_declared: float | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.lines_amount_declared is not None:
            d["lines_amount_declared"] = self.lines_amount_declared
        if self.tax_amount_declared is not None:
            d["tax_amount_declared"] = self.tax_amount_declared
        if self.total_amount_declared is not None:
            d["total_amount_declared"] = self.total_amount_declared
        return d


@dataclass
class ExtractedOrder:
    """Ordine completamente estratto (senza risoluzione codici)."""
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "delta-industrial-supply"
    document_type: str = "ORIGINAL"
    status: str = "EXTRACTED"
    header: ExtractedHeader | None = None
    buyer: ExtractedParty | None = None
    seller: ExtractedParty | None = None
    ship_to: ExtractedParty | None = None
    bill_to: ExtractedParty | None = None
    lines: list[ExtractedLine] = field(default_factory=list)
    totals: ExtractedTotals | None = None
    overall_confidence: float = 0.0
    
    source_channel: str = "EMAIL_IMAP"
    source_message_id: str | None = None
    source_from_address: str | None = None
    source_subject: str | None = None
    source_received_at: str | None = None
    source_documents: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        d: dict[str, Any] = {
            "schema_version": "1.0",
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "document_type": self.document_type,
            "status": self.status,
            "source": {
                "channel": self.source_channel,
                "message_id": self.source_message_id,
                "from_address": self.source_from_address,
                "subject": self.source_subject,
                "received_at": self.source_received_at or now,
                "documents": self.source_documents or [],
            },
            "header": self.header.to_dict() if self.header else {},
            "lines": [line.to_dict() for line in self.lines],
            "processing": {
                "extractor": "extract/ollama",
                "created_at": now,
            },
        }
        
        if self.buyer:
            d["buyer"] = self.buyer.to_dict()
        if self.seller:
            d["seller"] = self.seller.to_dict()
        if self.ship_to:
            d["ship_to"] = self.ship_to.to_dict()
        if self.bill_to:
            d["bill_to"] = self.bill_to.to_dict()
        if self.totals:
            d["totals"] = self.totals.to_dict()
        
        return d


@dataclass
class ExtractionResult:
    """Risultato completo dell'estrazione."""
    order: ExtractedOrder
    field_confidences: list[FieldConfidence] = field(default_factory=list)
    warnings: list[ExtractionWarning] = field(default_factory=list)
    llm_calls: int = 0
    llm_tokens_used: int = 0
    extraction_time_ms: int = 0
    preprocessed_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        order_dict = self.order.to_dict()
        
        evidence = {}
        for fc in self.field_confidences:
            evidence[fc.path] = {"confidence": fc.confidence}
            if fc.source:
                evidence[fc.path]["source"] = fc.source
            if fc.snippet:
                evidence[fc.path]["snippet"] = fc.snippet
        if evidence:
            order_dict["evidence"] = evidence
        
        if self.warnings:
            order_dict["validation"] = {
                "issues": [w.to_dict() for w in self.warnings]
            }
        
        return order_dict
