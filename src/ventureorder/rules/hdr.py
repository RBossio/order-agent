"""Regole di testata (HDR-01 … HDR-06)."""

from __future__ import annotations

from datetime import timedelta

from ventureorder.rules.access import (
    issue,
    normalize_terms,
    parse_date,
    threshold,
)
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import customer_of
from ventureorder.rules.registry import rule


@rule("HDR-01", Severity.BLOCK)
def hdr_01_po_number_required(ctx: RuleContext) -> list[Issue]:
    """Manca ``header.po_number``."""
    po_number = ctx.header.get("po_number")
    if po_number is None or not str(po_number).strip():
        return [
            issue(
                "HDR-01",
                Severity.BLOCK,
                "Numero d'ordine (PO) mancante o vuoto",
                "/header/po_number",
                suggestion="Inserire il numero d'ordine del cliente",
            )
        ]
    return []


@rule("HDR-02", Severity.REVIEW)
def hdr_02_po_date_plausible(ctx: RuleContext) -> list[Issue]:
    """``po_date`` mancante o non plausibile (>7 giorni futuro o >90 passato)."""
    raw = ctx.header.get("po_date")
    if raw is None or not str(raw).strip():
        return [
            issue(
                "HDR-02",
                Severity.REVIEW,
                "Data ordine (po_date) mancante",
                "/header/po_date",
                suggestion="Inserire la data del PO nel formato YYYY-MM-DD",
            )
        ]
    parsed = parse_date(raw)
    if parsed is None:
        return [
            issue(
                "HDR-02",
                Severity.REVIEW,
                f"Data ordine non valida: {raw!r}",
                "/header/po_date",
                suggestion="Usare il formato ISO 8601 (YYYY-MM-DD)",
            )
        ]
    future_days = int(threshold(ctx, "po_date_future_days", 7))
    past_days = int(threshold(ctx, "po_date_past_days", 90))
    if parsed > ctx.as_of + timedelta(days=future_days):
        return [
            issue(
                "HDR-02",
                Severity.REVIEW,
                f"Data ordine {parsed.isoformat()} oltre {future_days} giorni nel futuro",
                "/header/po_date",
                suggestion="Verificare la data del PO",
                po_date=parsed.isoformat(),
            )
        ]
    if parsed < ctx.as_of - timedelta(days=past_days):
        return [
            issue(
                "HDR-02",
                Severity.REVIEW,
                f"Data ordine {parsed.isoformat()} oltre {past_days} giorni nel passato",
                "/header/po_date",
                suggestion="Verificare la data del PO",
                po_date=parsed.isoformat(),
            )
        ]
    return []


@rule("HDR-03", Severity.REVIEW)
def hdr_03_currency_vs_pricelist(ctx: RuleContext) -> list[Issue]:
    """Valuta del PO diversa da quella del listino cliente."""
    currency = (ctx.header.get("currency") or "").strip().upper()
    customer = customer_of(ctx.reference_data, ctx.vof)
    if not currency:
        return [
            issue(
                "HDR-03",
                Severity.REVIEW,
                "Valuta mancante in testata",
                "/header/currency",
                suggestion="Impostare il codice ISO 4217 del listino cliente",
            )
        ]
    if customer is None:
        return []
    expected = (customer.currency or "").strip().upper()
    if expected and currency != expected:
        return [
            issue(
                "HDR-03",
                Severity.REVIEW,
                f"Valuta del PO {currency} diversa dal listino cliente {expected}",
                "/header/currency",
                suggestion="Allineare la valuta a quella del listino Odoo",
                po_currency=currency,
                list_currency=expected,
            )
        ]
    return []


@rule("HDR-04", Severity.REVIEW)
def hdr_04_delivery_date(ctx: RuleContext) -> list[Issue]:
    """``requested_delivery_date`` precedente a ``po_date`` o già passata."""
    raw = ctx.header.get("requested_delivery_date")
    if raw is None or not str(raw).strip():
        return []
    delivery = parse_date(raw)
    if delivery is None:
        return [
            issue(
                "HDR-04",
                Severity.REVIEW,
                f"Data di consegna richiesta non valida: {raw!r}",
                "/header/requested_delivery_date",
                suggestion="Usare il formato ISO 8601 (YYYY-MM-DD)",
            )
        ]
    po_date = parse_date(ctx.header.get("po_date"))
    if po_date and delivery < po_date:
        return [
            issue(
                "HDR-04",
                Severity.REVIEW,
                f"Data di consegna {delivery.isoformat()} precedente alla data PO {po_date.isoformat()}",
                "/header/requested_delivery_date",
                suggestion="Correggere la data di consegna richiesta",
            )
        ]
    if delivery < ctx.as_of:
        return [
            issue(
                "HDR-04",
                Severity.REVIEW,
                f"Data di consegna richiesta {delivery.isoformat()} già passata",
                "/header/requested_delivery_date",
                suggestion="Verificare la data di consegna con il cliente",
            )
        ]
    return []


@rule("HDR-05", Severity.REVIEW)
def hdr_05_change_or_cancel(ctx: RuleContext) -> list[Issue]:
    """CHANGE/CANCEL: nel prototipo sempre revisione, senza modificare ordini."""
    doc_type = str(ctx.vof.get("document_type") or "ORIGINAL").upper()
    if doc_type in {"CHANGE", "CANCEL"}:
        return [
            issue(
                "HDR-05",
                Severity.REVIEW,
                f"Documento di tipo {doc_type}: revisione obbligatoria nel prototipo",
                "/document_type",
                suggestion="Non modificare automaticamente ordini esistenti",
            )
        ]
    return []


@rule("HDR-06", Severity.WARN)
def hdr_06_payment_terms(ctx: RuleContext) -> list[Issue]:
    """Termini di pagamento del PO diversi da quelli del cliente in Odoo."""
    po_terms = ctx.header.get("payment_terms_text")
    if not po_terms:
        return []
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None or not customer.payment_terms:
        return []
    if normalize_terms(str(po_terms)) != normalize_terms(customer.payment_terms):
        return [
            issue(
                "HDR-06",
                Severity.WARN,
                (
                    f"Termini di pagamento del PO '{po_terms}' diversi da quelli "
                    f"Odoo '{customer.payment_terms}'"
                ),
                "/header/payment_terms_text",
                suggestion="Verificare i termini; in posting non si forza il payment_term_id",
                po_terms=str(po_terms),
                erp_terms=customer.payment_terms,
            )
        ]
    return []
