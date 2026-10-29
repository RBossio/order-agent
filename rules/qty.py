"""QTY: Quantity validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("QTY-01", Severity.BLOCK)
def qty_01_missing_or_invalid(ctx: RuleContext) -> list[Issue]:
    """Verifica che ogni riga abbia una quantità valida."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        qty = line.get("quantity")

        if qty is None:
            issues.append(
                Issue(
                    rule_id="QTY-01",
                    severity=Severity.BLOCK,
                    message=f"Riga {i + 1}: quantità mancante",
                    json_pointer=f"/lines/{i}/quantity",
                    suggestion="Inserire la quantità ordinata",
                )
            )
        elif not isinstance(qty, (int, float)) or qty <= 0:
            issues.append(
                Issue(
                    rule_id="QTY-01",
                    severity=Severity.BLOCK,
                    message=f"Riga {i + 1}: quantità non valida ({qty})",
                    json_pointer=f"/lines/{i}/quantity",
                    suggestion="La quantità deve essere un numero positivo",
                )
            )

    return issues


@rule("QTY-02", Severity.REVIEW)
def qty_02_anomalous_quantity(ctx: RuleContext) -> list[Issue]:
    """Segnala quantità anomale rispetto alla media storica."""
    lines = ctx.order.get("lines", [])
    threshold = ctx.thresholds.get("qty_anomaly_multiple", 10)
    issues = []

    for i, line in enumerate(lines):
        qty = line.get("quantity", 0)
        item = line.get("item", {})
        avg_qty = item.get("avg_order_qty") or item.get("typical_quantity")

        if avg_qty and qty > 0:
            ratio = qty / avg_qty
            if ratio >= threshold:
                issues.append(
                    Issue(
                        rule_id="QTY-02",
                        severity=Severity.REVIEW,
                        message=f"Riga {i + 1}: quantità {qty} è {ratio:.1f}x la media ({avg_qty})",
                        json_pointer=f"/lines/{i}/quantity",
                        suggestion="Verificare la quantità con il cliente",
                        details={"quantity": qty, "average": avg_qty, "ratio": ratio},
                    )
                )

    return issues


@rule("QTY-03", Severity.INFO)
def qty_03_not_multiple(ctx: RuleContext) -> list[Issue]:
    """Segnala quantità non multipla del minimo d'ordine."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        qty = line.get("quantity", 0)
        item = line.get("item", {})
        moq = item.get("min_order_qty") or item.get("moq")
        multiple = item.get("order_multiple")

        if multiple and qty > 0 and qty % multiple != 0:
            issues.append(
                Issue(
                    rule_id="QTY-03",
                    severity=Severity.INFO,
                    message=f"Riga {i + 1}: quantità {qty} non è multiplo di {multiple}",
                    json_pointer=f"/lines/{i}/quantity",
                    suggestion=f"Arrotondare a multiplo di {multiple}",
                    details={"quantity": qty, "multiple": multiple},
                )
            )
        elif moq and qty > 0 and qty < moq:
            issues.append(
                Issue(
                    rule_id="QTY-03",
                    severity=Severity.INFO,
                    message=f"Riga {i + 1}: quantità {qty} inferiore al minimo d'ordine ({moq})",
                    json_pointer=f"/lines/{i}/quantity",
                    suggestion=f"La quantità minima ordinabile è {moq}",
                    details={"quantity": qty, "moq": moq},
                )
            )

    return issues
