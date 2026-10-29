"""SEC: Security validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("SEC-01", Severity.BLOCK)
def sec_01_dangerous_attachments(ctx: RuleContext) -> list[Issue]:
    """Blocca ordini con allegati potenzialmente pericolosi."""
    attachments = ctx.order.get("attachments", [])
    source = ctx.order.get("source", {})
    source_attachments = source.get("attachments", [])
    ref = ctx.reference_data
    issues = []

    all_attachments = attachments + source_attachments

    for i, att in enumerate(all_attachments):
        filename = att.get("filename") or att.get("name", "")
        extension = ""
        if "." in filename:
            extension = "." + filename.rsplit(".", 1)[-1].lower()

        is_dangerous = False
        if ref:
            is_dangerous = ref.is_dangerous_extension(extension)
        else:
            dangerous_extensions = {
                ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif",
                ".vbs", ".js", ".jar", ".ps1", ".sh", ".dll", ".sys",
            }
            is_dangerous = extension in dangerous_extensions

        if is_dangerous:
            issues.append(
                Issue(
                    rule_id="SEC-01",
                    severity=Severity.BLOCK,
                    message=f"Allegato potenzialmente pericoloso: {filename}",
                    json_pointer=f"/attachments/{i}" if i < len(attachments) else f"/source/attachments/{i - len(attachments)}",
                    suggestion="Rimuovere l'allegato e verificare la fonte",
                )
            )

    return issues


@rule("SEC-02", Severity.WARN)
def sec_02_email_authentication(ctx: RuleContext) -> list[Issue]:
    """Verifica autenticazione email (SPF/DKIM)."""
    source = ctx.order.get("source", {})
    email_headers = source.get("email_headers", {})

    if not email_headers:
        return []

    issues = []

    spf_result = email_headers.get("spf_result", "").lower()
    dkim_result = email_headers.get("dkim_result", "").lower()

    if spf_result and spf_result not in ("pass", "none", ""):
        issues.append(
            Issue(
                rule_id="SEC-02",
                severity=Severity.WARN,
                message=f"Verifica SPF fallita: {spf_result}",
                json_pointer="/source/email_headers/spf_result",
                suggestion="Verificare l'autenticità del mittente",
            )
        )

    if dkim_result and dkim_result not in ("pass", "none", ""):
        issues.append(
            Issue(
                rule_id="SEC-02",
                severity=Severity.WARN,
                message=f"Verifica DKIM fallita: {dkim_result}",
                json_pointer="/source/email_headers/dkim_result",
                suggestion="Verificare l'autenticità del mittente",
            )
        )

    return issues
