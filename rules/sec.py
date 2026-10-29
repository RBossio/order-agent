"""Regole di validazione per la sicurezza (SEC).

SEC-01: Allegato cifrato, con macro, oltre 20 MB o di tipo non ammesso (BLOCK)
SEC-02: SPF/DKIM falliti (solo con caselle reali; nel prototipo non attiva) (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "message/rfc822",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".vbs", ".js",
    ".jar", ".ps1", ".sh", ".dll", ".sys",
}

MACRO_EXTENSIONS = {".xlsm", ".docm", ".pptm", ".xlsb"}


@rule("SEC-01", Severity.BLOCK)
def rule_sec_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Allegato cifrato, con macro, oltre 20 MB o di tipo non ammesso."""
    issues: list[Issue] = []
    source = vof.get("source", {})
    documents = source.get("documents", [])
    
    max_size_mb = ctx.get_threshold("max_attachment_mb", 20)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    for idx, doc in enumerate(documents):
        filename = doc.get("filename", "").lower()
        mime_type = doc.get("mime_type", "")
        size_bytes = doc.get("size_bytes", 0)
        is_encrypted = doc.get("is_encrypted", False)
        has_macros = doc.get("has_macros", False)
        
        if is_encrypted:
            issues.append(Issue(
                code="SEC-01",
                severity=Severity.BLOCK,
                message=f"Allegato '{doc.get('filename')}' è cifrato. Impossibile elaborarlo.",
                path=f"/source/documents/{idx}",
                suggestion="Richiedere al mittente una versione non cifrata del documento.",
                details={"filename": doc.get("filename"), "reason": "encrypted"},
            ))
            continue
        
        if has_macros or any(filename.endswith(ext) for ext in MACRO_EXTENSIONS):
            issues.append(Issue(
                code="SEC-01",
                severity=Severity.BLOCK,
                message=f"Allegato '{doc.get('filename')}' contiene macro. Messo in quarantena.",
                path=f"/source/documents/{idx}",
                suggestion="Richiedere al mittente una versione senza macro.",
                details={"filename": doc.get("filename"), "reason": "macros"},
            ))
            continue
        
        if size_bytes > max_size_bytes:
            size_mb = size_bytes / (1024 * 1024)
            issues.append(Issue(
                code="SEC-01",
                severity=Severity.BLOCK,
                message=f"Allegato '{doc.get('filename')}' ({size_mb:.1f} MB) supera il limite di {max_size_mb} MB.",
                path=f"/source/documents/{idx}",
                suggestion=f"La dimensione massima ammessa è {max_size_mb} MB.",
                details={
                    "filename": doc.get("filename"),
                    "size_mb": round(size_mb, 1),
                    "max_mb": max_size_mb,
                    "reason": "size",
                },
            ))
            continue
        
        if any(filename.endswith(ext) for ext in DANGEROUS_EXTENSIONS):
            issues.append(Issue(
                code="SEC-01",
                severity=Severity.BLOCK,
                message=f"Allegato '{doc.get('filename')}' è di un tipo non ammesso (eseguibile).",
                path=f"/source/documents/{idx}",
                suggestion="Questo tipo di file non è accettato per ragioni di sicurezza.",
                details={"filename": doc.get("filename"), "reason": "dangerous_extension"},
            ))
            continue
        
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            issues.append(Issue(
                code="SEC-01",
                severity=Severity.REVIEW,
                message=f"Allegato '{doc.get('filename')}' con MIME type '{mime_type}' non standard.",
                path=f"/source/documents/{idx}",
                suggestion="Verificare che il file sia effettivamente un documento d'ordine.",
                details={"filename": doc.get("filename"), "mime_type": mime_type},
            ))
    
    return issues


@rule("SEC-02", Severity.REVIEW)
def rule_sec_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """SPF/DKIM falliti (solo in futuro con caselle reali; nel prototipo non attiva)."""
    source = vof.get("source", {})
    
    spf_result = source.get("spf_result")
    dkim_result = source.get("dkim_result")
    
    if spf_result is None and dkim_result is None:
        return []
    
    issues: list[Issue] = []
    
    if spf_result and spf_result.lower() not in ("pass", "none"):
        issues.append(Issue(
            code="SEC-02",
            severity=Severity.REVIEW,
            message=f"Verifica SPF fallita: {spf_result}. Possibile email contraffatta.",
            path="/source",
            suggestion="Verificare l'autenticità del mittente prima di elaborare l'ordine.",
            details={"spf_result": spf_result},
        ))
    
    if dkim_result and dkim_result.lower() not in ("pass", "none"):
        issues.append(Issue(
            code="SEC-02",
            severity=Severity.REVIEW,
            message=f"Verifica DKIM fallita: {dkim_result}. Possibile email modificata.",
            path="/source",
            suggestion="Verificare l'integrità del messaggio prima di elaborare l'ordine.",
            details={"dkim_result": dkim_result},
        ))
    
    return issues
