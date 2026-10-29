"""Regole di validazione per le unità di misura (UOM).

UOM-01: UoM non riconosciuta (REVIEW)
UOM-02: Nessuna conversione possibile tra UoM cliente e unità vendibili (BLOCK)
UOM-03: Conversione applicata (INFO)
UOM-04: Confezione sul documento diversa da quella di catalogo (REVIEW)
UOM-05: Quantità convertita non intera per unità indivisibile (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule

KNOWN_UOMS = {
    "EA", "C62", "H87", "BX", "CS", "PK", "CT", "DZN", "DZ",
    "GLL", "GAL", "OZA", "LTR", "KGM", "LBR", "RO", "PR", "BG", "DR",
    "EACH", "UNIT", "PC", "PCS", "BOX", "CASE", "PACK", "DOZEN",
}

INDIVISIBLE_UOMS = {"EA", "C62", "H87", "BX", "CS", "PK", "CT", "PR", "BG", "RO", "DR"}


@rule("UOM-01", Severity.REVIEW)
def rule_uom_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """UoM non riconosciuta."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        uom_raw = line.get("uom_raw", "")
        uom = line.get("uom")
        
        if uom_raw and not uom:
            normalized = uom_raw.upper().strip()
            if normalized not in KNOWN_UOMS:
                issues.append(Issue(
                    code="UOM-01",
                    severity=Severity.REVIEW,
                    message=f"Riga {line.get('line_no', idx+1)}: unità di misura '{uom_raw}' non riconosciuta.",
                    path=f"/lines/{idx}/uom",
                    suggestion="Selezionare manualmente l'unità di misura corretta.",
                    details={"uom_raw": uom_raw},
                ))
    
    return issues


@rule("UOM-02", Severity.BLOCK)
def rule_uom_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Nessuna conversione possibile tra UoM cliente e unità vendibili del prodotto."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        erp_uom = resolution.get("erp_uom")
        conversion_factor = resolution.get("conversion_factor")
        method = resolution.get("method")
        
        if method not in ("UNRESOLVED", None) and not erp_uom and not conversion_factor:
            uom_raw = line.get("uom_raw", "")
            sku = resolution.get("sku", "")
            
            issues.append(Issue(
                code="UOM-02",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: impossibile convertire '{uom_raw}' nell'unità di vendita del prodotto '{sku}'.",
                path=f"/lines/{idx}/resolution/erp_uom",
                suggestion="Verificare le unità di vendita disponibili per il prodotto.",
                details={
                    "uom_raw": uom_raw,
                    "sku": sku,
                },
            ))
    
    return issues


@rule("UOM-03", Severity.INFO)
def rule_uom_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Conversione UoM applicata (es. CS → BX, DZ → EA)."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        uom = line.get("uom")
        erp_uom = resolution.get("erp_uom")
        conversion_factor = resolution.get("conversion_factor")
        
        if erp_uom and uom and erp_uom != uom and conversion_factor and conversion_factor != 1:
            qty = line.get("quantity", 0)
            erp_qty = resolution.get("erp_quantity", qty)
            
            issues.append(Issue(
                code="UOM-03",
                severity=Severity.INFO,
                message=f"Riga {line.get('line_no', idx+1)}: conversione applicata {qty} {uom} = {erp_qty} {erp_uom} (fattore {conversion_factor}).",
                path=f"/lines/{idx}/resolution",
                details={
                    "original_qty": qty,
                    "original_uom": uom,
                    "erp_qty": erp_qty,
                    "erp_uom": erp_uom,
                    "factor": conversion_factor,
                },
            ))
    
    return issues


@rule("UOM-04", Severity.REVIEW)
def rule_uom_04(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Confezione sul documento diversa da quella di catalogo."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    if not ctx.reference_data:
        return issues
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        pack = line.get("pack")
        if not pack:
            continue
        
        doc_inner_count = pack.get("inner_count")
        if not doc_inner_count:
            continue
        
        product_id = resolution.get("erp_product_id")
        if product_id:
            product = ctx.reference_data.get_product_by_id(product_id)
            if product:
                catalog_pack = product.get("pack", {})
                catalog_inner_count = catalog_pack.get("inner_count")
                
                if catalog_inner_count and doc_inner_count != catalog_inner_count:
                    issues.append(Issue(
                        code="UOM-04",
                        severity=Severity.REVIEW,
                        message=f"Riga {line.get('line_no', idx+1)}: confezione documento ({doc_inner_count}/pack) diversa da catalogo ({catalog_inner_count}/pack).",
                        path=f"/lines/{idx}/pack",
                        suggestion="Verificare se il cliente intende una confezione diversa da quella standard.",
                        details={
                            "doc_pack": pack.get("raw"),
                            "doc_inner_count": doc_inner_count,
                            "catalog_inner_count": catalog_inner_count,
                        },
                    ))
    
    return issues


@rule("UOM-05", Severity.REVIEW)
def rule_uom_05(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Quantità convertita non intera per un'unità indivisibile."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        erp_qty = resolution.get("erp_quantity")
        erp_uom = resolution.get("erp_uom")
        
        if erp_qty is None or erp_uom is None:
            continue
        
        if erp_uom in INDIVISIBLE_UOMS and erp_qty != int(erp_qty):
            issues.append(Issue(
                code="UOM-05",
                severity=Severity.REVIEW,
                message=f"Riga {line.get('line_no', idx+1)}: quantità convertita {erp_qty} {erp_uom} non intera per unità indivisibile.",
                path=f"/lines/{idx}/resolution/erp_quantity",
                suggestion="Arrotondare la quantità al numero intero più vicino.",
                details={
                    "erp_quantity": erp_qty,
                    "erp_uom": erp_uom,
                },
            ))
    
    return issues
