"""Regole di sicurezza (SEC-01, SEC-02)."""

from __future__ import annotations

from pathlib import Path

from ventureorder.rules.access import (
    ALLOWED_DOCUMENT_KINDS,
    DANGEROUS_EXTENSIONS,
    issue,
    threshold,
)
from ventureorder.rules.models import Issue, RuleContext, Severity
from ventureorder.rules.registry import rule


def _extension(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


@rule("SEC-01", Severity.BLOCK)
def sec_01_quarantine(ctx: RuleContext) -> list[Issue]:
    """Allegato cifrato, con macro, oltre 20 MB o di tipo non ammesso (quarantena)."""
    issues: list[Issue] = []
    max_bytes = int(threshold(ctx, "max_attachment_bytes", 20 * 1024 * 1024))
    hints = ctx.security
    if hints is not None:
        if hints.encrypted:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    "Allegato cifrato: ordine in quarantena",
                    "/source/documents",
                    suggestion="Non elaborare file cifrati; richiedere una copia in chiaro",
                )
            )
        if hints.has_macros:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    "Allegato con macro: ordine in quarantena",
                    "/source/documents",
                    suggestion="I file Excel con macro (.xlsm) non sono ammessi",
                )
            )
        if hints.disallowed_type:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    "Tipo di allegato non ammesso: ordine in quarantena",
                    "/source/documents",
                    suggestion="Accettati solo PDF, Excel, CSV, EML e immagini",
                )
            )
        if hints.file_size_bytes is not None and hints.file_size_bytes > max_bytes:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    (
                        f"Allegato di {hints.file_size_bytes} byte oltre il massimo "
                        f"di {max_bytes} (20 MB)"
                    ),
                    "/source/documents",
                    suggestion="Chiedere un file più piccolo",
                )
            )
        ext = _extension(hints.filename)
        if ext in DANGEROUS_EXTENSIONS:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    f"Estensione pericolosa '{ext}': ordine in quarantena",
                    "/source/documents",
                    suggestion="Rifiutare eseguibili e macro",
                )
            )

    for index, document in enumerate(ctx.source.get("documents") or []):
        if not isinstance(document, dict):
            continue
        filename = document.get("filename")
        ext = _extension(filename if isinstance(filename, str) else None)
        kind = document.get("kind")
        if ext in DANGEROUS_EXTENSIONS:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    f"Allegato pericoloso '{filename}': ordine in quarantena",
                    f"/source/documents/{index}",
                    suggestion="Rifiutare eseguibili e macro",
                )
            )
        if kind and kind not in ALLOWED_DOCUMENT_KINDS:
            issues.append(
                issue(
                    "SEC-01",
                    Severity.BLOCK,
                    f"Tipo documento '{kind}' non ammesso: ordine in quarantena",
                    f"/source/documents/{index}/kind",
                    suggestion="Accettati PDF_TEXT, PDF_SCAN, XLSX, XLS, CSV, EMAIL_BODY, IMAGE",
                )
            )
    return issues


@rule("SEC-02", Severity.REVIEW)
def sec_02_spf_dkim(ctx: RuleContext) -> list[Issue]:
    """SPF/DKIM falliti (disattivata nel prototipo via config/rules.yaml)."""
    hints = ctx.security
    if hints is None:
        return []
    issues: list[Issue] = []
    if hints.spf_pass is False:
        issues.append(
            issue(
                "SEC-02",
                Severity.REVIEW,
                "Verifica SPF fallita",
                "/source/from_address",
                suggestion="Verificare l'autenticità del mittente (caselle reali, futuro)",
            )
        )
    if hints.dkim_pass is False:
        issues.append(
            issue(
                "SEC-02",
                Severity.REVIEW,
                "Verifica DKIM fallita",
                "/source/from_address",
                suggestion="Verificare l'autenticità del mittente (caselle reali, futuro)",
            )
        )
    return issues
