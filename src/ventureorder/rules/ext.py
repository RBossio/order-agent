"""Regole di estrazione (EXT-01 … EXT-03)."""

from __future__ import annotations

import re

from ventureorder.rules.access import issue, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.registry import rule

CRITICAL_HEADER = {
    "/header/po_number": "numero PO",
    "/header/currency": "valuta",
    "/buyer": "cliente",
    "/buyer/name": "cliente",
    "/buyer/resolved": "cliente",
}

CRITICAL_LINE_FIELDS = {
    "buyer_item_code": "codice",
    "seller_item_code": "codice",
    "quantity": "quantità",
    "uom": "UoM",
    "uom_raw": "UoM",
    "unit_price": "prezzo",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


_CURRENCY_ALIASES: dict[str, tuple[str, ...]] = {
    "usd": ("usd", "$", "us$", "dollar", "dollars"),
    "eur": ("eur", "€", "euro", "euros"),
    "gbp": ("gbp", "£", "pound", "pounds"),
    "cad": ("cad", "c$", "ca$"),
    "chf": ("chf", "fr."),
}


def _numeric_variants(token: str) -> list[str]:
    """Varianti testuali di un numero (24.0 → 24, 24.00, $24)."""
    cleaned = token.replace(",", "").replace(" ", "")
    try:
        number = float(cleaned)
    except ValueError:
        return []
    variants = {f"{number:g}", f"{number:.1f}", f"{number:.2f}"}
    if number == int(number):
        variants.add(str(int(number)))
    return [item for item in variants if item]


def _token_in_haystack(token: str, haystack: str, *, numeric: bool) -> bool:
    """Match di token: numeri con confine di cifra, testo con confine di parola."""
    if not token:
        return False
    if numeric:
        pattern = rf"(?<!\d){re.escape(token)}(?!\d)"
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def snippet_in_document(snippet: str, haystack: str) -> bool:
    """True se lo snippet compare nel testo, con tolleranza su numeri e valuta."""
    needle = _normalize_text(snippet)
    if not needle:
        return True
    numeric_variants = _numeric_variants(needle)
    if numeric_variants:
        for variant in numeric_variants:
            if _token_in_haystack(variant, haystack, numeric=True):
                return True
            if f"${variant}" in haystack:
                return True
        return False
    if _token_in_haystack(needle, haystack, numeric=False):
        return True
    aliases = _CURRENCY_ALIASES.get(needle)
    if aliases:
        for alias in aliases:
            if alias == "$":
                if "$" in haystack:
                    return True
            elif _token_in_haystack(alias, haystack, numeric=False):
                return True
    return False


@rule("EXT-01", Severity.REVIEW)
def ext_01_low_confidence(ctx: RuleContext) -> list[Issue]:
    """Confidenza < 0,90 su un campo critico (PO, cliente, codice, qty, UoM, prezzo)."""
    issues: list[Issue] = []
    min_conf = float(threshold(ctx, "confidence_min", 0.90))
    evidence = ctx.evidence
    seen: set[str] = set()

    def maybe(pointer: str, label: str) -> None:
        if pointer in seen:
            return
        payload = evidence.get(pointer)
        if not isinstance(payload, dict):
            return
        confidence = payload.get("confidence")
        if confidence is None:
            return
        if float(confidence) < min_conf:
            seen.add(pointer)
            issues.append(
                issue(
                    "EXT-01",
                    Severity.REVIEW,
                    f"Campo critico '{label}' con confidenza {float(confidence):.0%} (< {min_conf:.0%})",
                    pointer,
                    suggestion="Verificare manualmente il valore estratto",
                    confidence=float(confidence),
                )
            )

    for pointer, label in CRITICAL_HEADER.items():
        maybe(pointer, label)
    for index, _line in enumerate(ctx.lines):
        for field, label in CRITICAL_LINE_FIELDS.items():
            maybe(f"/lines/{index}/{field}", label)
    return issues


@rule("EXT-02", Severity.REVIEW)
def ext_02_unanchored(ctx: RuleContext) -> list[Issue]:
    """Snippet dell'evidenza non trovato nel testo estratto (anti-allucinazione)."""
    if not ctx.document_text:
        return []
    haystack = _normalize_text(ctx.document_text)
    issues: list[Issue] = []
    for pointer, payload in ctx.evidence.items():
        if not isinstance(payload, dict):
            continue
        snippet = payload.get("snippet")
        if not snippet:
            continue
        if not snippet_in_document(str(snippet), haystack):
            issues.append(
                issue(
                    "EXT-02",
                    Severity.REVIEW,
                    f"Valore non ancorato: lo snippet di {pointer} non compare nel testo estratto",
                    pointer,
                    suggestion="Possibile allucinazione LLM: verificare sul documento",
                )
            )
    return issues


@rule("EXT-03", Severity.REVIEW)
def ext_03_invalid_schema(ctx: RuleContext) -> list[Issue]:
    """Output LLM non valido rispetto allo schema dopo 2 tentativi."""
    if ctx.llm_schema_valid:
        return []
    if ctx.llm_schema_attempts < 2:
        return []
    return [
        issue(
            "EXT-03",
            Severity.REVIEW,
            (
                "Output LLM non valido rispetto allo schema VOF "
                f"dopo {ctx.llm_schema_attempts} tentativi"
            ),
            "/",
            suggestion="Inserimento manuale in console di revisione",
        )
    ]
