"""HDR: Header validation rules."""

import re
from datetime import datetime

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("HDR-01", Severity.BLOCK)
def hdr_01_po_number_required(ctx: RuleContext) -> list[Issue]:
    """Verifica che il numero d'ordine (PO) sia presente e valido."""
    po = ctx.order.get("po_number")
    if not po or not str(po).strip():
        return [
            Issue(
                rule_id="HDR-01",
                severity=Severity.BLOCK,
                message="Numero d'ordine (PO) mancante o vuoto",
                json_pointer="/po_number",
                suggestion="Inserire il numero d'ordine del cliente",
            )
        ]
    return []


@rule("HDR-02", Severity.REVIEW)
def hdr_02_order_date_valid(ctx: RuleContext) -> list[Issue]:
    """Verifica che la data dell'ordine sia valida e non futura."""
    order_date = ctx.order.get("order_date")
    if not order_date:
        return [
            Issue(
                rule_id="HDR-02",
                severity=Severity.REVIEW,
                message="Data ordine mancante",
                json_pointer="/order_date",
                suggestion="Inserire la data dell'ordine",
            )
        ]

    try:
        parsed = datetime.fromisoformat(order_date.replace("Z", "+00:00"))
        if parsed.date() > datetime.now().date():
            return [
                Issue(
                    rule_id="HDR-02",
                    severity=Severity.REVIEW,
                    message="Data ordine nel futuro",
                    json_pointer="/order_date",
                    suggestion="Verificare la data dell'ordine",
                )
            ]
    except (ValueError, AttributeError):
        return [
            Issue(
                rule_id="HDR-02",
                severity=Severity.REVIEW,
                message="Formato data ordine non valido",
                json_pointer="/order_date",
                suggestion="Usare formato ISO 8601 (YYYY-MM-DD)",
            )
        ]

    return []


@rule("HDR-03", Severity.BLOCK)
def hdr_03_currency_valid(ctx: RuleContext) -> list[Issue]:
    """Verifica che la valuta sia valida."""
    currency = ctx.order.get("currency")
    if not currency:
        return [
            Issue(
                rule_id="HDR-03",
                severity=Severity.BLOCK,
                message="Valuta mancante",
                json_pointer="/currency",
                suggestion="Specificare la valuta (es. EUR, USD)",
            )
        ]

    ref = ctx.reference_data
    if ref and not ref.is_valid_currency(currency):
        return [
            Issue(
                rule_id="HDR-03",
                severity=Severity.BLOCK,
                message=f"Valuta '{currency}' non riconosciuta",
                json_pointer="/currency",
                suggestion="Usare un codice valuta ISO 4217 valido",
            )
        ]

    return []


@rule("HDR-04", Severity.WARN)
def hdr_04_delivery_date_reasonable(ctx: RuleContext) -> list[Issue]:
    """Verifica che la data di consegna sia ragionevole."""
    delivery_date = ctx.order.get("requested_delivery_date")
    if not delivery_date:
        return []

    try:
        parsed = datetime.fromisoformat(delivery_date.replace("Z", "+00:00"))
        today = datetime.now().date()

        if parsed.date() < today:
            return [
                Issue(
                    rule_id="HDR-04",
                    severity=Severity.WARN,
                    message="Data consegna richiesta nel passato",
                    json_pointer="/requested_delivery_date",
                    suggestion="Verificare la data di consegna",
                )
            ]

        days_ahead = (parsed.date() - today).days
        if days_ahead > 365:
            return [
                Issue(
                    rule_id="HDR-04",
                    severity=Severity.WARN,
                    message=f"Data consegna molto lontana ({days_ahead} giorni)",
                    json_pointer="/requested_delivery_date",
                    suggestion="Verificare la data di consegna",
                )
            ]
    except (ValueError, AttributeError):
        return [
            Issue(
                rule_id="HDR-04",
                severity=Severity.WARN,
                message="Formato data consegna non valido",
                json_pointer="/requested_delivery_date",
                suggestion="Usare formato ISO 8601 (YYYY-MM-DD)",
            )
        ]

    return []


@rule("HDR-05", Severity.INFO)
def hdr_05_document_type(ctx: RuleContext) -> list[Issue]:
    """Verifica il tipo di documento."""
    doc_type = ctx.order.get("document_type")
    valid_types = {"ORDER", "BLANKET", "RELEASE", "QUOTE", "RFQ"}

    if doc_type and doc_type.upper() not in valid_types:
        return [
            Issue(
                rule_id="HDR-05",
                severity=Severity.INFO,
                message=f"Tipo documento '{doc_type}' non standard",
                json_pointer="/document_type",
                suggestion=f"Tipi validi: {', '.join(sorted(valid_types))}",
            )
        ]

    return []


@rule("HDR-06", Severity.INFO)
def hdr_06_payment_terms(ctx: RuleContext) -> list[Issue]:
    """Verifica i termini di pagamento."""
    terms = ctx.order.get("payment_terms")
    if not terms:
        return []

    pattern = r"^(NET\s*\d+|COD|CIA|CWO|\d+\s*(DAYS?|GG)|PREPAID)$"
    if not re.match(pattern, str(terms).upper().strip()):
        return [
            Issue(
                rule_id="HDR-06",
                severity=Severity.INFO,
                message=f"Termini di pagamento '{terms}' non standard",
                json_pointer="/payment_terms",
                suggestion="Es: NET30, NET60, COD",
            )
        ]

    return []
