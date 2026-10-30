"""Regole cliente (CUS-01 … CUS-05)."""

from __future__ import annotations

from ventureorder.rules.access import email_domain, issue, resolved
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.reference import addresses_match, customer_of
from ventureorder.rules.registry import rule

FUZZY_METHODS = frozenset({"FUZZY_NAME"})


@rule("CUS-01", Severity.BLOCK)
def cus_01_buyer_resolved(ctx: RuleContext) -> list[Issue]:
    """Cliente (``buyer.resolved``) non trovato in anagrafica."""
    info = resolved(ctx.buyer)
    partner_id = info.get("erp_partner_id")
    partner_ref = info.get("erp_partner_ref")
    if partner_id is None and not partner_ref:
        return [
            issue(
                "CUS-01",
                Severity.BLOCK,
                "Cliente non risolto: manca buyer.resolved",
                "/buyer/resolved",
                suggestion="Riconoscere il cliente (P.IVA, dominio, codice) prima di validare",
            )
        ]
    if ctx.reference_data is None:
        return []
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None:
        label = partner_ref or partner_id
        return [
            issue(
                "CUS-01",
                Severity.BLOCK,
                f"Cliente '{label}' non trovato in anagrafica Odoo",
                "/buyer/resolved",
                suggestion="Verificare l'anagrafica o creare il partner (dati sintetici)",
            )
        ]
    return []


@rule("CUS-02", Severity.REVIEW)
def cus_02_fuzzy_name(ctx: RuleContext) -> list[Issue]:
    """Cliente trovato solo per nome fuzzy (score < 0,95)."""
    info = resolved(ctx.buyer)
    method = str(info.get("method") or "")
    score = info.get("score")
    score_f = float(score) if isinstance(score, int | float) else 0.0
    if method in FUZZY_METHODS and score_f < 0.95:
        return [
            issue(
                "CUS-02",
                Severity.REVIEW,
                (
                    f"Cliente riconosciuto in modo incerto "
                    f"(metodo {method or 'n/d'}, score {score_f:.2f})"
                ),
                "/buyer/resolved",
                suggestion="Verificare l'associazione con l'anagrafica",
                method=method,
                score=score_f,
            )
        ]
    return []


@rule("CUS-03", Severity.REVIEW)
def cus_03_ship_to(ctx: RuleContext) -> list[Issue]:
    """``ship_to`` non corrisponde a nessun indirizzo di consegna del cliente."""
    if not ctx.ship_to:
        return []
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None:
        return []
    if addresses_match(ctx.ship_to, customer):
        return []
    return [
        issue(
            "CUS-03",
            Severity.REVIEW,
            "Indirizzo di consegna non presente tra i child_ids di tipo delivery del cliente",
            "/ship_to",
            suggestion="Verificare o aggiungere l'indirizzo di consegna in anagrafica",
        )
    ]


@rule("CUS-04", Severity.REVIEW)
def cus_04_sender_domain(ctx: RuleContext) -> list[Issue]:
    """Dominio del mittente non associato al cliente riconosciuto."""
    from_address = ctx.source.get("from_address")
    domain = email_domain(from_address if isinstance(from_address, str) else None)
    if not domain:
        return []
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None or not customer.email_domain:
        return []
    expected = customer.email_domain.lower()
    if domain == expected or domain.endswith("." + expected):
        return []
    return [
        issue(
            "CUS-04",
            Severity.REVIEW,
            f"Dominio mittente '{domain}' non associato al cliente ({expected})",
            "/source/from_address",
            suggestion="Possibile inoltro o tentativo di frode: verificare il mittente",
            sender_domain=domain,
            customer_domain=expected,
        )
    ]


@rule("CUS-05", Severity.REVIEW)
def cus_05_sale_warn(ctx: RuleContext) -> list[Issue]:
    """Cliente con avviso o blocco in Odoo (``sale_warn``)."""
    customer = customer_of(ctx.reference_data, ctx.vof)
    if customer is None:
        return []
    warn = (customer.sale_warn or "no-message").lower()
    if warn in {"block", "warning"}:
        return [
            issue(
                "CUS-05",
                Severity.REVIEW,
                f"Cliente con sale_warn='{warn}' in Odoo",
                "/buyer/resolved",
                suggestion="Gestire l'avviso/blocco prima di creare la bozza",
                sale_warn=warn,
            )
        ]
    return []
