"""Regole quantità (QTY-01 … QTY-03)."""

from __future__ import annotations

from ventureorder.rules.access import as_float, issue, line_pointer, line_resolution, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import customer_of, product_of
from ventureorder.rules.registry import rule


@rule("QTY-01", Severity.BLOCK)
def qty_01_invalid(ctx: RuleContext) -> list[Issue]:
    """Quantità mancante, ≤ 0 o non numerica."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        raw = line.get("quantity")
        qty = as_float(raw)
        if raw is None or raw == "":
            issues.append(
                issue(
                    "QTY-01",
                    Severity.BLOCK,
                    f"Riga {line.get('line_no', index + 1)}: quantità mancante",
                    line_pointer(index, "quantity"),
                    suggestion="Inserire una quantità numerica positiva",
                )
            )
        elif qty is None or qty <= 0:
            issues.append(
                issue(
                    "QTY-01",
                    Severity.BLOCK,
                    f"Riga {line.get('line_no', index + 1)}: quantità non valida ({raw!r})",
                    line_pointer(index, "quantity"),
                    suggestion="La quantità deve essere un numero > 0",
                )
            )
    return issues


@rule("QTY-02", Severity.REVIEW)
def qty_02_anomalous(ctx: RuleContext) -> list[Issue]:
    """Quantità anomala: > 3× p99 storico o oltre il massimo di riga."""
    issues: list[Issue] = []
    multiple = float(threshold(ctx, "qty_anomaly_multiple", 3.0))
    max_qty = float(threshold(ctx, "max_line_qty", 10000))
    customer = customer_of(ctx.reference_data, ctx.vof)
    for index, line in enumerate(ctx.lines):
        qty = as_float(line.get("quantity"))
        if qty is None or qty <= 0:
            continue
        if qty > max_qty:
            issues.append(
                issue(
                    "QTY-02",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                        f"oltre il massimo configurato ({max_qty:g})"
                    ),
                    line_pointer(index, "quantity"),
                    suggestion="Verificare la quantità con il cliente",
                )
            )
            continue
        sku = str(line_resolution(line).get("sku") or "")
        if not sku or customer is None or ctx.reference_data is None:
            continue
        p99 = ctx.reference_data.get_qty_p99(customer.erp_partner_ref, sku)
        if p99 and qty > multiple * p99:
            issues.append(
                issue(
                    "QTY-02",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                        f"oltre {multiple:g}× il 99° percentile storico ({p99:g})"
                    ),
                    line_pointer(index, "quantity"),
                    suggestion="Verificare la quantità con il cliente",
                    p99=p99,
                    multiple=multiple,
                )
            )
    return issues


@rule("QTY-03", Severity.WARN)
def qty_03_multiple_or_moq(ctx: RuleContext) -> list[Issue]:
    """Quantità non multipla del multiplo di vendita, o sotto il minimo d'ordine."""
    issues: list[Issue] = []
    if ctx.reference_data is None:
        return issues
    for index, line in enumerate(ctx.lines):
        qty = as_float(line.get("quantity"))
        product = product_of(ctx.reference_data, line)
        if qty is None or qty <= 0 or product is None:
            continue
        moq = product.min_order_qty
        multiple = product.sale_multiple
        if moq is not None and qty < moq:
            issues.append(
                issue(
                    "QTY-03",
                    Severity.WARN,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                        f"sotto il minimo d'ordine ({moq})"
                    ),
                    line_pointer(index, "quantity"),
                    suggestion=f"Ordinare almeno {moq}",
                )
            )
        elif multiple is not None and multiple > 0:
            remainder = qty % multiple
            if remainder > 1e-9 and abs(remainder - multiple) > 1e-9:
                issues.append(
                    issue(
                        "QTY-03",
                        Severity.WARN,
                        (
                            f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                            f"non multipla di {multiple}"
                        ),
                        line_pointer(index, "quantity"),
                        suggestion=f"Arrotondare a un multiplo di {multiple}",
                    )
                )
    return issues
