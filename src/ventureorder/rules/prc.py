"""Regole prezzo (PRC-01 … PRC-04)."""

from __future__ import annotations

import re

from ventureorder.rules.access import as_float, issue, line_pointer, line_resolution, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import product_of
from ventureorder.rules.registry import rule

AMBIGUOUS_BASIS = re.compile(
    r"(per\s*c\b|per\s*m\b|/100\b|/c\b|/m\b|per\s*100\b)",
    re.IGNORECASE,
)


@rule("PRC-01", Severity.REVIEW)
def prc_01_vs_list_price(ctx: RuleContext) -> list[Issue]:
    """Prezzo PO diverso dal listino Odoo oltre ±2% (configurabile)."""
    issues: list[Issue] = []
    tolerance = float(threshold(ctx, "price_tolerance_pct", 2.0))
    for index, line in enumerate(ctx.lines):
        po_price = as_float(line.get("unit_price"))
        if po_price is None:
            continue
        resolution = line_resolution(line)
        expected = as_float(resolution.get("erp_list_price"))
        if expected is None and ctx.reference_data is not None:
            product = product_of(ctx.reference_data, line)
            if product is not None:
                expected = product.list_price
        if expected is None or expected <= 0:
            continue
        diff_pct = abs(po_price - expected) / expected * 100
        if diff_pct > tolerance:
            issues.append(
                issue(
                    "PRC-01",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: prezzo PO {po_price:.2f} "
                        f"diverso dal listino {expected:.2f} ({diff_pct:.1f}%, soglia ±{tolerance:g}%)"
                    ),
                    line_pointer(index, "unit_price"),
                    suggestion="Verificare il prezzo o accettare il prezzo PO in revisione",
                    po_price=po_price,
                    list_price=expected,
                    difference_pct=diff_pct,
                )
            )
    return issues


@rule("PRC-02", Severity.INFO)
def prc_02_missing_price(ctx: RuleContext) -> list[Issue]:
    """Prezzo assente sul PO: si usa il listino Odoo."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        if line.get("unit_price") is not None:
            continue
        list_price = as_float(line_resolution(line).get("erp_list_price"))
        if list_price is None and ctx.reference_data is not None:
            product = product_of(ctx.reference_data, line)
            if product is not None:
                list_price = product.list_price
        issues.append(
            issue(
                "PRC-02",
                Severity.INFO,
                (
                    f"Riga {line.get('line_no', index + 1)}: prezzo assente sul PO; "
                    f"si usa il listino Odoo"
                    + (f" ({list_price:.2f})" if list_price is not None else "")
                ),
                line_pointer(index, "unit_price"),
                suggestion="Il connettore non imposta price_unit: Odoo calcola dal listino",
                list_price=list_price,
            )
        )
    return issues


@rule("PRC-03", Severity.REVIEW)
def prc_03_line_amount(ctx: RuleContext) -> list[Issue]:
    """``qty × prezzo`` (con basis e sconto) ≠ ``line_amount`` oltre max(0,01; 0,5%)."""
    issues: list[Issue] = []
    abs_tol = float(threshold(ctx, "line_amount_abs_tol", 0.01))
    pct_tol = float(threshold(ctx, "line_amount_pct_tol", 0.5))
    for index, line in enumerate(ctx.lines):
        qty = as_float(line.get("quantity"))
        price = as_float(line.get("unit_price"))
        amount = as_float(line.get("line_amount"))
        if qty is None or price is None or amount is None:
            continue
        basis = as_float(line.get("price_basis_qty")) or 1.0
        if basis <= 0:
            basis = 1.0
        discount = as_float(line.get("discount_pct")) or 0.0
        expected = qty * price / basis * (1 - discount / 100)
        diff = abs(amount - expected)
        allowed = max(abs_tol, abs(expected) * pct_tol / 100)
        if diff > allowed:
            issues.append(
                issue(
                    "PRC-03",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: importo {amount:.2f} "
                        f"≠ {qty:g} × {price:.2f} (atteso {expected:.2f})"
                    ),
                    line_pointer(index, "line_amount"),
                    suggestion="Di solito indica un errore di estrazione",
                    expected=expected,
                    declared=amount,
                )
            )
    return issues


@rule("PRC-04", Severity.REVIEW)
def prc_04_ambiguous_basis(ctx: RuleContext) -> list[Issue]:
    """Base del prezzo ambigua ('per C', 'per M', '/100') non risolta."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        haystack = " ".join(
            str(part)
            for part in (
                line.get("uom_raw"),
                line.get("notes"),
                line.get("description"),
                line.get("price_uom"),
            )
            if part
        )
        basis = as_float(line.get("price_basis_qty"))
        if AMBIGUOUS_BASIS.search(haystack) and (basis is None or basis == 1.0):
            issues.append(
                issue(
                    "PRC-04",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: base del prezzo ambigua "
                        "non risolta (per C / per M /100)"
                    ),
                    line_pointer(index, "price_basis_qty"),
                    suggestion="Impostare price_basis_qty (100 o 1000) dopo verifica",
                )
            )
    return issues
