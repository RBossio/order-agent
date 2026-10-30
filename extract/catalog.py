"""Matching anagrafica: SKU, xref, UoM e cliente (DatagenReferenceDataProvider)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ventureorder.rules.access import email_domain, normalize_uom
from ventureorder.rules.reference import (
    CustomerRecord,
    DatagenReferenceDataProvider,
    ProductRecord,
    ReferenceDataProvider,
    XrefRecord,
)

_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|corp|ltd|co|company|group|holdings|manufacturing)\b\.?",
    re.IGNORECASE,
)


def _norm_name(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower().replace("(synthetic)", "")
    text = _COMPANY_SUFFIX.sub(" ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@dataclass
class ItemHit:
    """Esito del riconoscimento articolo."""

    product: ProductRecord | None = None
    xref: XrefRecord | None = None
    customer_ref: str | None = None
    method: str = "UNRESOLVED"
    role: str = "unknown"  # seller | buyer | unknown


class CatalogMatcher:
    """Wrapper sul provider di anagrafica per l'estrazione."""

    def __init__(self, provider: ReferenceDataProvider | None = None) -> None:
        self.provider: ReferenceDataProvider | None = provider
        if self.provider is None:
            try:
                self.provider = DatagenReferenceDataProvider.from_datagen()
            except (FileNotFoundError, ImportError, OSError):
                self.provider = None

    def classify_item_code(self, code: str | None, customer_ref: str | None = None) -> ItemHit:
        """Classifica un codice come SKU venditore o xref cliente."""
        hit = ItemHit()
        if not code or self.provider is None:
            return hit
        token = str(code).strip()
        if not token:
            return hit

        product = self.provider.get_product_by_sku(token)
        if product is not None:
            hit.product = product
            hit.method = "SELLER_CODE"
            hit.role = "seller"
            return hit

        if customer_ref:
            xref = self.provider.get_xref(customer_ref, token)
            if xref is not None:
                hit.xref = xref
                hit.customer_ref = customer_ref
                hit.product = self.provider.get_product_by_sku(xref.sku)
                hit.method = "XREF"
                hit.role = "buyer"
                return hit

        xrefs = self._xrefs_for_code(token)
        if len(xrefs) == 1:
            ref, xref = xrefs[0]
            hit.xref = xref
            hit.customer_ref = ref
            hit.product = self.provider.get_product_by_sku(xref.sku)
            hit.method = "XREF"
            hit.role = "buyer"
            return hit
        return hit

    def resolve_line(
        self,
        seller_item_code: str | None,
        buyer_item_code: str | None,
        customer_ref: str | None = None,
        uom_raw: str | None = None,
        quantity: float | None = None,
    ) -> dict[str, Any]:
        """Costruisce ``line.resolution`` (SKU esatto o xref; niente fuzzy)."""
        hit = self.classify_item_code(seller_item_code, customer_ref)
        if hit.product is None:
            hit = self.classify_item_code(buyer_item_code, customer_ref)

        if hit.product is None:
            return {"method": "UNRESOLVED", "score": 0.0, "sku": None, "erp_product_id": None}

        product = hit.product
        factor = 1.0
        erp_uom = product.sale_uom
        erp_qty = quantity
        if uom_raw and self.provider is not None:
            src = normalize_uom(uom_raw)
            dst = normalize_uom(product.sale_uom)
            if src and dst and src != dst:
                conv = self.provider.get_uom_conversion(src, dst, product.sku)
                if conv:
                    factor = float(conv)
                    if quantity is not None:
                        erp_qty = quantity * factor
                else:
                    factor = None  # type: ignore[assignment]
        return {
            "sku": product.sku,
            "erp_product_id": product.erp_product_id,
            "erp_uom": erp_uom,
            "erp_quantity": erp_qty,
            "conversion_factor": factor if factor is not None else None,
            "method": hit.method,
            "score": 1.0,
            "candidates": [],
            "erp_list_price": product.list_price,
        }

    def resolve_buyer(
        self,
        name: str | None,
        from_address: str | None,
        item_customer_ref: str | None = None,
    ) -> dict[str, Any] | None:
        """Risolve il cliente da dominio email, xref o nome."""
        if self.provider is None:
            return None
        domain = email_domain(from_address)
        if domain:
            customer = self._customer_by_domain(domain)
            if customer is not None:
                return _buyer_resolved(customer, "EMAIL_DOMAIN", 0.99)

        if item_customer_ref:
            customer = self.provider.get_customer_by_ref(item_customer_ref)
            if customer is not None:
                return _buyer_resolved(customer, "CODE", 0.95)

        needle = _norm_name(name)
        if needle:
            matches = [
                customer
                for customer in self._iter_customers()
                if needle == _norm_name(customer.name) or needle in _norm_name(customer.name)
            ]
            if len(matches) == 1:
                return _buyer_resolved(matches[0], "FUZZY_NAME", 0.96)
        return None

    def is_valid_uom(self, uom: str | None) -> bool:
        if not uom:
            return False
        if self.provider is None:
            return True
        return self.provider.is_valid_uom(str(uom))

    def item_in_catalog(self, seller_code: str | None, buyer_code: str | None) -> bool:
        hit = self.classify_item_code(seller_code)
        if hit.product is not None:
            return True
        hit = self.classify_item_code(buyer_code)
        return hit.product is not None

    def _xrefs_for_code(self, code: str) -> list[tuple[str, XrefRecord]]:
        provider = self.provider
        if provider is None:
            return []
        xrefs = getattr(provider, "_xrefs", {})
        needle = code.strip()
        found: list[tuple[str, XrefRecord]] = []
        for (customer_ref, item_code), xref in xrefs.items():
            if str(item_code).strip() == needle:
                found.append((str(customer_ref), xref))
        return found

    def _iter_customers(self) -> list[CustomerRecord]:
        provider = self.provider
        if provider is None:
            return []
        by_ref = getattr(provider, "_customers_by_ref", {})
        return list(by_ref.values())

    def _customer_by_domain(self, domain: str) -> CustomerRecord | None:
        domain = domain.lower()
        matches = [
            customer
            for customer in self._iter_customers()
            if customer.email_domain and (
                domain == customer.email_domain.lower()
                or domain.endswith("." + customer.email_domain.lower())
            )
        ]
        if len(matches) == 1:
            return matches[0]
        return None


def _buyer_resolved(customer: CustomerRecord, method: str, score: float) -> dict[str, Any]:
    return {
        "erp_partner_id": customer.erp_partner_id,
        "erp_partner_ref": customer.erp_partner_ref,
        "method": method,
        "score": score,
    }
