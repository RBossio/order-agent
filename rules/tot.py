"""TOT: Total validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("TOT-01", Severity.REVIEW)
def tot_01_total_mismatch(ctx: RuleContext) -> list[Issue]:
    """Verifica che il totale corrisponda alla somma delle righe."""
    lines = ctx.order.get("lines", [])
    stated_total = ctx.order.get("total") or ctx.order.get("order_total")
    tolerance_pct = ctx.thresholds.get("total_tolerance_pct", 0.01)

    if stated_total is None:
        return []

    calculated_total = 0.0
    for line in lines:
        amount = line.get("line_amount") or line.get("amount")
        if amount is not None:
            calculated_total += amount
        else:
            qty = line.get("quantity", 0)
            price = line.get("unit_price") or line.get("price", 0)
            calculated_total += qty * price

    charges = ctx.order.get("charges", [])
    for charge in charges:
        calculated_total += charge.get("amount", 0)

    diff = abs(stated_total - calculated_total)
    if stated_total > 0:
        diff_pct = (diff / stated_total) * 100
    else:
        diff_pct = 100 if diff > 0 else 0

    if diff > 0.01 and diff_pct > tolerance_pct:
        return [
            Issue(
                rule_id="TOT-01",
                severity=Severity.REVIEW,
                message=f"Totale dichiarato {stated_total:.2f} non corrisponde al calcolato {calculated_total:.2f} (diff: {diff:.2f})",
                json_pointer="/total",
                suggestion="Verificare il totale dell'ordine",
                details={
                    "stated_total": stated_total,
                    "calculated_total": calculated_total,
                    "difference": diff,
                    "difference_pct": diff_pct,
                },
            )
        ]

    return []


@rule("TOT-02", Severity.WARN)
def tot_02_missing_line_amounts(ctx: RuleContext) -> list[Issue]:
    """Segnala quando mancano gli importi delle righe."""
    lines = ctx.order.get("lines", [])
    missing_count = 0

    for line in lines:
        amount = line.get("line_amount") or line.get("amount")
        qty = line.get("quantity")
        price = line.get("unit_price") or line.get("price")

        if amount is None and (qty is None or price is None):
            missing_count += 1

    if missing_count > 0:
        return [
            Issue(
                rule_id="TOT-02",
                severity=Severity.WARN,
                message=f"{missing_count} riga/e senza importo calcolabile",
                json_pointer="/lines",
                suggestion="Inserire importo o quantità e prezzo per ogni riga",
            )
        ]

    return []


@rule("TOT-03", Severity.INFO)
def tot_03_unmapped_charges(ctx: RuleContext) -> list[Issue]:
    """Segnala spese/oneri non mappati."""
    charges = ctx.order.get("charges", [])
    issues = []

    for i, charge in enumerate(charges):
        charge_type = charge.get("type") or charge.get("charge_type")
        mapped = charge.get("mapped", True)

        if not mapped or charge_type in ("UNKNOWN", "OTHER"):
            issues.append(
                Issue(
                    rule_id="TOT-03",
                    severity=Severity.INFO,
                    message=f"Spesa non mappata: {charge.get('description', charge_type)} ({charge.get('amount', 0):.2f})",
                    json_pointer=f"/charges/{i}",
                    suggestion="Classificare la spesa (trasporto, imballo, etc.)",
                )
            )

    return issues
