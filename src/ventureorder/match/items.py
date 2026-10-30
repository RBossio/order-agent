"""Riconoscimento dei codici articolo per riga (§6.2–6.4)."""

from __future__ import annotations

from typing import Any

from ventureorder.match.fields import strip_forbidden_from_line
from ventureorder.match.lexicon import attribute_score, expand_abbreviations, extract_attributes
from ventureorder.match.models import ItemCandidate, ItemMatch
from ventureorder.match.normalize import (
    normalize_description,
    normalize_gtin,
    normalize_item_code,
    normalize_sku,
    token_set_ratio,
)
from ventureorder.match.uom import convert_line_uom
from ventureorder.rules.access import normalize_uom
from ventureorder.rules.reference import (
    ProductRecord,
    ReferenceDataProvider,
    XrefRecord,
)

DEFAULT_THRESHOLDS: dict[str, float] = {
    "item_unresolved_min": 0.75,
    "item_fuzzy_high": 0.92,
    "item_fuzzy_margin": 0.08,
    "item_fuzzy_cap": 0.85,
    "item_fuzzy_confirm_min": 2,
    "item_xref_trusted": 1.00,
    "item_xref_candidate": 0.95,
    "item_seller_code": 0.98,
    "item_gtin": 0.99,
    "item_mpn": 0.97,
    "item_mpn_solo": 0.93,
    "price_tolerance_pct": 2.0,
}

_MEASURE_KEYS = ("dim", "inch", "mil", "thread", "metric", "size")


class ItemMatcher:
    """Cascata XREF → SKU interno → GTIN/EAN → descrizione fuzzy.

    Si ferma al primo risultato forte. Se più candidati coincidono, l'esito
    è ambiguo e si espongono i primi 3.
    """

    def __init__(
        self,
        provider: ReferenceDataProvider,
        thresholds: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._products = _iter_products(provider)
        self._by_sku: dict[str, ProductRecord] = {
            normalize_sku(product.sku): product for product in self._products if product.sku
        }
        self._by_gtin: dict[str, list[ProductRecord]] = {}
        self._xref_norm: dict[tuple[str, str], list[XrefRecord]] = {}
        for product in self._products:
            padded = normalize_gtin(product.gtin) if product.gtin else None
            if padded:
                self._by_gtin.setdefault(padded, []).append(product)
        for xref in _iter_xrefs(provider):
            norm = normalize_item_code(xref.customer_item_code)
            if norm:
                self._xref_norm.setdefault((xref.customer_ref, norm), []).append(xref)

    def resolve(self, line: dict[str, Any], customer_ref: str | None) -> ItemMatch:
        """Riconosce il prodotto di una riga VOF.

        Non legge ``resolution``, ``sku`` né ``erp_product_id`` già risolti
        (vedi ``match.fields``). ``customer_ref`` arriva dal matcher cliente,
        non dal ground truth.
        """
        line = strip_forbidden_from_line(line)
        xref_match = self._match_xref(line, customer_ref)
        if xref_match is not None:
            return xref_match

        sku_match = self._match_sku(line)
        if sku_match is not None:
            return sku_match

        gtin_match = self._match_gtin(line)
        if gtin_match is not None:
            return gtin_match

        fuzzy = self._match_fuzzy(line)
        if fuzzy is not None:
            return fuzzy
        return ItemMatch(product=None, score=0.0, method="UNRESOLVED")

    def _decorate(
        self, product: ProductRecord, score: float, method: str, line: dict[str, Any]
    ) -> ItemMatch:
        erp_qty, factor, erp_uom = convert_line_uom(self.provider, product, line)
        return ItemMatch(
            product=product,
            score=score,
            method=method,
            conversion_factor=factor,
            erp_uom=erp_uom,
            erp_quantity=erp_qty,
            erp_list_price=product.list_price,
        )

    def _match_xref(self, line: dict[str, Any], customer_ref: str | None) -> ItemMatch | None:
        if not customer_ref:
            return None
        code = line.get("buyer_item_code")
        if not code:
            return None
        norm = normalize_item_code(str(code))
        if not norm:
            return None
        hits = list(self._xref_norm.get((customer_ref, norm), []))
        if not hits:
            raw = self.provider.get_xref(customer_ref, str(code))
            if raw:
                hits = [raw]
        if not hits:
            return None
        products: list[tuple[XrefRecord, ProductRecord]] = []
        for xref in hits:
            product = self.provider.get_product_by_sku(xref.sku)
            if product:
                products.append((xref, product))
        if not products:
            return None
        skus = {item.sku for _, item in products}
        trusted = float(self.thresholds.get("item_xref_trusted", 1.0))
        candidate = float(self.thresholds.get("item_xref_candidate", 0.95))
        if len(skus) > 1:
            return ItemMatch(
                product=None,
                score=self._ambiguous_score(min(trusted, candidate)),
                method="XREF",
                ambiguous=True,
                candidates=[
                    ItemCandidate(
                        sku=item.sku,
                        score=trusted if xref.status.upper() == "TRUSTED" else candidate,
                        erp_product_id=item.erp_product_id,
                        description=item.name,
                        method="XREF",
                    )
                    for xref, item in products[:3]
                ],
            )
        xref, product = products[0]
        score = trusted if str(xref.status or "TRUSTED").upper() == "TRUSTED" else candidate
        return self._decorate(product, score, "XREF", line)

    def _match_sku(self, line: dict[str, Any]) -> ItemMatch | None:
        score = float(self.thresholds.get("item_seller_code", 0.98))
        for field in ("seller_item_code", "buyer_item_code"):
            raw = line.get(field)
            if not raw:
                continue
            product = self._by_sku.get(normalize_sku(str(raw)))
            if product is None:
                product = self.provider.get_product_by_sku(str(raw))
            if product:
                return self._decorate(product, score, "SELLER_CODE", line)
        return None

    def _match_gtin(self, line: dict[str, Any]) -> ItemMatch | None:
        padded = normalize_gtin(line.get("gtin") if line.get("gtin") else None)
        if not padded:
            return None
        hits = list(self._by_gtin.get(padded, []))
        if not hits:
            found = self.provider.get_product_by_gtin(padded)
            if found:
                hits = [found]
        if not hits:
            return None
        score = float(self.thresholds.get("item_gtin", 0.99))
        unique = _unique_products(hits)
        if len(unique) > 1:
            return ItemMatch(
                product=None,
                score=self._ambiguous_score(score),
                method="GTIN",
                ambiguous=True,
                candidates=[
                    ItemCandidate(
                        sku=item.sku,
                        score=score,
                        erp_product_id=item.erp_product_id,
                        description=item.name,
                        method="GTIN",
                    )
                    for item in unique[:3]
                ],
            )
        return self._decorate(unique[0], score, "GTIN", line)

    def _match_fuzzy(self, line: dict[str, Any]) -> ItemMatch | None:
        description = line.get("description")
        if not description:
            return None
        query = expand_abbreviations(normalize_description(str(description)))
        if not query:
            return None
        query_attrs = extract_attributes(str(description))
        line_uom = normalize_uom(line.get("uom")) or normalize_uom(line.get("uom_raw"))
        unresolved_min = float(self.thresholds.get("item_unresolved_min", 0.75))
        margin = float(self.thresholds.get("item_fuzzy_margin", 0.08))
        fuzzy_cap = float(self.thresholds.get("item_fuzzy_cap", 0.85))
        fuzzy_high = float(self.thresholds.get("item_fuzzy_high", 0.92))
        confirm_min = int(self.thresholds.get("item_fuzzy_confirm_min", 2))
        ranked: list[tuple[float, ProductRecord, float, bool, dict[str, str]]] = []
        for product in self._products:
            catalog = expand_abbreviations(normalize_description(product.name))
            s_text = token_set_ratio(query, catalog) / 100.0
            if s_text < 0.40:
                continue
            prod_attrs = extract_attributes(product.name)
            s_attr, discordant = attribute_score(query_attrs, prod_attrs)
            s_uom = self._uom_signal(line_uom, product)
            # Peso semantico assente → va su S_testo (§6.3). S_storico = 0 nel prototipo.
            score = 0.50 * s_text + 0.25 * s_attr + 0.15 * s_uom
            if discordant:
                score = min(score - 0.30, 0.80)
            score = max(0.0, min(0.95, score))
            if score >= unresolved_min * 0.8:
                ranked.append((score, product, s_uom, discordant, prod_attrs))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best, best_uom, discordant, prod_attrs = ranked[0]
        if best_score < unresolved_min:
            return ItemMatch(
                product=None,
                score=best_score,
                method="UNRESOLVED",
                candidates=[_candidate(item, score) for score, item, *_rest in ranked[:3]],
            )
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        ambiguous = len(ranked) > 1 and (best_score - second) < margin
        confirmations = (
            0
            if discordant
            else self._independent_confirmations(line, best, query_attrs, prod_attrs, best_uom)
        )
        # Ambiguo o senza conferme indipendenti: mai confidenza alta (§6.6).
        if ambiguous or confirmations < confirm_min:
            score = min(best_score, fuzzy_cap)
        else:
            score = min(best_score, fuzzy_high)
        match = self._decorate(best, score, "FUZZY", line)
        match.ambiguous = ambiguous
        match.candidates = [_candidate(item, raw) for raw, item, *_rest in ranked[:3]]
        return match

    def _ambiguous_score(self, score: float) -> float:
        """Un esito ambiguo non può mai avere confidenza alta (≥ 0,9)."""
        cap = float(self.thresholds.get("item_fuzzy_cap", 0.85))
        return min(float(score), cap)

    def _independent_confirmations(
        self,
        line: dict[str, Any],
        product: ProductRecord,
        query_attrs: dict[str, str],
        catalog_attrs: dict[str, str],
        s_uom: float,
    ) -> int:
        """Conferme indipendenti dalla sola similarità testuale.

        UoM compatibile, prezzo entro il listino, misura o colore uguali.
        """
        count = 0
        if s_uom >= 1.0:
            count += 1
        if self._price_within_list(line, product):
            count += 1
        if _measure_or_color_match(query_attrs, catalog_attrs):
            count += 1
        return count

    def _price_within_list(self, line: dict[str, Any], product: ProductRecord) -> bool:
        raw = line.get("unit_price")
        if not isinstance(raw, int | float):
            return False
        list_price = float(product.list_price)
        if list_price == 0:
            return float(raw) == 0.0
        tol = float(self.thresholds.get("price_tolerance_pct", 2.0)) / 100.0
        return abs(float(raw) - list_price) / abs(list_price) <= tol

    def _uom_signal(self, line_uom: str | None, product: ProductRecord) -> float:
        sale = normalize_uom(product.sale_uom)
        if not line_uom or not sale:
            return 0.5
        if line_uom == sale:
            return 1.0
        if self.provider.get_uom_conversion(line_uom, sale, product.sku) is not None:
            return 0.5
        return 0.0


def _measure_or_color_match(query: dict[str, str], catalog: dict[str, str]) -> bool:
    """True se misura o colore coincidono tra documento e catalogo."""
    if query.get("color") and catalog.get("color") == query["color"]:
        return True
    return any(key in query and catalog.get(key) == query[key] for key in _MEASURE_KEYS)


def _candidate(product: ProductRecord, score: float) -> ItemCandidate:
    return ItemCandidate(
        sku=product.sku,
        score=score,
        erp_product_id=product.erp_product_id,
        description=product.name,
        method="FUZZY",
    )


def _iter_products(provider: ReferenceDataProvider) -> list[ProductRecord]:
    iterator = getattr(provider, "iter_products", None)
    if callable(iterator):
        return list(iterator())
    return []


def _iter_xrefs(provider: ReferenceDataProvider) -> list[XrefRecord]:
    iterator = getattr(provider, "iter_xrefs", None)
    if callable(iterator):
        return list(iterator())
    return []


def _unique_products(items: list[ProductRecord]) -> list[ProductRecord]:
    seen: set[str] = set()
    out: list[ProductRecord] = []
    for item in items:
        if item.sku in seen:
            continue
        seen.add(item.sku)
        out.append(item)
    return out
