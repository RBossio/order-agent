"""Regole di validazione per i prezzi (PRC).

PRC-01: Prezzo PO diverso dal prezzo Odoo oltre ±2% (REVIEW)
PRC-02: Prezzo assente sul PO (INFO)
PRC-03: quantity × unit_price ≠ line_amount (REVIEW)
PRC-04: Base del prezzo ambigua non risolta (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("PRC-01", Severity.REVIEW)
def rule_prc_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Prezzo PO diverso dal prezzo Odoo (listino cliente) oltre ±2%."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    tolerance_pct = ctx.get_threshold("price_tolerance_pct", 2.0)
    
    for idx, line in enumerate(lines):
        unit_price = line.get("unit_price")
        if unit_price is None:
            continue
        
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        erp_price = resolution.get("erp_list_price")
        if erp_price is None:
            continue
        
        if erp_price == 0:
            if unit_price != 0:
                issues.append(Issue(
                    code="PRC-01",
                    severity=Severity.REVIEW,
                    message=f"Riga {line.get('line_no', idx+1)}: prezzo PO {unit_price:.2f} ma listino Odoo è 0.",
                    path=f"/lines/{idx}/unit_price",
                    suggestion="Il prodotto non ha un prezzo di listino. Verificare.",
                ))
            continue
        
        diff_pct = abs(unit_price - erp_price) / erp_price * 100
        
        if diff_pct > tolerance_pct:
            direction = "superiore" if unit_price > erp_price else "inferiore"
            issues.append(Issue(
                code="PRC-01",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: prezzo PO {unit_price:.2f} {direction} al listino Odoo {erp_price:.2f} ({diff_pct:+.1f}%, soglia ±{tolerance_pct}%).",
                path=f"/lines/{idx}/unit_price",
                suggestion="Verificare il prezzo con il cliente. Decidere se usare il prezzo del PO o il listino.",
                details={
                    "po_price": unit_price,
                    "erp_price": erp_price,
                    "diff_pct": round(diff_pct, 1),
                    "tolerance_pct": tolerance_pct,
                },
            ))
    
    return issues


@rule("PRC-02", Severity.INFO)
def rule_prc_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Prezzo assente sul PO: si usa il listino Odoo."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        unit_price = line.get("unit_price")
        
        if unit_price is None:
            resolution = line.get("resolution")
            erp_price = resolution.get("erp_list_price") if resolution else None
            
            msg = f"Riga {line.get('line_no', idx+1)}: prezzo non indicato sul PO."
            if erp_price:
                msg += f" Verrà usato il listino Odoo ({erp_price:.2f})."
            
            issues.append(Issue(
                code="PRC-02",
                severity=Severity.INFO,
                message=msg,
                path=f"/lines/{idx}/unit_price",
                details={"erp_price": erp_price},
            ))
    
    return issues


@rule("PRC-03", Severity.REVIEW)
def rule_prc_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """quantity × unit_price (con price_basis_qty e discount) ≠ line_amount oltre tolleranza."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    tolerance_pct = ctx.get_threshold("line_amount_tolerance_pct", 0.5)
    tolerance_abs = ctx.get_threshold("line_amount_tolerance_abs", 0.01)
    
    for idx, line in enumerate(lines):
        quantity = line.get("quantity")
        unit_price = line.get("unit_price")
        line_amount = line.get("line_amount")
        
        if quantity is None or unit_price is None or line_amount is None:
            continue
        
        price_basis_qty = line.get("price_basis_qty", 1) or 1
        discount_pct = line.get("discount_pct", 0) or 0
        
        effective_price = unit_price / price_basis_qty
        
        computed_amount = quantity * effective_price * (1 - discount_pct / 100)
        
        diff = abs(computed_amount - line_amount)
        threshold = max(tolerance_abs, line_amount * tolerance_pct / 100)
        
        if diff > threshold:
            issues.append(Issue(
                code="PRC-03",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: importo calcolato ({computed_amount:.2f}) ≠ importo dichiarato ({line_amount:.2f}). Differenza: {diff:.2f}.",
                path=f"/lines/{idx}/line_amount",
                suggestion="Verificare i dati estratti: quantità, prezzo unitario, base prezzo o sconto potrebbero essere errati.",
                details={
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "price_basis_qty": price_basis_qty,
                    "discount_pct": discount_pct,
                    "computed": round(computed_amount, 2),
                    "declared": line_amount,
                    "diff": round(diff, 2),
                },
            ))
    
    return issues


@rule("PRC-04", Severity.REVIEW)
def rule_prc_04(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Base del prezzo ambigua ('per C', 'per M', '/100') non risolta."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    ambiguous_patterns = ["per c", "per m", "/100", "/1000", "per 100", "per 1000", "per hundred", "per thousand"]
    
    for idx, line in enumerate(lines):
        price_basis_qty = line.get("price_basis_qty")
        unit_price = line.get("unit_price")
        
        if unit_price is None:
            continue
        
        description = (line.get("description") or "").lower()
        uom_raw = (line.get("uom_raw") or "").lower()
        
        has_ambiguous = any(p in description or p in uom_raw for p in ambiguous_patterns)
        
        if has_ambiguous and price_basis_qty in (None, 1):
            issues.append(Issue(
                code="PRC-04",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: possibile prezzo 'per 100' o 'per M' non risolto.",
                path=f"/lines/{idx}/price_basis_qty",
                suggestion="Verificare se il prezzo è per unità singola o per multipli (100, 1000).",
                details={
                    "description": line.get("description"),
                    "uom_raw": line.get("uom_raw"),
                    "price_basis_qty": price_basis_qty,
                },
            ))
    
    return issues
