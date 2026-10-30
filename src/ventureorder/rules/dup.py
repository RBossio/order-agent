"""Regole duplicati (DUP-01 … DUP-03)."""

from __future__ import annotations

from ventureorder.rules.access import issue, parse_date, threshold
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import customer_of, line_overlap
from ventureorder.rules.registry import rule


@rule("DUP-01", Severity.BLOCK)
def dup_01_existing_po(ctx: RuleContext) -> list[Issue]:
    """Esiste già un ordine con stesso (cliente, po_number, po_revision) POSTED/EXPORTED."""
    ref = ctx.reference_data
    customer = customer_of(ref, ctx.vof)
    po_number = ctx.header.get("po_number")
    if ref is None or customer is None or not po_number:
        return []
    revision = int(ctx.header.get("po_revision") or 0)
    existing = ref.get_existing_orders(customer.erp_partner_ref, str(po_number), revision)
    if not existing:
        return []
    ids = [order.order_id for order in existing[:3]]
    return [
        issue(
            "DUP-01",
            Severity.BLOCK,
            (
                f"Duplicato: PO '{po_number}' rev.{revision} già POSTED/EXPORTED "
                f"per {customer.erp_partner_ref}"
            ),
            "/header/po_number",
            suggestion="Scartare come duplicato o usare una revisione diversa",
            existing_orders=ids,
        )
    ]


@rule("DUP-02", Severity.BLOCK)
def dup_02_hash_or_message_id(ctx: RuleContext) -> list[Issue]:
    """Stesso SHA-256 di allegato o stesso Message-ID già elaborato."""
    ref = ctx.reference_data
    if ref is None:
        return []
    message_id = ctx.source.get("message_id")
    if message_id:
        found = ref.get_order_by_message_id(str(message_id))
        if found:
            return [
                issue(
                    "DUP-02",
                    Severity.BLOCK,
                    "Duplicato: Message-ID già elaborato",
                    "/source/message_id",
                    suggestion="Deduplica silenziosa: non rielaborare l'email",
                    existing_order=found.order_id,
                )
            ]
    for index, document in enumerate(ctx.source.get("documents") or []):
        sha = (document or {}).get("sha256") if isinstance(document, dict) else None
        if not sha:
            continue
        found = ref.get_order_by_sha256(str(sha))
        if found:
            return [
                issue(
                    "DUP-02",
                    Severity.BLOCK,
                    "Duplicato: SHA-256 dell'allegato già elaborato",
                    f"/source/documents/{index}/sha256",
                    suggestion="Deduplica silenziosa: non rielaborare l'allegato",
                    existing_order=found.order_id,
                )
            ]
    return []


@rule("DUP-03", Severity.REVIEW)
def dup_03_similar_order(ctx: RuleContext) -> list[Issue]:
    """Ordine molto simile (stesso cliente, ≥80% righe, ±3 giorni) con PO diverso."""
    ref = ctx.reference_data
    customer = customer_of(ref, ctx.vof)
    po_date = parse_date(ctx.header.get("po_date"))
    po_number = str(ctx.header.get("po_number") or "")
    if ref is None or customer is None or po_date is None:
        return []
    window = int(threshold(ctx, "similar_order_days", 3))
    overlap_min = float(threshold(ctx, "similar_line_overlap", 0.80))
    similar = ref.get_similar_orders(customer.erp_partner_ref, po_date, po_number, window)
    hits = [
        order
        for order in similar
        if line_overlap(ctx.lines, order) >= overlap_min
    ]
    if not hits:
        return []
    return [
        issue(
            "DUP-03",
            Severity.REVIEW,
            (
                "Ordine simile già presente "
                f"({hits[0].po_number}, sovrapposizione righe ≥ {overlap_min:.0%})"
            ),
            "/header/po_number",
            suggestion="Verificare se è un duplicato con PO diverso",
            similar_orders=[order.order_id for order in hits[:3]],
        )
    ]
