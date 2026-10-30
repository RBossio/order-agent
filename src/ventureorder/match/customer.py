"""Riconoscimento del cliente a partire da un VOF estratto."""

from __future__ import annotations

from typing import Any

from ventureorder.match.fields import strip_forbidden_from_buyer
from ventureorder.match.models import CustomerCandidate, CustomerMatch
from ventureorder.match.normalize import (
    normalize_address,
    normalize_name,
    normalize_tax_id,
    sender_domain,
    token_set_ratio,
)
from ventureorder.rules.reference import CustomerRecord, ReferenceDataProvider

DEFAULT_THRESHOLDS: dict[str, float] = {
    "customer_fuzzy_name_min": 0.85,
    "customer_fuzzy_name_review": 0.95,
    "customer_ambiguous_margin": 0.08,
    "customer_address_min": 0.90,
}


class CustomerMatcher:
    """Cascata TAX_ID → EMAIL_DOMAIN → FUZZY_NAME → ADDRESS.

    Si ferma al primo passo con almeno un candidato. Più candidati allo
    stesso passo rendono l'esito ambiguo (nessun partner scelto).
    """

    def __init__(
        self,
        provider: ReferenceDataProvider,
        thresholds: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._customers = _iter_customers(provider)
        self._by_tax: dict[str, list[CustomerRecord]] = {}
        self._by_domain: dict[str, list[CustomerRecord]] = {}
        self._by_name: dict[str, list[CustomerRecord]] = {}
        self._by_address: dict[str, list[CustomerRecord]] = {}
        for customer in self._customers:
            tax = normalize_tax_id(customer.tax_id)
            if tax:
                self._by_tax.setdefault(tax, []).append(customer)
            domain = (customer.email_domain or "").strip().lower()
            if domain:
                self._by_domain.setdefault(domain, []).append(customer)
            name = normalize_name(customer.name)
            if name:
                self._by_name.setdefault(name, []).append(customer)
            self._index_addresses(customer)

    def _index_addresses(self, customer: CustomerRecord) -> None:
        keys: list[str] = []
        billing = normalize_address(customer.address)
        if billing:
            keys.append(billing)
        for entry in customer.ship_to or []:
            addr = entry.get("address") if isinstance(entry, dict) else None
            key = normalize_address(addr if isinstance(addr, dict) else None)
            if key:
                keys.append(key)
        for key in keys:
            bucket = self._by_address.setdefault(key, [])
            if customer not in bucket:
                bucket.append(customer)

    def resolve(self, vof: dict[str, Any]) -> CustomerMatch:
        """Riconosce il buyer del VOF. Cascata: P.IVA, email, nome, indirizzo.

        Non legge ``buyer.resolved``, ``code_on_document`` né altri ID anagrafici
        (vedi ``match.fields``).
        """
        raw_buyer = vof.get("buyer") if isinstance(vof.get("buyer"), dict) else {}
        buyer = strip_forbidden_from_buyer(raw_buyer if isinstance(raw_buyer, dict) else {})
        tax_hits = self._lookup_tax(buyer.get("tax_id"))
        if tax_hits:
            return self._finish(tax_hits, "TAX_ID", 1.0)

        domain = sender_domain(vof)
        domain_hits = self._lookup_domain(domain)
        if domain_hits:
            return self._finish(domain_hits, "EMAIL_DOMAIN", 0.99)

        name_match = self._lookup_name(buyer.get("name"))
        if name_match is not None:
            return name_match

        address = buyer.get("address")
        if not isinstance(address, dict):
            bill_to = vof.get("bill_to") if isinstance(vof.get("bill_to"), dict) else {}
            address = bill_to.get("address") if isinstance(bill_to, dict) else None
        addr_hits = self._lookup_address(address if isinstance(address, dict) else None)
        if addr_hits:
            min_addr = float(self.thresholds.get("customer_address_min", 0.90))
            return self._finish(addr_hits, "ADDRESS", min_addr)

        return CustomerMatch(customer=None, score=0.0, method="UNRESOLVED")

    def _lookup_tax(self, tax_id: Any) -> list[CustomerRecord]:
        key = normalize_tax_id(str(tax_id) if tax_id else None)
        if not key:
            return []
        return list(self._by_tax.get(key, []))

    def _lookup_domain(self, domain: str | None) -> list[CustomerRecord]:
        if not domain:
            return []
        needle = domain.strip().lower()
        hits = list(self._by_domain.get(needle, []))
        if hits:
            return hits
        for stored, customers in self._by_domain.items():
            if needle == stored or needle.endswith("." + stored) or stored.endswith("." + needle):
                hits.extend(customers)
        return _unique(hits)

    def _lookup_name(self, name: Any) -> CustomerMatch | None:
        normalized = normalize_name(str(name) if name else None)
        if not normalized:
            return None
        exact = list(self._by_name.get(normalized, []))
        if exact:
            return self._finish(exact, "FUZZY_NAME", 0.97)

        min_score = float(self.thresholds.get("customer_fuzzy_name_min", 0.85))
        margin = float(self.thresholds.get("customer_ambiguous_margin", 0.08))
        ranked: list[tuple[float, CustomerRecord]] = []
        for customer in self._customers:
            catalog = normalize_name(customer.name)
            if not catalog:
                continue
            score = token_set_ratio(normalized, catalog) / 100.0
            if score >= min_score:
                ranked.append((score, customer))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best = ranked[0]
        close = [item for item in ranked if best_score - item[0] < margin]
        if len(close) > 1:
            return CustomerMatch(
                customer=None,
                score=min(best_score, float(self.thresholds.get("customer_fuzzy_name_min", 0.85))),
                method="FUZZY_NAME",
                ambiguous=True,
                candidates=[
                    CustomerCandidate(
                        erp_partner_id=item.erp_partner_id,
                        erp_partner_ref=item.erp_partner_ref,
                        name=item.name,
                        score=score,
                        method="FUZZY_NAME",
                    )
                    for score, item in close[:5]
                ],
            )
        return CustomerMatch(
            customer=best,
            score=min(best_score, 0.95),
            method="FUZZY_NAME",
            candidates=[
                CustomerCandidate(
                    erp_partner_id=best.erp_partner_id,
                    erp_partner_ref=best.erp_partner_ref,
                    name=best.name,
                    score=best_score,
                    method="FUZZY_NAME",
                )
            ],
        )

    def _lookup_address(self, address: dict[str, Any] | None) -> list[CustomerRecord]:
        key = normalize_address(address)
        if not key:
            return []
        hits = list(self._by_address.get(key, []))
        if hits:
            return hits
        # Fuzzy leggero: stessa città+CAP e token_set su line1.
        city_cap = " ".join(
            part.lower().strip()
            for part in (
                str((address or {}).get("city") or ""),
                str((address or {}).get("postal_code") or ""),
            )
            if part
        )
        line1 = str((address or {}).get("line1") or (address or {}).get("street") or "").lower()
        if not city_cap or not line1:
            return []
        scored: list[CustomerRecord] = []
        for customer in self._customers:
            for raw in [
                customer.address,
                *[
                    e.get("address") if isinstance(e, dict) else None
                    for e in customer.ship_to or []
                ],
            ]:
                if not isinstance(raw, dict):
                    continue
                other_city = " ".join(
                    part.lower().strip()
                    for part in (str(raw.get("city") or ""), str(raw.get("postal_code") or ""))
                    if part
                )
                if other_city != city_cap:
                    continue
                other_line = str(raw.get("line1") or raw.get("street") or "").lower()
                if token_set_ratio(line1, other_line) >= 90:
                    scored.append(customer)
                    break
        return _unique(scored)

    def _finish(self, hits: list[CustomerRecord], method: str, score: float) -> CustomerMatch:
        unique = _unique(hits)
        if not unique:
            return CustomerMatch(customer=None, score=0.0, method="UNRESOLVED")
        candidates = [
            CustomerCandidate(
                erp_partner_id=item.erp_partner_id,
                erp_partner_ref=item.erp_partner_ref,
                name=item.name,
                score=score,
                method=method,
            )
            for item in unique
        ]
        if len(unique) > 1:
            return CustomerMatch(
                customer=None,
                score=min(score, float(self.thresholds.get("customer_fuzzy_name_min", 0.85))),
                method=method,
                ambiguous=True,
                candidates=candidates,
            )
        return CustomerMatch(
            customer=unique[0],
            score=score,
            method=method,
            candidates=candidates,
        )


def _iter_customers(provider: ReferenceDataProvider) -> list[CustomerRecord]:
    iterator = getattr(provider, "iter_customers", None)
    if callable(iterator):
        return list(iterator())
    return []


def _unique(items: list[CustomerRecord]) -> list[CustomerRecord]:
    seen: set[str] = set()
    out: list[CustomerRecord] = []
    for item in items:
        if item.erp_partner_ref in seen:
            continue
        seen.add(item.erp_partner_ref)
        out.append(item)
    return out
