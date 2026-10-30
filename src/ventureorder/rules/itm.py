"""Regole articolo (ITM-01 … ITM-07)."""

from __future__ import annotations

from ventureorder.rules.access import gtin_is_valid, issue, line_pointer, line_resolution
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import customer_of, product_of
from ventureorder.rules.registry import rule

UNRESOLVED_METHODS = frozenset({"UNRESOLVED"})
FUZZY_METHODS = frozenset({"FUZZY", "SEMANTIC"})
ITM01_SCORE_MIN = 0.75


@rule("ITM-01", Severity.BLOCK)
def itm_01_unresolved(ctx: RuleContext) -> list[Issue]:
    """Riga non risolta (manca resolution o score < 0,75)."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        resolution = line_resolution(line)
        method = str(resolution.get("method") or "")
        score = resolution.get("score")
        score_f = float(score) if isinstance(score, int | float) else None
        sku = resolution.get("sku")
        product_id = resolution.get("erp_product_id")
        unresolved = (
            not resolution
            or method in UNRESOLVED_METHODS
            or (sku is None and product_id is None)
            or (score_f is not None and score_f < ITM01_SCORE_MIN)
        )
        if unresolved:
            issues.append(
                issue(
                    "ITM-01",
                    Severity.BLOCK,
                    f"Riga {line.get('line_no', index + 1)}: articolo non risolto (score < 0,75)",
                    line_pointer(index, "resolution"),
                    suggestion="Associare lo SKU del distributore (xref, GTIN, MPN o manuale)",
                )
            )
    return issues


@rule("ITM-02", Severity.BLOCK)
def itm_02_not_saleable(ctx: RuleContext) -> list[Issue]:
    """Prodotto archiviato o non vendibile (``active`` / ``sale_ok``)."""
    issues: list[Issue] = []
    if ctx.reference_data is None:
        return issues
    for index, line in enumerate(ctx.lines):
        product = product_of(ctx.reference_data, line)
        if product is None:
            continue
        if not product.active or not product.sale_ok:
            issues.append(
                issue(
                    "ITM-02",
                    Severity.BLOCK,
                    (
                        f"Riga {line.get('line_no', index + 1)}: prodotto {product.sku} "
                        f"archiviato o non vendibile"
                    ),
                    line_pointer(index, "resolution"),
                    suggestion="Sostituire con un articolo attivo e sale_ok",
                    sku=product.sku,
                    active=product.active,
                    sale_ok=product.sale_ok,
                )
            )
    return issues


@rule("ITM-03", Severity.REVIEW)
def itm_03_fuzzy_or_semantic(ctx: RuleContext) -> list[Issue]:
    """Prodotto riconosciuto solo per similarità (FUZZY/SEMANTIC)."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        method = str(line_resolution(line).get("method") or "")
        if method in FUZZY_METHODS:
            issues.append(
                issue(
                    "ITM-03",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: articolo riconosciuto "
                        f"solo per similarità ({method})"
                    ),
                    line_pointer(index, "resolution"),
                    suggestion="Confermare lo SKU in revisione",
                    method=method,
                )
            )
    return issues


@rule("ITM-04", Severity.REVIEW)
def itm_04_identifier_conflict(ctx: RuleContext) -> list[Issue]:
    """Conflitto tra identificatori (xref, GTIN, MPN, codice venditore)."""
    issues: list[Issue] = []
    if ctx.reference_data is None:
        return issues
    customer = customer_of(ctx.reference_data, ctx.vof)
    customer_ref = customer.erp_partner_ref if customer else None
    for index, line in enumerate(ctx.lines):
        found: dict[str, str] = {}
        buyer_code = line.get("buyer_item_code")
        if customer_ref and buyer_code:
            xref = ctx.reference_data.get_xref(customer_ref, str(buyer_code))
            if xref:
                found["xref"] = xref.sku
        gtin = line.get("gtin")
        if gtin and gtin_is_valid(str(gtin)):
            product = ctx.reference_data.get_product_by_gtin(str(gtin))
            if product:
                found["gtin"] = product.sku
        mpn = line.get("manufacturer_part_number")
        if mpn:
            product = ctx.reference_data.get_product_by_mpn(str(mpn))
            if product:
                found["mpn"] = product.sku
        seller_code = line.get("seller_item_code")
        if seller_code:
            product = ctx.reference_data.get_product_by_sku(str(seller_code))
            if product:
                found["seller_code"] = product.sku
        skus = set(found.values())
        if len(skus) > 1:
            issues.append(
                issue(
                    "ITM-04",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: identificatori in conflitto "
                        f"({', '.join(sorted(skus))})"
                    ),
                    line_pointer(index),
                    suggestion="Verificare xref, GTIN e MPN: indicano prodotti diversi",
                    identifiers=found,
                )
            )
    return issues


@rule("ITM-05", Severity.WARN)
def itm_05_gtin_checksum(ctx: RuleContext) -> list[Issue]:
    """GTIN con cifra di controllo non valida: ignorato nel matching."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        gtin = line.get("gtin")
        if not gtin:
            continue
        if not gtin_is_valid(str(gtin)):
            issues.append(
                issue(
                    "ITM-05",
                    Severity.WARN,
                    (
                        f"Riga {line.get('line_no', index + 1)}: GTIN '{gtin}' "
                        "con cifra di controllo non valida (ignorato nel matching)"
                    ),
                    line_pointer(index, "gtin"),
                    suggestion="Correggere il GTIN o ignorarlo e usare xref/MPN",
                )
            )
    return issues


@rule("ITM-06", Severity.WARN)
def itm_06_duplicate_product(ctx: RuleContext) -> list[Issue]:
    """Stesso prodotto su più righe."""
    issues: list[Issue] = []
    seen: dict[str, int] = {}
    for index, line in enumerate(ctx.lines):
        resolution = line_resolution(line)
        key = str(resolution.get("sku") or resolution.get("erp_product_id") or "")
        if not key:
            continue
        if key in seen:
            issues.append(
                issue(
                    "ITM-06",
                    Severity.WARN,
                    (
                        f"Riga {line.get('line_no', index + 1)}: prodotto '{key}' già presente "
                        f"alla riga {seen[key]}"
                    ),
                    line_pointer(index),
                    suggestion="Consolidare le quantità o confermare che è voluto",
                )
            )
        else:
            line_no = line.get("line_no", index + 1)
            seen[key] = int(line_no) if isinstance(line_no, int) else index + 1
    return issues


@rule("ITM-07", Severity.REVIEW)
def itm_07_xref_candidate(ctx: RuleContext) -> list[Issue]:
    """Riga risolta con xref CANDIDATE (non ancora TRUSTED)."""
    issues: list[Issue] = []
    if ctx.reference_data is None:
        return issues
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None:
        return issues
    for index, line in enumerate(ctx.lines):
        method = str(line_resolution(line).get("method") or "")
        buyer_code = line.get("buyer_item_code")
        if method != "XREF" or not buyer_code:
            continue
        xref = ctx.reference_data.get_xref(customer.erp_partner_ref, str(buyer_code))
        if xref and xref.status.upper() == "CANDIDATE":
            issues.append(
                issue(
                    "ITM-07",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: xref CANDIDATE "
                        f"per codice cliente '{buyer_code}'"
                    ),
                    line_pointer(index, "buyer_item_code"),
                    suggestion="Promuovere l'xref a TRUSTED dopo conferma",
                    status=xref.status,
                )
            )
    return issues
