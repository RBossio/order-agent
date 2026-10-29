"""Regole di validazione per l'export (EXP).

EXP-01: Export Peppol: manca EndpointID (GLN/schemeID) per buyer o seller (BLOCK per Peppol)
EXP-02: Export X12/EDIFACT: campo oltre la lunghezza massima del segmento (WARN)
EXP-03: UoM senza corrispondenza nella codelist del formato di destinazione (BLOCK per quel formato)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule

X12_UOM_CODES = {
    "EA", "BX", "CA", "PK", "CT", "DZ", "GA", "FO", "LT", "KG", "LB",
    "RL", "PR", "BG", "DR", "PC", "UN",
}

EDIFACT_UOM_CODES = {
    "EA", "C62", "H87", "BX", "CS", "PK", "CT", "DZN", "GLL", "OZA",
    "LTR", "KGM", "LBR", "RO", "PR", "BG", "DR",
}

PEPPOL_UOM_CODES = {
    "C62", "H87", "EA", "BX", "CS", "PK", "CT", "DZN", "GLL", "OZA",
    "LTR", "KGM", "LBR", "RO", "PR", "BG", "DR", "MTR", "CMT", "MMT",
    "KMT", "TNE", "GRM", "MGM", "HLT", "MLT", "DAY", "MON", "ANN",
}

X12_MAX_LENGTHS = {
    "description": 80,
    "item_code": 48,
    "name": 60,
}

EDIFACT_MAX_LENGTHS = {
    "description": 35,
    "item_code": 35,
    "name": 35,
}


def _check_field_lengths(
    vof: dict[str, Any],
    max_lengths: dict[str, int],
    format_name: str,
) -> list[Issue]:
    """Verifica che i campi non superino le lunghezze massime del formato."""
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        description = line.get("description", "")
        if len(description) > max_lengths.get("description", 999):
            issues.append(Issue(
                code="EXP-02",
                severity=Severity.WARN,
                message=f"Riga {line.get('line_no', idx+1)}: descrizione ({len(description)} car.) supera il limite {format_name} ({max_lengths['description']} car.). Verrà troncata.",
                path=f"/lines/{idx}/description",
                details={
                    "length": len(description),
                    "max": max_lengths["description"],
                    "format": format_name,
                },
            ))
        
        buyer_code = line.get("buyer_item_code", "")
        if buyer_code and len(buyer_code) > max_lengths.get("item_code", 999):
            issues.append(Issue(
                code="EXP-02",
                severity=Severity.WARN,
                message=f"Riga {line.get('line_no', idx+1)}: codice cliente ({len(buyer_code)} car.) supera il limite {format_name}. Verrà troncato.",
                path=f"/lines/{idx}/buyer_item_code",
                details={
                    "length": len(buyer_code),
                    "max": max_lengths["item_code"],
                    "format": format_name,
                },
            ))
    
    return issues


@rule("EXP-01", Severity.BLOCK)
def rule_exp_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Export Peppol: manca EndpointID (GLN o schemeID) per buyer o seller."""
    export_format = ctx.config.get("export_format")
    
    if export_format != "PEPPOL_ORDER":
        return []
    
    issues: list[Issue] = []
    
    buyer = vof.get("buyer", {})
    buyer_gln = buyer.get("gln")
    buyer_peppol = buyer.get("peppol_endpoint")
    
    if not buyer_gln and not buyer_peppol:
        issues.append(Issue(
            code="EXP-01",
            severity=Severity.BLOCK,
            message="Export Peppol: manca EndpointID (GLN o schemeID) per il buyer.",
            path="/buyer/peppol_endpoint",
            suggestion="Per l'export Peppol è necessario un identificativo endpoint (GLN o altro scheme).",
        ))
    
    seller = vof.get("seller", {})
    seller_gln = seller.get("gln")
    seller_peppol = seller.get("peppol_endpoint")
    
    if not seller_gln and not seller_peppol:
        issues.append(Issue(
            code="EXP-01",
            severity=Severity.BLOCK,
            message="Export Peppol: manca EndpointID (GLN o schemeID) per il seller.",
            path="/seller/peppol_endpoint",
            suggestion="Per l'export Peppol è necessario un identificativo endpoint (GLN o altro scheme).",
        ))
    
    return issues


@rule("EXP-02", Severity.WARN)
def rule_exp_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Export X12/EDIFACT: campo oltre la lunghezza massima del segmento."""
    export_format = ctx.config.get("export_format")
    
    if export_format == "X12_850":
        return _check_field_lengths(vof, X12_MAX_LENGTHS, "X12")
    elif export_format == "EDIFACT_ORDERS":
        return _check_field_lengths(vof, EDIFACT_MAX_LENGTHS, "EDIFACT")
    
    return []


@rule("EXP-03", Severity.BLOCK)
def rule_exp_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """UoM senza corrispondenza nella codelist del formato di destinazione."""
    export_format = ctx.config.get("export_format")
    
    if not export_format:
        return []
    
    if export_format == "X12_850":
        valid_uoms = X12_UOM_CODES
        format_name = "X12"
    elif export_format == "EDIFACT_ORDERS":
        valid_uoms = EDIFACT_UOM_CODES
        format_name = "EDIFACT"
    elif export_format == "PEPPOL_ORDER":
        valid_uoms = PEPPOL_UOM_CODES
        format_name = "Peppol"
    else:
        return []
    
    issues: list[Issue] = []
    lines = vof.get("lines", [])
    
    for idx, line in enumerate(lines):
        resolution = line.get("resolution")
        if not resolution:
            continue
        
        erp_uom = resolution.get("erp_uom")
        if not erp_uom:
            continue
        
        if erp_uom not in valid_uoms:
            issues.append(Issue(
                code="EXP-03",
                severity=Severity.BLOCK,
                message=f"Riga {line.get('line_no', idx+1)}: UoM '{erp_uom}' non presente nella codelist {format_name}.",
                path=f"/lines/{idx}/resolution/erp_uom",
                suggestion=f"Selezionare un'unità di misura compatibile con {format_name}.",
                details={
                    "uom": erp_uom,
                    "format": format_name,
                    "valid_uoms": sorted(valid_uoms)[:10],
                },
            ))
    
    return issues
