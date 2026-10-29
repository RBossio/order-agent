"""UOM: Unit of Measure validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("UOM-01", Severity.BLOCK)
def uom_01_unknown_uom(ctx: RuleContext) -> list[Issue]:
    """Verifica che l'unità di misura sia riconosciuta."""
    lines = ctx.order.get("lines", [])
    ref = ctx.reference_data
    issues = []

    for i, line in enumerate(lines):
        uom = line.get("uom") or line.get("unit_of_measure")
        if uom and ref and not ref.is_valid_uom(uom):
            issues.append(
                Issue(
                    rule_id="UOM-01",
                    severity=Severity.BLOCK,
                    message=f"Riga {i + 1}: unità di misura '{uom}' non riconosciuta",
                    json_pointer=f"/lines/{i}/uom",
                    suggestion="Usare un'unità standard (es. PZ, KG, L, M)",
                )
            )

    return issues


@rule("UOM-02", Severity.REVIEW)
def uom_02_no_conversion(ctx: RuleContext) -> list[Issue]:
    """Segnala quando non esiste conversione UoM per l'articolo."""
    lines = ctx.order.get("lines", [])
    ref = ctx.reference_data
    issues = []

    for i, line in enumerate(lines):
        line_uom = line.get("uom") or line.get("unit_of_measure")
        item = line.get("item", {})
        item_id = item.get("id") or item.get("item_id")
        item_uom = item.get("base_uom") or item.get("uom")

        if line_uom and item_uom and line_uom.upper() != item_uom.upper():
            if ref:
                conversion = ref.get_uom_conversion(line_uom, item_uom, item_id)
                if conversion is None:
                    issues.append(
                        Issue(
                            rule_id="UOM-02",
                            severity=Severity.REVIEW,
                            message=f"Riga {i + 1}: nessuna conversione da '{line_uom}' a '{item_uom}'",
                            json_pointer=f"/lines/{i}/uom",
                            suggestion="Definire la conversione UoM o correggere l'unità",
                            details={"from_uom": line_uom, "to_uom": item_uom},
                        )
                    )

    return issues


@rule("UOM-03", Severity.INFO)
def uom_03_conversion_applied(ctx: RuleContext) -> list[Issue]:
    """Informa quando è stata applicata una conversione UoM."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        conversion = line.get("uom_conversion_applied")
        if conversion:
            original = conversion.get("original_uom")
            target = conversion.get("target_uom")
            factor = conversion.get("factor", 1)
            issues.append(
                Issue(
                    rule_id="UOM-03",
                    severity=Severity.INFO,
                    message=f"Riga {i + 1}: conversione UoM applicata ({original} → {target}, fattore {factor})",
                    json_pointer=f"/lines/{i}/uom_conversion_applied",
                    details=conversion,
                )
            )

    return issues


@rule("UOM-04", Severity.WARN)
def uom_04_pack_mismatch(ctx: RuleContext) -> list[Issue]:
    """Verifica coerenza tra UoM e confezione."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        uom = line.get("uom", "").upper()
        item = line.get("item", {})
        pack_size = item.get("pack_size") or item.get("units_per_pack")

        if pack_size and pack_size > 1:
            if uom in ("PZ", "EA", "UN") and not line.get("pack_acknowledged"):
                issues.append(
                    Issue(
                        rule_id="UOM-04",
                        severity=Severity.WARN,
                        message=f"Riga {i + 1}: articolo venduto in confezioni da {pack_size}, ma UoM è '{uom}'",
                        json_pointer=f"/lines/{i}/uom",
                        suggestion="Verificare se la quantità è per pezzo o per confezione",
                        details={"pack_size": pack_size, "uom": uom},
                    )
                )

    return issues


@rule("UOM-05", Severity.WARN)
def uom_05_non_integer_qty(ctx: RuleContext) -> list[Issue]:
    """Segnala quantità non intere per UoM discrete."""
    lines = ctx.order.get("lines", [])
    issues = []
    discrete_uoms = {"PZ", "EA", "UN", "CT", "BOX", "PAL", "SET", "PR", "DZ"}

    for i, line in enumerate(lines):
        uom = (line.get("uom") or "").upper()
        qty = line.get("quantity")

        if uom in discrete_uoms and qty is not None:
            if isinstance(qty, float) and not qty.is_integer():
                issues.append(
                    Issue(
                        rule_id="UOM-05",
                        severity=Severity.WARN,
                        message=f"Riga {i + 1}: quantità {qty} non intera per UoM '{uom}'",
                        json_pointer=f"/lines/{i}/quantity",
                        suggestion="Arrotondare la quantità o cambiare UoM",
                    )
                )

    return issues
