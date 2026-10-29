"""Regole di validazione per le quantità (QTY).

QTY-01: Quantità mancante, ≤ 0 o non numerica (BLOCK)
QTY-02: Quantità anomala (oltre 3x il 99° percentile storico) (REVIEW)
QTY-03: Quantità non multipla del multiplo di vendita o sotto il minimo (WARN)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("QTY-01", Severity.BLOCK)
def rule_qty_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Quantità mancante, ≤ 0 o non numerica."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        quantity = line.get("quantity")
        line_no = line.get("line_no", idx + 1)
        
        if quantity is None:
            issues.append(Issue(
                code="QTY-01",
                severity=Severity.BLOCK,
                message=f"Riga {line_no}: quantità mancante.",
                path=f"/lines/{idx}/quantity",
                suggestion="Inserire la quantità ordinata.",
            ))
        elif not isinstance(quantity, (int, float)):
            issues.append(Issue(
                code="QTY-01",
                severity=Severity.BLOCK,
                message=f"Riga {line_no}: quantità '{quantity}' non numerica.",
                path=f"/lines/{idx}/quantity",
                suggestion="Inserire un valore numerico valido per la quantità.",
            ))
        elif quantity <= 0:
            issues.append(Issue(
                code="QTY-01",
                severity=Severity.BLOCK,
                message=f"Riga {line_no}: quantità {quantity} non valida (deve essere > 0).",
                path=f"/lines/{idx}/quantity",
                suggestion="Inserire una quantità positiva.",
            ))
    
    return issues


@rule("QTY-02", Severity.REVIEW)
def rule_qty_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Quantità anomala: oltre 3x il 99° percentile storico del cliente per quel prodotto."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    anomaly_factor = ctx.get_threshold("quantity_anomaly_factor", 3.0)
    
    if not ctx.reference_data:
        return issues
    
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    tenant_id = vof.get("tenant_id", ctx.tenant_id)
    
    if not partner_id:
        return issues
    
    for idx, line in enumerate(lines):
        quantity = line.get("quantity")
        if not quantity or not isinstance(quantity, (int, float)):
            continue
        
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        product_id = resolution.get("erp_product_id")
        if not product_id:
            continue
        
        stats = ctx.reference_data.get_product_history_stats(
            tenant_id, partner_id, product_id
        )
        
        if stats:
            p99 = stats.get("quantity_p99")
            if p99 and quantity > p99 * anomaly_factor:
                issues.append(Issue(
                    code="QTY-02",
                    severity=Severity.REVIEW,
                    message=f"Riga {line.get('line_no', idx+1)}: quantità {quantity} anomala (storico P99: {p99}, soglia: {p99 * anomaly_factor:.0f}).",
                    path=f"/lines/{idx}/quantity",
                    suggestion="Verificare che la quantità ordinata sia corretta.",
                    details={
                        "quantity": quantity,
                        "p99": p99,
                        "threshold": p99 * anomaly_factor,
                        "factor": anomaly_factor,
                    },
                ))
            
            max_qty = stats.get("max_quantity")
            if max_qty and quantity > max_qty * anomaly_factor and (not p99 or quantity <= p99 * anomaly_factor):
                issues.append(Issue(
                    code="QTY-02",
                    severity=Severity.REVIEW,
                    message=f"Riga {line.get('line_no', idx+1)}: quantità {quantity} oltre {anomaly_factor}x il massimo storico ({max_qty}).",
                    path=f"/lines/{idx}/quantity",
                    suggestion="Verificare che la quantità ordinata sia corretta.",
                    details={
                        "quantity": quantity,
                        "max_historical": max_qty,
                    },
                ))
    
    return issues


@rule("QTY-03", Severity.WARN)
def rule_qty_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Quantità non multipla del multiplo di vendita, o sotto il minimo d'ordine."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    if not ctx.reference_data:
        return issues
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        erp_qty = resolution.get("erp_quantity")
        if not erp_qty:
            continue
        
        product_id = resolution.get("erp_product_id")
        if not product_id:
            continue
        
        product = ctx.reference_data.get_product_by_id(product_id)
        if not product:
            continue
        
        min_qty = product.get("sale_min_qty")
        if min_qty and erp_qty < min_qty:
            issues.append(Issue(
                code="QTY-03",
                severity=Severity.WARN,
                message=f"Riga {line.get('line_no', idx+1)}: quantità {erp_qty} sotto il minimo d'ordine ({min_qty}).",
                path=f"/lines/{idx}/resolution/erp_quantity",
                suggestion=f"La quantità minima ordinabile è {min_qty}.",
                details={
                    "quantity": erp_qty,
                    "min_qty": min_qty,
                },
            ))
        
        multiple = product.get("sale_multiple_qty")
        if multiple and multiple > 1 and erp_qty % multiple != 0:
            issues.append(Issue(
                code="QTY-03",
                severity=Severity.WARN,
                message=f"Riga {line.get('line_no', idx+1)}: quantità {erp_qty} non multipla di {multiple}.",
                path=f"/lines/{idx}/resolution/erp_quantity",
                suggestion=f"La quantità deve essere un multiplo di {multiple}.",
                details={
                    "quantity": erp_qty,
                    "multiple": multiple,
                },
            ))
    
    return issues
