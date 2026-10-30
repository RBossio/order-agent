"""Risultati del riconoscimento cliente e articolo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ventureorder.rules.reference import CustomerRecord, ProductRecord


@dataclass(frozen=True)
class CustomerCandidate:
    """Candidato cliente (per esiti ambigui)."""

    erp_partner_id: int
    erp_partner_ref: str
    name: str
    score: float
    method: str


@dataclass
class CustomerMatch:
    """Esito del riconoscimento cliente.

    Se ``ambiguous`` è vero non si sceglie un partner: CUS-01 resta BLOCK.
    """

    customer: CustomerRecord | None
    score: float
    method: str
    ambiguous: bool = False
    candidates: list[CustomerCandidate] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        """True se c'è un unico cliente con score > 0."""
        return self.customer is not None and not self.ambiguous and self.score > 0

    def to_vof(self) -> dict[str, Any] | None:
        """Serializza in ``buyer.resolved`` (schema VOF)."""
        if not self.resolved or self.customer is None:
            if self.ambiguous:
                return {
                    "erp_partner_id": None,
                    "erp_partner_ref": None,
                    "method": None,
                    "score": 0.0,
                }
            return None
        return {
            "erp_partner_id": self.customer.erp_partner_id,
            "erp_partner_ref": self.customer.erp_partner_ref,
            "method": self.method,
            "score": round(float(self.score), 4),
        }


@dataclass(frozen=True)
class ItemCandidate:
    """Candidato prodotto, allineato a ``$defs/candidate`` dello schema."""

    sku: str
    score: float
    erp_product_id: int | None = None
    description: str | None = None
    method: str = "FUZZY"

    def to_vof(self) -> dict[str, Any]:
        """Serializza un candidato per ``resolution.candidates``."""
        return {
            "sku": self.sku,
            "erp_product_id": self.erp_product_id,
            "description": self.description,
            "score": round(float(self.score), 4),
            "method": self.method,
        }


@dataclass
class ItemMatch:
    """Esito del riconoscimento di una riga.

    In caso ambiguo su metodo forte (XREF/SKU/GTIN) non si assegna lo SKU.
    In caso FUZZY ambiguo si propongono i primi 3 candidati e la confidenza
    resta sotto la soglia di revisione (mai ≥ 0,9).
    """

    product: ProductRecord | None
    score: float
    method: str
    ambiguous: bool = False
    candidates: list[ItemCandidate] = field(default_factory=list)
    conversion_factor: float | None = None
    erp_uom: str | None = None
    erp_quantity: float | None = None
    erp_list_price: float | None = None

    def to_vof(self) -> dict[str, Any]:
        """Serializza in ``line.resolution``."""
        top = [c.to_vof() for c in self.candidates[:3]] if self.ambiguous else []
        strong_ambiguous = self.ambiguous and self.method in {
            "XREF",
            "SELLER_CODE",
            "GTIN",
            "MPN",
        }
        if self.product is None or strong_ambiguous or self.method == "UNRESOLVED":
            return {
                "sku": None,
                "erp_product_id": None,
                "erp_uom": self.erp_uom,
                "erp_quantity": self.erp_quantity,
                "conversion_factor": self.conversion_factor,
                "method": "UNRESOLVED",
                "score": round(float(self.score), 4),
                "candidates": top,
                "erp_list_price": self.erp_list_price,
            }
        return {
            "sku": self.product.sku,
            "erp_product_id": self.product.erp_product_id,
            "erp_uom": self.erp_uom or self.product.sale_uom,
            "erp_quantity": self.erp_quantity,
            "conversion_factor": self.conversion_factor,
            "method": self.method,
            "score": round(float(self.score), 4),
            "candidates": top,
            "erp_list_price": (
                self.erp_list_price if self.erp_list_price is not None else self.product.list_price
            ),
        }
