"""Regole di validazione per il cliente (CUS).

CUS-01: Cliente non trovato in Odoo (BLOCK)
CUS-02: Cliente trovato solo per nome fuzzy con score < 0.95 (REVIEW)
CUS-03: ship_to non corrisponde a nessun indirizzo di consegna (REVIEW)
CUS-04: Dominio del mittente non associato al cliente riconosciuto (REVIEW)
CUS-05: Cliente con avviso o blocco in Odoo (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("CUS-01", Severity.BLOCK)
def rule_cus_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Cliente (buyer.resolved) non trovato in Odoo."""
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved")
    
    if not resolved or not resolved.get("erp_partner_id"):
        buyer_name = buyer.get("name", "sconosciuto")
        return [Issue(
            code="CUS-01",
            severity=Severity.BLOCK,
            message=f"Cliente '{buyer_name}' non trovato nell'anagrafica ERP.",
            path="/buyer/resolved",
            suggestion="Selezionare manualmente il cliente dall'anagrafica o crearne uno nuovo.",
            details={"buyer_name": buyer_name},
        )]
    
    return []


@rule("CUS-02", Severity.REVIEW)
def rule_cus_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Cliente trovato solo per nome fuzzy con score < 0.95."""
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved")
    
    if not resolved:
        return []
    
    method = resolved.get("method")
    score = resolved.get("score", 1.0)
    
    if method == "FUZZY_NAME" and score < 0.95:
        return [Issue(
            code="CUS-02",
            severity=Severity.REVIEW,
            message=f"Cliente identificato per similarità del nome (score {score:.2f}).",
            path="/buyer/resolved",
            suggestion="Verificare che il cliente identificato sia corretto.",
            details={
                "method": method,
                "score": score,
                "partner_id": resolved.get("erp_partner_id"),
            },
        )]
    
    return []


@rule("CUS-03", Severity.REVIEW)
def rule_cus_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """ship_to non corrisponde a nessun indirizzo di consegna del cliente."""
    ship_to = vof.get("ship_to")
    if not ship_to:
        return []
    
    ship_to_resolved = ship_to.get("resolved")
    
    if not ship_to_resolved or not ship_to_resolved.get("erp_partner_id"):
        ship_to_name = ship_to.get("name", "")
        ship_to_code = ship_to.get("code_on_document", "")
        
        buyer = vof.get("buyer", {})
        buyer_resolved = buyer.get("resolved", {})
        partner_id = buyer_resolved.get("erp_partner_id")
        
        if ctx.reference_data and partner_id:
            addresses = ctx.reference_data.get_customer_ship_to_addresses(partner_id)
            if addresses:
                return [Issue(
                    code="CUS-03",
                    severity=Severity.REVIEW,
                    message=f"Indirizzo di consegna '{ship_to_name or ship_to_code}' non trovato tra gli indirizzi del cliente.",
                    path="/ship_to/resolved",
                    suggestion="Selezionare un indirizzo di consegna esistente o crearne uno nuovo.",
                    details={
                        "ship_to_name": ship_to_name,
                        "ship_to_code": ship_to_code,
                        "available_addresses": len(addresses),
                    },
                )]
        
        if ship_to_name or ship_to_code:
            return [Issue(
                code="CUS-03",
                severity=Severity.REVIEW,
                message=f"Indirizzo di consegna '{ship_to_name or ship_to_code}' non risolto.",
                path="/ship_to/resolved",
                suggestion="Verificare e assegnare l'indirizzo di consegna corretto.",
            )]
    
    return []


@rule("CUS-04", Severity.REVIEW)
def rule_cus_04(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Dominio del mittente non associato al cliente riconosciuto."""
    source = vof.get("source", {})
    from_address = source.get("from_address")
    
    if not from_address or "@" not in from_address:
        return []
    
    sender_domain = from_address.split("@")[-1].lower()
    
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    
    if not partner_id or not ctx.reference_data:
        return []
    
    customer = ctx.reference_data.get_customer_by_id(partner_id)
    if not customer:
        return []
    
    customer_domain = customer.get("email_domain", "").lower()
    customer_email = customer.get("email", "")
    if customer_email and "@" in customer_email:
        customer_domain = customer_email.split("@")[-1].lower()
    
    if customer_domain and sender_domain != customer_domain and not sender_domain.endswith(f".{customer_domain}"):
        return [Issue(
            code="CUS-04",
            severity=Severity.REVIEW,
            message=f"Dominio email mittente ({sender_domain}) non corrisponde al cliente ({customer_domain}).",
            path="/source/from_address",
            suggestion="Verificare che l'ordine provenga effettivamente dal cliente indicato. Possibile inoltro o frode.",
            details={
                "sender_domain": sender_domain,
                "customer_domain": customer_domain,
                "from_address": from_address,
            },
        )]
    
    return []


@rule("CUS-05", Severity.REVIEW)
def rule_cus_05(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Cliente con avviso o blocco in Odoo (sale_warn = block/warning)."""
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    
    if not partner_id or not ctx.reference_data:
        return []
    
    customer = ctx.reference_data.get_customer_by_id(partner_id)
    if not customer:
        return []
    
    sale_warn = customer.get("sale_warn")
    
    if sale_warn == "block":
        return [Issue(
            code="CUS-05",
            severity=Severity.REVIEW,
            message="Cliente bloccato in Odoo. Impossibile creare ordini.",
            path="/buyer/resolved",
            suggestion="Contattare l'amministrazione per verificare lo stato del cliente.",
            details={"sale_warn": sale_warn, "partner_id": partner_id},
        )]
    elif sale_warn == "warning":
        warn_msg = customer.get("sale_warn_msg", "")
        return [Issue(
            code="CUS-05",
            severity=Severity.REVIEW,
            message=f"Cliente con avviso in Odoo: {warn_msg or 'nessun dettaglio'}.",
            path="/buyer/resolved",
            suggestion="Leggere l'avviso e procedere con cautela.",
            details={"sale_warn": sale_warn, "message": warn_msg},
        )]
    
    return []
