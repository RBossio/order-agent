"""Regole di export (EXP-01 … EXP-03). Si applicano solo al formato richiesto."""

from __future__ import annotations

from ventureorder.rules.access import issue, normalize_uom, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.registry import rule


def _target(ctx: RuleContext) -> str | None:
    if not ctx.export_target:
        return None
    return str(ctx.export_target).upper()


@rule("EXP-01", Severity.BLOCK)
def exp_01_peppol_endpoint(ctx: RuleContext) -> list[Issue]:
    """Export Peppol: manca EndpointID (o GLN) per buyer o seller."""
    if _target(ctx) != "PEPPOL":
        return []
    issues: list[Issue] = []
    for party_name, pointer in (("buyer", "/buyer"), ("seller", "/seller")):
        party = ctx.vof.get(party_name) or {}
        if not isinstance(party, dict):
            party = {}
        endpoint = party.get("peppol_endpoint") or party.get("gln")
        if not endpoint:
            issues.append(
                issue(
                    "EXP-01",
                    Severity.BLOCK,
                    f"Export Peppol: manca EndpointID/GLN per {party_name}",
                    f"{pointer}/peppol_endpoint",
                    suggestion="Valorizzare peppol_endpoint o gln prima dell'export Peppol",
                )
            )
    return issues


@rule("EXP-02", Severity.WARN)
def exp_02_segment_length(ctx: RuleContext) -> list[Issue]:
    """Export X12/EDIFACT: campo oltre la lunghezza massima del segmento (si tronca)."""
    target = _target(ctx)
    if target not in {"X12", "EDIFACT"}:
        return []
    issues: list[Issue] = []
    imd_max = int(threshold(ctx, "x12_imd_max_length", 35))
    for index, line in enumerate(ctx.lines):
        description = line.get("description") or ""
        if len(str(description)) > imd_max:
            issues.append(
                issue(
                    "EXP-02",
                    Severity.WARN,
                    (
                        f"Riga {line.get('line_no', index + 1)}: descrizione di "
                        f"{len(str(description))} caratteri (max IMD {imd_max}); verrà troncata"
                    ),
                    f"/lines/{index}/description",
                    suggestion="Tracciare il troncamento in export; accorciare se possibile",
                    max_length=imd_max,
                )
            )
    po_number = str(ctx.header.get("po_number") or "")
    po_max = 22 if target == "X12" else 35
    if len(po_number) > po_max:
        issues.append(
            issue(
                "EXP-02",
                Severity.WARN,
                f"po_number di {len(po_number)} caratteri (max {po_max} per {target}); verrà troncato",
                "/header/po_number",
                suggestion="Tracciare il troncamento in export",
                max_length=po_max,
            )
        )
    return issues


@rule("EXP-03", Severity.BLOCK)
def exp_03_uom_codelist(ctx: RuleContext) -> list[Issue]:
    """UoM senza corrispondenza nella codelist del formato di destinazione."""
    target = _target(ctx)
    if target not in {"PEPPOL", "X12", "EDIFACT"}:
        return []
    issues: list[Issue] = []
    ref = ctx.reference_data
    for index, line in enumerate(ctx.lines):
        raw = line.get("uom") or line.get("uom_raw")
        if not raw:
            continue
        mapped = None
        if ref is not None:
            mapped = ref.map_uom_for_export(str(raw), target)
        elif normalize_uom(str(raw)):
            mapped = normalize_uom(str(raw))
        if mapped is None:
            issues.append(
                issue(
                    "EXP-03",
                    Severity.BLOCK,
                    (
                        f"Riga {line.get('line_no', index + 1)}: UoM '{raw}' senza "
                        f"corrispondenza nella codelist {target}"
                    ),
                    f"/lines/{index}/uom",
                    suggestion="Mappare l'UoM nella tabella del formato di destinazione",
                )
            )
    return issues
