"""CUS: Customer validation rules."""

import re

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("CUS-01", Severity.BLOCK)
def cus_01_customer_resolution(ctx: RuleContext) -> list[Issue]:
    """Verifica che il cliente sia identificato."""
    customer = ctx.order.get("customer", {})
    customer_id = customer.get("id") or customer.get("customer_id")
    customer_name = customer.get("name")

    if not customer_id and not customer_name:
        return [
            Issue(
                rule_id="CUS-01",
                severity=Severity.BLOCK,
                message="Cliente non identificato: ID e nome mancanti",
                json_pointer="/customer",
                suggestion="Specificare almeno l'ID o il nome del cliente",
            )
        ]

    if customer_id and ctx.reference_data:
        resolved = ctx.reference_data.get_customer(customer_id)
        if not resolved:
            return [
                Issue(
                    rule_id="CUS-01",
                    severity=Severity.BLOCK,
                    message=f"Cliente con ID '{customer_id}' non trovato in anagrafica",
                    json_pointer="/customer/id",
                    suggestion="Verificare l'ID cliente o creare una nuova anagrafica",
                )
            ]

    return []


@rule("CUS-02", Severity.REVIEW)
def cus_02_fuzzy_match(ctx: RuleContext) -> list[Issue]:
    """Segnala se il cliente è stato risolto con match fuzzy."""
    customer = ctx.order.get("customer", {})
    resolution_method = customer.get("resolution_method")
    confidence = customer.get("match_confidence", 1.0)

    if resolution_method == "fuzzy" or (confidence and confidence < 0.95):
        return [
            Issue(
                rule_id="CUS-02",
                severity=Severity.REVIEW,
                message=f"Cliente risolto con match fuzzy (confidenza: {confidence:.0%})",
                json_pointer="/customer",
                suggestion="Verificare l'associazione cliente",
                details={"confidence": confidence},
            )
        ]

    return []


@rule("CUS-03", Severity.REVIEW)
def cus_03_ship_to_differs(ctx: RuleContext) -> list[Issue]:
    """Verifica differenze tra bill_to e ship_to."""
    bill_to = ctx.order.get("bill_to", {})
    ship_to = ctx.order.get("ship_to", {})

    if not ship_to:
        return []

    bill_addr = _normalize_address(bill_to)
    ship_addr = _normalize_address(ship_to)

    if bill_addr and ship_addr and bill_addr != ship_addr:
        return [
            Issue(
                rule_id="CUS-03",
                severity=Severity.REVIEW,
                message="Indirizzo di spedizione diverso da fatturazione",
                json_pointer="/ship_to",
                suggestion="Verificare l'indirizzo di spedizione",
            )
        ]

    return []


def _normalize_address(addr: dict) -> str | None:
    """Normalize address for comparison."""
    if not addr:
        return None
    parts = [
        addr.get("street", ""),
        addr.get("city", ""),
        addr.get("postal_code", ""),
        addr.get("country", ""),
    ]
    normalized = " ".join(p.lower().strip() for p in parts if p)
    return normalized if normalized else None


@rule("CUS-04", Severity.WARN)
def cus_04_email_domain(ctx: RuleContext) -> list[Issue]:
    """Verifica dominio email del contatto."""
    customer = ctx.order.get("customer", {})
    email = customer.get("contact_email") or customer.get("email")

    if not email:
        return []

    suspicious_domains = {
        "tempmail.com", "throwaway.com", "guerrillamail.com",
        "10minutemail.com", "mailinator.com", "yopmail.com",
    }

    match = re.search(r"@([a-zA-Z0-9.-]+)$", email)
    if match:
        domain = match.group(1).lower()
        if domain in suspicious_domains:
            return [
                Issue(
                    rule_id="CUS-04",
                    severity=Severity.WARN,
                    message=f"Email usa dominio temporaneo/sospetto: {domain}",
                    json_pointer="/customer/contact_email",
                    suggestion="Verificare l'indirizzo email del cliente",
                )
            ]

    return []


@rule("CUS-05", Severity.INFO)
def cus_05_customer_warnings(ctx: RuleContext) -> list[Issue]:
    """Segnala avvisi configurati sul cliente."""
    customer = ctx.order.get("customer", {})
    warnings = customer.get("warnings", [])

    issues = []
    for i, warning in enumerate(warnings):
        issues.append(
            Issue(
                rule_id="CUS-05",
                severity=Severity.INFO,
                message=f"Avviso cliente: {warning}",
                json_pointer=f"/customer/warnings/{i}",
            )
        )

    return issues
