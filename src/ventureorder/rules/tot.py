"""Regole totali (TOT-01 … TOT-03)."""

from __future__ import annotations

from ventureorder.rules.access import as_float, issue, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.registry import rule


@rule("TOT-01", Severity.REVIEW)
def tot_01_total_mismatch(ctx: RuleContext) -> list[Issue]:
    """Somma righe + charges ≠ totale dichiarato oltre max(0,02; 0,1%)."""
    declared = as_float(
        ctx.totals.get("total_amount_declared") or ctx.totals.get("lines_amount_declared")
    )
    if declared is None:
        return []
    computed = 0.0
    for line in ctx.lines:
        amount = as_float(line.get("line_amount"))
        if amount is None:
            qty = as_float(line.get("quantity")) or 0.0
            price = as_float(line.get("unit_price")) or 0.0
            amount = qty * price
        computed += amount
    for charge in ctx.charges:
        computed += as_float(charge.get("amount")) or 0.0
    diff = abs(declared - computed)
    abs_tol = float(threshold(ctx, "total_abs_tol", 0.02))
    pct_tol = float(threshold(ctx, "total_pct_tol", 0.1))
    allowed = max(abs_tol, abs(declared) * pct_tol / 100)
    if diff > allowed:
        return [
            issue(
                "TOT-01",
                Severity.REVIEW,
                (
                    f"Totale dichiarato {declared:.2f} ≠ somma righe+spese {computed:.2f} "
                    f"(diff {diff:.2f})"
                ),
                "/totals/total_amount_declared",
                suggestion="Verificare estrazione dei totali o delle righe",
                declared=declared,
                computed=computed,
            )
        ]
    return []


@rule("TOT-02", Severity.BLOCK)
def tot_02_line_count(ctx: RuleContext) -> list[Issue]:
    """Numero di righe estratte ≠ dichiarato, o numerazione con salti."""
    issues: list[Issue] = []
    line_nos = [line.get("line_no") for line in ctx.lines if line.get("line_no") is not None]
    ints = [int(n) for n in line_nos if isinstance(n, int) or (isinstance(n, str) and str(n).isdigit())]
    if ints:
        expected = list(range(1, len(ints) + 1))
        if sorted(ints) != expected:
            issues.append(
                issue(
                    "TOT-02",
                    Severity.BLOCK,
                    f"Numerazione righe con salti: {sorted(ints)}",
                    "/lines",
                    suggestion="Possibili righe perse tra le pagine: ricontrollare l'estrazione",
                )
            )
    declared = ctx.declared_line_count
    extracted = len(ctx.lines)
    if declared is not None and declared != extracted:
        issues.append(
            issue(
                "TOT-02",
                Severity.BLOCK,
                f"Righe estratte {extracted} ≠ righe dichiarate {declared}",
                "/lines",
                suggestion="Confrontare con il numero di righe stampato sul documento",
                extracted=extracted,
                declared=declared,
            )
        )
    return issues


@rule("TOT-03", Severity.WARN)
def tot_03_unmapped_charges(ctx: RuleContext) -> list[Issue]:
    """Spese (trasporto, handling) senza prodotto servizio mappato in Odoo."""
    issues: list[Issue] = []
    mapped = ctx.config.get("charge_product_map") or {}
    for index, charge in enumerate(ctx.charges):
        charge_type = str(charge.get("type") or "OTHER")
        sku = None
        if ctx.reference_data is not None:
            sku = ctx.reference_data.get_charge_product(charge_type)
        if sku is None:
            sku = mapped.get(charge_type)
        if not sku:
            issues.append(
                issue(
                    "TOT-03",
                    Severity.WARN,
                    (
                        f"Spesa {charge_type} di {charge.get('amount', 0)} "
                        "senza prodotto servizio mappato in Odoo"
                    ),
                    f"/charges/{index}",
                    suggestion="Configurare config/rules.yaml charge_product_map o ignorare in posting",
                    charge_type=charge_type,
                )
            )
    return issues
