"""EXP: Export/Peppol validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("EXP-01", Severity.REVIEW)
def exp_01_peppol_endpoint_missing(ctx: RuleContext) -> list[Issue]:
    """Verifica presenza endpoint Peppol per export."""
    export = ctx.order.get("export", {})
    if not export.get("peppol_required"):
        return []

    customer = ctx.order.get("customer", {})
    customer_id = customer.get("id") or customer.get("customer_id")
    ref = ctx.reference_data

    endpoint = None
    if ref and customer_id:
        endpoint = ref.get_peppol_endpoint(customer_id)

    if not endpoint and not customer.get("peppol_endpoint"):
        return [
            Issue(
                rule_id="EXP-01",
                severity=Severity.REVIEW,
                message="Endpoint Peppol mancante per cliente con export richiesto",
                json_pointer="/customer/peppol_endpoint",
                suggestion="Configurare l'endpoint Peppol del cliente",
            )
        ]

    return []


@rule("EXP-02", Severity.WARN)
def exp_02_field_length(ctx: RuleContext) -> list[Issue]:
    """Verifica lunghezza campi per export EDI/Peppol."""
    max_length = ctx.thresholds.get("max_field_length", 256)
    issues = []

    field_limits = {
        "/po_number": 35,
        "/customer/name": 100,
        "/customer/address/street": 100,
        "/customer/address/city": 50,
        "/notes": 500,
    }

    def check_field(path: str, value: str | None, limit: int) -> None:
        if value and len(str(value)) > limit:
            issues.append(
                Issue(
                    rule_id="EXP-02",
                    severity=Severity.WARN,
                    message=f"Campo {path} troppo lungo ({len(str(value))} caratteri, max {limit})",
                    json_pointer=path,
                    suggestion=f"Accorciare a massimo {limit} caratteri",
                )
            )

    check_field("/po_number", ctx.order.get("po_number"), field_limits["/po_number"])
    check_field("/notes", ctx.order.get("notes"), field_limits["/notes"])

    customer = ctx.order.get("customer", {})
    check_field("/customer/name", customer.get("name"), field_limits["/customer/name"])

    address = customer.get("address", {})
    check_field("/customer/address/street", address.get("street"), field_limits["/customer/address/street"])
    check_field("/customer/address/city", address.get("city"), field_limits["/customer/address/city"])

    lines = ctx.order.get("lines", [])
    for i, line in enumerate(lines):
        item = line.get("item", {})
        desc = item.get("description")
        if desc and len(desc) > max_length:
            issues.append(
                Issue(
                    rule_id="EXP-02",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: descrizione troppo lunga ({len(desc)} caratteri)",
                    json_pointer=f"/lines/{i}/item/description",
                    suggestion=f"Accorciare a massimo {max_length} caratteri",
                )
            )

    return issues


@rule("EXP-03", Severity.WARN)
def exp_03_uom_codelist(ctx: RuleContext) -> list[Issue]:
    """Verifica UoM per compatibilità Peppol codelist."""
    export = ctx.order.get("export", {})
    if not export.get("peppol_required"):
        return []

    lines = ctx.order.get("lines", [])
    ref = ctx.reference_data
    issues = []

    peppol_codes = set()
    if ref:
        peppol_codes = ref.get_peppol_uom_codes()
    else:
        peppol_codes = {
            "C62", "EA", "KGM", "GRM", "LTR", "MTR", "CMT", "MMT",
            "MTK", "MTQ", "LBR", "ONZ", "GLL", "QT", "PT", "INH",
        }

    for i, line in enumerate(lines):
        uom = line.get("uom") or line.get("unit_of_measure", "")
        if uom and uom.upper() not in peppol_codes:
            issues.append(
                Issue(
                    rule_id="EXP-03",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: UoM '{uom}' non in codelist Peppol",
                    json_pointer=f"/lines/{i}/uom",
                    suggestion="Usare un codice UN/ECE Rec 20 (es. C62, EA, KGM)",
                )
            )

    return issues
