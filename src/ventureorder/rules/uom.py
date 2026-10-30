"""Regole unità di misura (UOM-01 … UOM-05)."""

from __future__ import annotations

from ventureorder.rules.access import (
    INDIVISIBLE_UOMS,
    as_float,
    issue,
    line_pointer,
    line_resolution,
    normalize_uom,
)
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import product_of
from ventureorder.rules.registry import rule


def _line_uom(line: dict) -> str | None:
    return normalize_uom(line.get("uom")) or normalize_uom(line.get("uom_raw"))


@rule("UOM-01", Severity.REVIEW)
def uom_01_unknown(ctx: RuleContext) -> list[Issue]:
    """UoM non riconosciuta."""
    issues: list[Issue] = []
    ref = ctx.reference_data
    for index, line in enumerate(ctx.lines):
        raw = line.get("uom") or line.get("uom_raw")
        if not raw:
            issues.append(
                issue(
                    "UOM-01",
                    Severity.REVIEW,
                    f"Riga {line.get('line_no', index + 1)}: unità di misura mancante",
                    line_pointer(index, "uom"),
                    suggestion="Indicare l'UoM del documento (EA, CS, BX, …)",
                )
            )
            continue
        if ref is None:
            continue
        if not ref.is_valid_uom(str(raw)):
            issues.append(
                issue(
                    "UOM-01",
                    Severity.REVIEW,
                    f"Riga {line.get('line_no', index + 1)}: UoM '{raw}' non riconosciuta",
                    line_pointer(index, "uom"),
                    suggestion="Normalizzare al codice UN/ECE Rec. 20 (EA, CS, BX, DZN, …)",
                )
            )
    return issues


@rule("UOM-02", Severity.BLOCK)
def uom_02_no_conversion(ctx: RuleContext) -> list[Issue]:
    """Nessuna conversione tra UoM del cliente e unità vendibili del prodotto."""
    issues: list[Issue] = []
    ref = ctx.reference_data
    for index, line in enumerate(ctx.lines):
        resolution = line_resolution(line)
        factor = as_float(resolution.get("conversion_factor"))
        if factor:
            continue
        line_uom = _line_uom(line)
        product = product_of(ref, line) if ref is not None else None
        if line_uom is None or product is None:
            continue
        sale_uom = normalize_uom(product.sale_uom)
        if not sale_uom or line_uom == sale_uom:
            continue
        conv = ref.get_uom_conversion(line_uom, sale_uom, product.sku) if ref else None
        if conv is None:
            issues.append(
                issue(
                    "UOM-02",
                    Severity.BLOCK,
                    (
                        f"Riga {line.get('line_no', index + 1)}: nessuna conversione "
                        f"da '{line_uom}' a '{sale_uom}'"
                    ),
                    line_pointer(index, "uom"),
                    suggestion="Definire la conversione di confezione o correggere l'UoM",
                    from_uom=line_uom,
                    to_uom=sale_uom,
                )
            )
    return issues


@rule("UOM-03", Severity.INFO)
def uom_03_conversion_applied(ctx: RuleContext) -> list[Issue]:
    """Conversione applicata (es. CS → BX, DZ → EA)."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        resolution = line_resolution(line)
        factor = as_float(resolution.get("conversion_factor"))
        erp_uom = normalize_uom(resolution.get("erp_uom"))
        line_uom = _line_uom(line)
        converted = (factor is not None and factor != 1.0) or (
            erp_uom and line_uom and erp_uom != line_uom
        )
        if converted:
            issues.append(
                issue(
                    "UOM-03",
                    Severity.INFO,
                    (
                        f"Riga {line.get('line_no', index + 1)}: conversione UoM applicata "
                        f"({line_uom} → {erp_uom}, fattore {factor if factor is not None else 1})"
                    ),
                    line_pointer(index, "resolution"),
                    from_uom=line_uom,
                    to_uom=erp_uom,
                    factor=factor,
                )
            )
    return issues


@rule("UOM-04", Severity.REVIEW)
def uom_04_pack_mismatch(ctx: RuleContext) -> list[Issue]:
    """Confezione sul documento diversa da quella di catalogo."""
    issues: list[Issue] = []
    ref = ctx.reference_data
    if ref is None:
        return issues
    for index, line in enumerate(ctx.lines):
        pack = line.get("pack") or {}
        raw = (pack.get("raw") if isinstance(pack, dict) else None) or None
        if not raw:
            continue
        product = product_of(ref, line)
        catalog_raw = None
        if product and product.pack:
            catalog_raw = product.pack.get("raw")
        if not catalog_raw:
            continue
        if _norm_pack(raw) != _norm_pack(str(catalog_raw)):
            issues.append(
                issue(
                    "UOM-04",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: confezione documento "
                        f"'{raw}' diversa dal catalogo '{catalog_raw}'"
                    ),
                    line_pointer(index, "pack"),
                    suggestion="Verificare inner pack e quantità convertita",
                    document_pack=raw,
                    catalog_pack=catalog_raw,
                )
            )
    return issues


@rule("UOM-05", Severity.REVIEW)
def uom_05_non_integer_converted(ctx: RuleContext) -> list[Issue]:
    """Quantità convertita non intera per un'unità indivisibile."""
    issues: list[Issue] = []
    for index, line in enumerate(ctx.lines):
        resolution = line_resolution(line)
        qty = as_float(resolution.get("erp_quantity"))
        uom = normalize_uom(resolution.get("erp_uom")) or _line_uom(line)
        if qty is None or uom is None:
            continue
        if uom in INDIVISIBLE_UOMS and abs(qty - round(qty)) > 1e-9:
            issues.append(
                issue(
                    "UOM-05",
                    Severity.REVIEW,
                    (
                        f"Riga {line.get('line_no', index + 1)}: quantità convertita "
                        f"{qty} non intera per UoM indivisibile '{uom}'"
                    ),
                    line_pointer(index, "resolution"),
                    suggestion="Arrotondare o rivedere il fattore di conversione",
                )
            )
    return issues


def _norm_pack(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum() or ch in "/xX")
