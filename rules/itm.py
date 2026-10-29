"""Regole di validazione per gli articoli (ITM).

ITM-01: Riga non risolta (score < 0.75) (BLOCK)
ITM-02: Prodotto archiviato o non vendibile (BLOCK)
ITM-03: Prodotto riconosciuto solo per similarità (FUZZY/SEMANTIC) (REVIEW)
ITM-04: Conflitto tra identificatori (REVIEW)
ITM-05: GTIN con cifra di controllo non valida (WARN)
ITM-06: Stesso prodotto su più righe (WARN)
ITM-07: Riga risolta con xref CANDIDATE (non TRUSTED) (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


def _validate_gtin_checksum(gtin: str) -> bool:
    """Valida la cifra di controllo GS1 del GTIN."""
    if not gtin or not gtin.isdigit():
        return False
    
    if len(gtin) not in (8, 12, 13, 14):
        return False
    
    gtin = gtin.zfill(14)
    
    total = 0
    for i, digit in enumerate(gtin[:-1]):
        weight = 3 if i % 2 == 0 else 1
        total += int(digit) * weight
    
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(gtin[-1])


@rule("ITM-01", Severity.BLOCK)
def rule_itm_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Riga non risolta (score < 0.75)."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    fuzzy_min = ctx.get_threshold("fuzzy_match_min", 0.75)
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        
        if not resolution:
            issues.append(Issue(
                code="ITM-01",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: articolo non risolto. Nessuna corrispondenza trovata.",
                path=f"/lines/{idx}/resolution",
                suggestion="Cercare manualmente l'articolo nel catalogo e assegnarlo.",
                details={
                    "line_no": line.get("line_no"),
                    "description": line.get("description", "")[:100],
                    "buyer_item_code": line.get("buyer_item_code"),
                },
            ))
            continue
        
        method = resolution.get("method")
        score = resolution.get("score", 0)
        
        if method == "UNRESOLVED" or score < fuzzy_min:
            issues.append(Issue(
                code="ITM-01",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: articolo non identificabile (score {score:.2f} < {fuzzy_min}).",
                path=f"/lines/{idx}/resolution",
                suggestion="Cercare manualmente l'articolo nel catalogo.",
                details={
                    "line_no": line.get("line_no"),
                    "score": score,
                    "method": method,
                    "candidates": resolution.get("candidates", [])[:3],
                },
            ))
    
    return issues


@rule("ITM-02", Severity.BLOCK)
def rule_itm_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Prodotto archiviato o non vendibile."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    if not ctx.reference_data:
        return issues
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        product_id = resolution.get("erp_product_id")
        sku = resolution.get("sku")
        
        if product_id:
            product = ctx.reference_data.get_product_by_id(product_id)
        elif sku:
            product = ctx.reference_data.get_product_by_sku(sku)
        else:
            continue
        
        if not product:
            continue
        
        if not product.get("active", True):
            issues.append(Issue(
                code="ITM-02",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: prodotto '{sku}' archiviato.",
                path=f"/lines/{idx}/resolution",
                suggestion="Selezionare un prodotto attivo alternativo.",
                details={"sku": sku, "product_id": product_id},
            ))
        elif not product.get("sale_ok", True):
            issues.append(Issue(
                code="ITM-02",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: prodotto '{sku}' non vendibile.",
                path=f"/lines/{idx}/resolution",
                suggestion="Il prodotto non è abilitato per la vendita. Selezionare un'alternativa.",
                details={"sku": sku, "product_id": product_id},
            ))
    
    return issues


@rule("ITM-03", Severity.REVIEW)
def rule_itm_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Prodotto riconosciuto solo per similarità (FUZZY/SEMANTIC)."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        method = resolution.get("method")
        score = resolution.get("score", 0)
        
        if method in ("FUZZY", "SEMANTIC"):
            candidates = resolution.get("candidates", [])
            buyer_code = line.get("buyer_item_code", "N/A")
            
            msg = f"Riga {line.get('line_no', idx+1)}: articolo '{resolution.get('sku')}' riconosciuto per similarità (score {score:.2f})."
            if buyer_code and buyer_code != "N/A":
                msg += f" Codice cliente '{buyer_code}' non trovato nel cross-reference."
            
            issues.append(Issue(
                code="ITM-03",
                severity=Severity.REVIEW,
                message=msg,
                path=f"/lines/{idx}/resolution",
                suggestion="Verificare che il prodotto selezionato sia corretto.",
                details={
                    "method": method,
                    "score": score,
                    "candidates_count": len(candidates),
                    "buyer_item_code": buyer_code,
                },
            ))
    
    return issues


@rule("ITM-04", Severity.REVIEW)
def rule_itm_04(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Conflitto tra identificatori (xref, GTIN e MPN indicano prodotti diversi)."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    if not ctx.reference_data:
        return issues
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        resolved_sku = resolution.get("sku")
        gtin = line.get("gtin")
        
        conflicts: list[str] = []
        
        if gtin and _validate_gtin_checksum(gtin):
            product_by_gtin = ctx.reference_data.get_product_by_sku(gtin)
            if product_by_gtin and product_by_gtin.get("sku") != resolved_sku:
                conflicts.append(f"GTIN {gtin} → {product_by_gtin.get('sku')}")
        
        if conflicts:
            issues.append(Issue(
                code="ITM-04",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: conflitto tra identificatori. Risolto: {resolved_sku}. Alternativo: {', '.join(conflicts)}.",
                path=f"/lines/{idx}/resolution",
                suggestion="Verificare quale prodotto è quello corretto.",
                details={
                    "resolved_sku": resolved_sku,
                    "conflicts": conflicts,
                },
            ))
    
    return issues


@rule("ITM-05", Severity.WARN)
def rule_itm_05(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """GTIN con cifra di controllo non valida."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        gtin = line.get("gtin")
        
        if gtin and not _validate_gtin_checksum(gtin):
            issues.append(Issue(
                code="ITM-05",
                severity=Severity.WARN,
                message=f"Riga {line.get('line_no', idx+1)}: GTIN '{gtin}' con cifra di controllo non valida. Ignorato nel matching.",
                path=f"/lines/{idx}/gtin",
                suggestion="Il GTIN è stato ignorato nella ricerca perché non valido.",
                details={"gtin": gtin},
            ))
    
    return issues


@rule("ITM-06", Severity.WARN)
def rule_itm_06(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Stesso prodotto su più righe."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    sku_to_lines: dict[str, list[int]] = {}
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        sku = resolution.get("sku")
        if sku:
            line_no = line.get("line_no", idx + 1)
            if sku not in sku_to_lines:
                sku_to_lines[sku] = []
            sku_to_lines[sku].append(line_no)
    
    for sku, line_numbers in sku_to_lines.items():
        if len(line_numbers) > 1:
            issues.append(Issue(
                code="ITM-06",
                severity=Severity.WARN,
                message=f"Prodotto '{sku}' presente su più righe: {', '.join(map(str, line_numbers))}.",
                path="/lines",
                suggestion="Verificare se le righe duplicate sono intenzionali o se vanno consolidate.",
                details={"sku": sku, "line_numbers": line_numbers},
            ))
    
    return issues


@rule("ITM-07", Severity.REVIEW)
def rule_itm_07(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Riga risolta con xref CANDIDATE (non ancora TRUSTED)."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        method = resolution.get("method")
        
        if method == "XREF" and resolution.get("score", 1.0) < 1.0:
            sku = resolution.get("sku")
            buyer_code = line.get("buyer_item_code", "")
            
            issues.append(Issue(
                code="ITM-07",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: cross-reference '{buyer_code}' → '{sku}' non ancora confermato (CANDIDATE).",
                path=f"/lines/{idx}/resolution",
                suggestion="Confermare l'associazione per renderla definitiva (TRUSTED).",
                details={
                    "buyer_item_code": buyer_code,
                    "sku": sku,
                    "score": resolution.get("score"),
                },
            ))
    
    return issues
