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
    """Quantità anomala: > 3× p99 storico, ×100 vs storico/confezione, o oltre il max."""
    issues: list[Issue] = []
    multiple = float(threshold(ctx, "qty_anomaly_multiple", 3.0))
    extreme = float(threshold(ctx, "qty_extreme_multiple", 100.0))
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
        product = product_of(ctx.reference_data, line)
        pack_count = None
        if product and isinstance(product.pack, dict) and product.pack.get("inner_count"):
            pack_count = as_float(product.pack.get("inner_count"))
        p99 = None
        if sku and customer is not None and ctx.reference_data is not None:
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
            continue
        if pack_count and pack_count > 0 and qty >= extreme * pack_count:
            issues.append(
                issue(
                    "QTY-02",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                        f"≥ {extreme:g}× la confezione ({pack_count:g})"
                    ),
                    line_pointer(index, "quantity"),
                    suggestion="Possibile zero in più: verificare la quantità con il cliente",
                    pack_count=pack_count,
                    multiple=extreme,
                )
            )
            continue
        if not p99 and qty >= extreme:
            issues.append(
                issue(
                    "QTY-02",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità {qty} "
                        f"≥ {extreme:g}× senza storico che la giustifichi"
                    ),
                    line_pointer(index, "quantity"),
                    suggestion="Verificare la quantità con il cliente",
                    multiple=extreme,
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
