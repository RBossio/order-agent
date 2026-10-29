"""Regole di validazione per i duplicati (DUP).

DUP-01: Esiste già un ordine con stesso (cliente, po_number, po_revision) POSTED/EXPORTED (BLOCK)
DUP-02: Stesso SHA-256 di allegato o stesso Message-ID già elaborato (BLOCK)
DUP-03: Ordine molto simile (≥80% righe uguali, ±3 giorni) con po_number diverso (REVIEW)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("DUP-01", Severity.BLOCK)
def rule_dup_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Esiste già un ordine con stesso (cliente, po_number, po_revision) POSTED o EXPORTED."""
    if not ctx.reference_data:
        return []
    
    header = vof.get("header", {})
    po_number = header.get("po_number")
    po_revision = header.get("po_revision", 0)
    
    if not po_number:
        return []
    
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    
    if not partner_id:
        return []
    
    tenant_id = vof.get("tenant_id", ctx.tenant_id)
    
    existing_orders = ctx.reference_data.get_order_history(
        tenant_id, partner_id, po_number
    )
    
    for existing in existing_orders:
        existing_rev = existing.get("po_revision", 0)
        existing_status = existing.get("status")
        
        if existing_rev == po_revision and existing_status in ("POSTED", "EXPORTED"):
            return [Issue(
                code="DUP-01",
                severity=Severity.BLOCK,
                message=f"Ordine duplicato: {po_number} rev.{po_revision} già presente con stato {existing_status}.",
                path="/header/po_number",
                suggestion="Questo ordine è già stato elaborato. Scartare come duplicato.",
                details={
                    "po_number": po_number,
                    "po_revision": po_revision,
                    "existing_order_id": existing.get("order_id"),
                    "existing_status": existing_status,
                },
            )]
    
    return []


@rule("DUP-02", Severity.BLOCK)
def rule_dup_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Stesso SHA-256 di allegato o stesso Message-ID già elaborato."""
    source = vof.get("source", {})
    
    message_id = source.get("message_id")
    if message_id and message_id in ctx.processed_message_ids:
        return [Issue(
            code="DUP-02",
            severity=Severity.BLOCK,
            message=f"Email con Message-ID '{message_id}' già elaborata.",
            path="/source/message_id",
            suggestion="Deduplica silenziosa: questo messaggio è già stato processato.",
            details={"message_id": message_id},
        )]
    
    documents = source.get("documents", [])
    for idx, doc in enumerate(documents):
        sha256 = doc.get("sha256")
        if sha256 and sha256 in ctx.processed_documents:
            return [Issue(
                code="DUP-02",
                severity=Severity.BLOCK,
                message=f"Documento con SHA-256 '{sha256[:16]}...' già elaborato.",
                path=f"/source/documents/{idx}/sha256",
                suggestion="Deduplica silenziosa: questo documento è già stato processato.",
                details={"sha256": sha256, "filename": doc.get("filename")},
            )]
    
    return []


@rule("DUP-03", Severity.REVIEW)
def rule_dup_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Ordine molto simile (stesso cliente, ≥80% righe uguali, ±3 giorni) con po_number diverso."""
    if not ctx.reference_data:
        return []
    
    header = vof.get("header", {})
    po_number = header.get("po_number")
    po_date_str = header.get("po_date")
    
    if not po_number or not po_date_str:
        return []
    
    try:
        po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date()
    except ValueError:
        return []
    
    buyer = vof.get("buyer", {})
    resolved = buyer.get("resolved", {})
    partner_id = resolved.get("erp_partner_id")
    
    if not partner_id:
        return []
    
    tenant_id = vof.get("tenant_id", ctx.tenant_id)
    window_days = int(ctx.get_threshold("duplicate_window_days", 3))
    similarity_pct = ctx.get_threshold("duplicate_similarity_pct", 80.0)
    
    current_skus = set()
    for line in vof.get("lines", []):
        resolution = line.get("resolution")
        if resolution:
            sku = resolution.get("sku")
            if sku:
                current_skus.add(sku)
    
    if not current_skus:
        return []
    
    existing_orders = ctx.reference_data.get_order_history(tenant_id, partner_id, "")
    
    for existing in existing_orders:
        existing_po = existing.get("po_number")
        if existing_po == po_number:
            continue
        
        existing_date_str = existing.get("po_date")
        if existing_date_str:
            try:
                existing_date = datetime.strptime(existing_date_str, "%Y-%m-%d").date()
                if abs((po_date - existing_date).days) > window_days:
                    continue
            except ValueError:
                continue
        
        existing_skus = set(existing.get("skus", []))
        if not existing_skus:
            continue
        
        common = current_skus & existing_skus
        total = current_skus | existing_skus
        
        if total:
            similarity = len(common) / len(total) * 100
            if similarity >= similarity_pct:
                return [Issue(
                    code="DUP-03",
                    severity=Severity.REVIEW,
                    message=f"Ordine simile ({similarity:.0f}% righe in comune) a '{existing_po}' datato {existing_date_str}.",
                    path="/header/po_number",
                    suggestion="Verificare che non sia un ordine duplicato con numero diverso.",
                    details={
                        "existing_po_number": existing_po,
                        "existing_date": existing_date_str,
                        "similarity_pct": round(similarity, 1),
                        "common_skus": len(common),
                        "total_skus": len(total),
                    },
                )]
    
    return []
