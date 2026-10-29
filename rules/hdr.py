"""Regole di validazione per la testata dell'ordine (HDR).

HDR-01: Manca po_number (BLOCK)
HDR-02: po_date mancante o non plausibile (REVIEW)
HDR-03: Valuta diversa da quella del listino cliente (REVIEW)
HDR-04: requested_delivery_date precedente a po_date o già passata (REVIEW)
HDR-05: document_type = CHANGE o CANCEL (REVIEW)
HDR-06: Termini di pagamento diversi da quelli del cliente (WARN)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("HDR-01", Severity.BLOCK)
def rule_hdr_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Manca po_number."""
    header = vof.get("header", {})
    po_number = header.get("po_number")
    
    if not po_number or not str(po_number).strip():
        return [Issue(
            code="HDR-01",
            severity=Severity.BLOCK,
            message="Numero ordine (PO Number) mancante. Campo obbligatorio.",
            path="/header/po_number",
            suggestion="Inserire il numero dell'ordine d'acquisto del cliente.",
        )]
    return []


@rule("HDR-02", Severity.REVIEW)
def rule_hdr_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """po_date mancante o non plausibile."""
    header = vof.get("header", {})
    po_date_str = header.get("po_date")
    issues: list[Issue] = []
    
    if not po_date_str:
        issues.append(Issue(
            code="HDR-02",
            severity=Severity.REVIEW,
            message="Data ordine (PO Date) mancante.",
            path="/header/po_date",
            suggestion="Inserire la data dell'ordine nel formato YYYY-MM-DD.",
        ))
        return issues
    
    try:
        po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        future_days = int(ctx.get_threshold("po_date_future_days", 7))
        past_days = int(ctx.get_threshold("po_date_past_days", 90))
        
        if po_date > today + timedelta(days=future_days):
            issues.append(Issue(
                code="HDR-02",
                severity=Severity.REVIEW,
                message=f"Data ordine {po_date_str} oltre {future_days} giorni nel futuro.",
                path="/header/po_date",
                suggestion="Verificare che la data dell'ordine sia corretta.",
                details={"po_date": po_date_str, "limit_days": future_days},
            ))
        elif po_date < today - timedelta(days=past_days):
            issues.append(Issue(
                code="HDR-02",
                severity=Severity.REVIEW,
                message=f"Data ordine {po_date_str} oltre {past_days} giorni nel passato.",
                path="/header/po_date",
                suggestion="Verificare che la data dell'ordine sia corretta.",
                details={"po_date": po_date_str, "limit_days": past_days},
            ))
    except ValueError:
        issues.append(Issue(
            code="HDR-02",
            severity=Severity.REVIEW,
            message=f"Data ordine '{po_date_str}' non valida o formato non riconosciuto.",
            path="/header/po_date",
            suggestion="La data deve essere nel formato YYYY-MM-DD (es. 2026-11-03).",
        ))
    
    return issues


@rule("HDR-03", Severity.REVIEW)
def rule_hdr_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Valuta diversa da quella del listino del cliente."""
    header = vof.get("header", {})
    currency = header.get("currency")
    
    if not currency:
        return []
    
    if ctx.reference_data:
        buyer = vof.get("buyer", {})
        resolved = buyer.get("resolved", {})
        partner_id = resolved.get("erp_partner_id")
        
        if partner_id:
            customer = ctx.reference_data.get_customer_by_id(partner_id)
            if customer:
                customer_currency = customer.get("currency", "USD")
                if currency != customer_currency:
                    return [Issue(
                        code="HDR-03",
                        severity=Severity.REVIEW,
                        message=f"Valuta ordine ({currency}) diversa dal listino cliente ({customer_currency}).",
                        path="/header/currency",
                        suggestion=f"Verificare la valuta. Il cliente usa normalmente {customer_currency}.",
                        details={
                            "order_currency": currency,
                            "customer_currency": customer_currency,
                        },
                    )]
    
    return []


@rule("HDR-04", Severity.REVIEW)
def rule_hdr_04(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """requested_delivery_date precedente a po_date o già passata."""
    header = vof.get("header", {})
    po_date_str = header.get("po_date")
    delivery_date_str = header.get("requested_delivery_date")
    
    if not delivery_date_str:
        return []
    
    issues: list[Issue] = []
    
    try:
        delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        if delivery_date < today:
            issues.append(Issue(
                code="HDR-04",
                severity=Severity.REVIEW,
                message=f"Data di consegna richiesta ({delivery_date_str}) già passata.",
                path="/header/requested_delivery_date",
                suggestion="La data di consegna richiesta è nel passato. Verificare con il cliente.",
            ))
        
        if po_date_str:
            try:
                po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date()
                if delivery_date < po_date:
                    issues.append(Issue(
                        code="HDR-04",
                        severity=Severity.REVIEW,
                        message=f"Data di consegna ({delivery_date_str}) precedente alla data ordine ({po_date_str}).",
                        path="/header/requested_delivery_date",
                        suggestion="La data di consegna non può essere prima della data dell'ordine.",
                    ))
            except ValueError:
                pass
    except ValueError:
        issues.append(Issue(
            code="HDR-04",
            severity=Severity.REVIEW,
            message=f"Data di consegna '{delivery_date_str}' non valida.",
            path="/header/requested_delivery_date",
            suggestion="La data deve essere nel formato YYYY-MM-DD.",
        ))
    
    return issues


@rule("HDR-05", Severity.REVIEW)
def rule_hdr_05(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """document_type = CHANGE o CANCEL: revisione obbligatoria nel prototipo."""
    doc_type = vof.get("document_type")
    
    if doc_type in ("CHANGE", "CANCEL"):
        message = (
            f"Ordine di tipo {doc_type}. "
            "Nel prototipo le modifiche e gli annullamenti richiedono sempre revisione manuale."
        )
        return [Issue(
            code="HDR-05",
            severity=Severity.REVIEW,
            message=message,
            path="/document_type",
            suggestion="Verificare l'ordine originale e applicare le modifiche manualmente.",
        )]
    
    return []


@rule("HDR-06", Severity.WARN)
def rule_hdr_06(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Termini di pagamento del PO diversi da quelli del cliente in Odoo."""
    header = vof.get("header", {})
    payment_terms = header.get("payment_terms_text")
    
    if not payment_terms or not ctx.reference_data:
        return []
    
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    
    if partner_id:
        customer = ctx.reference_data.get_customer_by_id(partner_id)
        if customer:
            customer_terms = customer.get("payment_terms")
            if customer_terms and payment_terms.lower() != customer_terms.lower():
                return [Issue(
                    code="HDR-06",
                    severity=Severity.WARN,
                    message=f"Termini di pagamento '{payment_terms}' diversi da quelli del cliente '{customer_terms}'.",
                    path="/header/payment_terms_text",
                    suggestion="I termini di pagamento dell'ordine differiscono da quelli standard del cliente.",
                    details={
                        "order_terms": payment_terms,
                        "customer_terms": customer_terms,
                    },
                )]
    
    return []
