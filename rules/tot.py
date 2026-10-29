"""Regole di validazione per i totali (TOT).

TOT-01: Somma importi riga + charges ≠ totale dichiarato (REVIEW)
TOT-02: Numero righe estratte ≠ numero dichiarato o numerazione con salti (BLOCK)
TOT-03: Charges presenti senza prodotto servizio mappato (WARN)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("TOT-01", Severity.REVIEW)
def rule_tot_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Somma degli importi di riga più charges ≠ totale dichiarato oltre tolleranza."""
    totals = vof.get("totals", {})
    
    total_declared = totals.get("total_amount_declared")
    lines_declared = totals.get("lines_amount_declared")
    
    declared = total_declared if total_declared is not None else lines_declared
    if declared is None:
        return []
    
    lines = vof.get("lines", [])
    computed_lines = sum(
        line.get("line_amount", 0) or 0
        for line in lines
    )
    
    charges = vof.get("charges", [])
    computed_charges = sum(
        charge.get("amount", 0) or 0
        for charge in charges
    )
    
    computed_total = computed_lines + computed_charges
    
    tolerance_pct = ctx.get_threshold("total_tolerance_pct", 0.1)
    tolerance_abs = ctx.get_threshold("total_tolerance_abs", 0.02)
    
    diff = abs(computed_total - declared)
    threshold = max(tolerance_abs, declared * tolerance_pct / 100)
    
    if diff > threshold:
        return [Issue(
            code="TOT-01",
            severity=Severity.REVIEW,
            message=f"Totale calcolato ({computed_total:.2f}) ≠ totale dichiarato ({declared:.2f}). Differenza: {diff:.2f}.",
            path="/totals",
            suggestion="Verificare gli importi delle righe e le spese accessorie.",
            details={
                "computed_lines": round(computed_lines, 2),
                "computed_charges": round(computed_charges, 2),
                "computed_total": round(computed_total, 2),
                "declared_total": declared,
                "diff": round(diff, 2),
            },
        )]
    
    return []


@rule("TOT-02", Severity.BLOCK)
def rule_tot_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Numero di righe estratte ≠ numero dichiarato o numerazione con salti."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    if not lines:
        return [Issue(
            code="TOT-02",
            severity=Severity.BLOCK,
            message="Nessuna riga estratta dall'ordine.",
            path="/lines",
            suggestion="Verificare l'estrazione del documento.",
        )]
    
    totals = vof.get("totals", {})
    declared_count = totals.get("lines_count")
    
    if declared_count is not None and len(lines) != declared_count:
        issues.append(Issue(
            code="TOT-02",
            severity=Severity.BLOCK,
            message=f"Numero righe estratte ({len(lines)}) ≠ numero dichiarato ({declared_count}). Possibili righe mancanti.",
            path="/lines",
            suggestion="Verificare che tutte le righe siano state estratte correttamente.",
            details={
                "extracted": len(lines),
                "declared": declared_count,
            },
        ))
    
    line_numbers = [line.get("line_no") for line in lines if line.get("line_no")]
    if line_numbers:
        expected_numbers = set(range(1, max(line_numbers) + 1))
        actual_numbers = set(line_numbers)
        missing = expected_numbers - actual_numbers
        
        if missing:
            issues.append(Issue(
                code="TOT-02",
                severity=Severity.BLOCK,
                message=f"Numerazione righe con salti: mancano le righe {sorted(missing)}.",
                path="/lines",
                suggestion="Potrebbero esserci righe non estratte, tipicamente tra le pagine.",
                details={
                    "missing_line_numbers": sorted(missing),
                    "extracted_line_numbers": sorted(actual_numbers),
                },
            ))
        
        duplicates = [n for n in actual_numbers if line_numbers.count(n) > 1]
        if duplicates:
            issues.append(Issue(
                code="TOT-02",
                severity=Severity.REVIEW,
                message=f"Numeri di riga duplicati: {duplicates}.",
                path="/lines",
                suggestion="Verificare se sono righe separate o duplicazioni nell'estrazione.",
                details={"duplicate_line_numbers": duplicates},
            ))
    
    return issues


@rule("TOT-03", Severity.WARN)
def rule_tot_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Charges presenti (trasporto, handling) senza prodotto servizio mappato in Odoo."""
    issues: list[Issue] = []
    charges = vof.get("charges", [])
    
    charges_config = ctx.config.get("charges_products", {})
    
    for idx, charge in enumerate(charges):
        charge_type = charge.get("type")
        amount = charge.get("amount", 0)
        
        if not charge_type or amount == 0:
            continue
        
        product_sku = charges_config.get(charge_type)
        
        if not product_sku:
            issues.append(Issue(
                code="TOT-03",
                severity=Severity.WARN,
                message=f"Spesa accessoria '{charge_type}' ({amount:.2f}) senza prodotto servizio mappato.",
                path=f"/charges/{idx}",
                suggestion="Configurare un prodotto servizio in Odoo per questo tipo di spesa.",
                details={
                    "charge_type": charge_type,
                    "amount": amount,
                },
            ))
    
    return issues
