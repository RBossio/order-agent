"""DUP: Duplicate detection rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("DUP-01", Severity.BLOCK)
def dup_01_existing_order(ctx: RuleContext) -> list[Issue]:
    """Verifica se esiste già un ordine con lo stesso PO number."""
    po_number = ctx.order.get("po_number")
    customer = ctx.order.get("customer", {})
    customer_id = customer.get("id") or customer.get("customer_id")
    ref = ctx.reference_data

    if not po_number or not customer_id or not ref:
        return []

    existing = ref.get_existing_orders(customer_id, po_number)
    if existing:
        order_ids = [str(o.get("id") or o.get("order_id")) for o in existing[:3]]
        return [
            Issue(
                rule_id="DUP-01",
                severity=Severity.BLOCK,
                message=f"Ordine duplicato: PO '{po_number}' già esistente per questo cliente",
                json_pointer="/po_number",
                suggestion="Verificare se è un duplicato o usare un PO diverso",
                details={"existing_orders": order_ids},
            )
        ]

    return []


@rule("DUP-02", Severity.BLOCK)
def dup_02_content_hash(ctx: RuleContext) -> list[Issue]:
    """Verifica duplicato tramite hash contenuto (SHA-256 o Message-ID)."""
    content_hash = ctx.order.get("content_hash")
    message_id = ctx.order.get("source", {}).get("message_id")
    ref = ctx.reference_data

    if not ref:
        return []

    hash_to_check = content_hash or message_id
    if hash_to_check:
        existing = ref.get_order_by_hash(hash_to_check)
        if existing:
            existing_id = existing.get("id") or existing.get("order_id")
            return [
                Issue(
                    rule_id="DUP-02",
                    severity=Severity.BLOCK,
                    message="Ordine duplicato: contenuto identico a ordine già presente",
                    json_pointer="/content_hash",
                    suggestion="Questo ordine è già stato elaborato",
                    details={"existing_order": existing_id, "hash": hash_to_check},
                )
            ]

    return []


@rule("DUP-03", Severity.REVIEW)
def dup_03_similar_order(ctx: RuleContext) -> list[Issue]:
    """Segnala ordini simili recenti (stesso cliente, data vicina, totale simile)."""
    customer = ctx.order.get("customer", {})
    customer_id = customer.get("id") or customer.get("customer_id")
    order_date = ctx.order.get("order_date")
    total = ctx.order.get("total") or ctx.order.get("order_total")
    ref = ctx.reference_data

    if not customer_id or not order_date or total is None or not ref:
        return []

    similar = ref.get_similar_orders(customer_id, order_date, total)
    if similar:
        similar_ids = [str(o.get("id") or o.get("order_id")) for o in similar[:3]]
        return [
            Issue(
                rule_id="DUP-03",
                severity=Severity.REVIEW,
                message="Ordine simile trovato: verificare se duplicato",
                json_pointer="/",
                suggestion="Confrontare con ordini simili recenti",
                details={"similar_orders": similar_ids},
            )
        ]

    return []
