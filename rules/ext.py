"""EXT: Extraction/Confidence validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("EXT-01", Severity.REVIEW)
def ext_01_low_confidence(ctx: RuleContext) -> list[Issue]:
    """Segnala campi estratti con confidenza bassa."""
    confidence_map = ctx.confidence_map
    min_confidence = ctx.thresholds.get("confidence_min", 0.90)
    issues = []

    critical_fields = {
        "po_number": "Numero ordine",
        "customer.name": "Nome cliente",
        "customer.id": "ID cliente",
        "total": "Totale",
        "order_date": "Data ordine",
    }

    for field_path, label in critical_fields.items():
        confidence = confidence_map.get(field_path)
        if confidence is not None and confidence < min_confidence:
            json_pointer = "/" + field_path.replace(".", "/")
            issues.append(
                Issue(
                    rule_id="EXT-01",
                    severity=Severity.REVIEW,
                    message=f"Campo '{label}' estratto con confidenza bassa ({confidence:.0%})",
                    json_pointer=json_pointer,
                    suggestion="Verificare manualmente il valore estratto",
                    details={"field": field_path, "confidence": confidence},
                )
            )

    for key, confidence in confidence_map.items():
        if key.startswith("lines.") and confidence < min_confidence:
            parts = key.split(".")
            if len(parts) >= 2:
                line_idx = parts[1]
                field_name = ".".join(parts[2:]) if len(parts) > 2 else "valore"
                issues.append(
                    Issue(
                        rule_id="EXT-01",
                        severity=Severity.REVIEW,
                        message=f"Riga {int(line_idx) + 1}: campo '{field_name}' con confidenza bassa ({confidence:.0%})",
                        json_pointer=f"/lines/{line_idx}",
                        suggestion="Verificare manualmente il valore estratto",
                        details={"field": key, "confidence": confidence},
                    )
                )

    return issues


@rule("EXT-02", Severity.WARN)
def ext_02_unanchored_value(ctx: RuleContext) -> list[Issue]:
    """Segnala valori estratti senza ancoraggio nel documento."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        extraction = line.get("extraction_metadata", {})
        anchored = extraction.get("anchored", True)
        source_bbox = extraction.get("source_bbox")

        if not anchored or (source_bbox is None and extraction.get("source") == "inference"):
            issues.append(
                Issue(
                    rule_id="EXT-02",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: valore inferito senza ancoraggio nel documento",
                    json_pointer=f"/lines/{i}",
                    suggestion="Verificare la correttezza del valore inferito",
                )
            )

    header_extraction = ctx.order.get("extraction_metadata", {})
    for field in ["total", "order_date", "po_number"]:
        field_meta = header_extraction.get(field, {})
        if isinstance(field_meta, dict) and not field_meta.get("anchored", True):
            issues.append(
                Issue(
                    rule_id="EXT-02",
                    severity=Severity.WARN,
                    message=f"Campo '{field}': valore inferito senza ancoraggio",
                    json_pointer=f"/{field}",
                    suggestion="Verificare la correttezza del valore inferito",
                )
            )

    return issues


@rule("EXT-03", Severity.REVIEW)
def ext_03_llm_extraction_errors(ctx: RuleContext) -> list[Issue]:
    """Segnala errori o warning dall'estrazione LLM."""
    extraction = ctx.order.get("extraction_metadata", {})
    errors = extraction.get("errors", [])
    warnings = extraction.get("warnings", [])
    issues = []

    for error in errors:
        issues.append(
            Issue(
                rule_id="EXT-03",
                severity=Severity.REVIEW,
                message=f"Errore estrazione: {error}",
                json_pointer="/extraction_metadata/errors",
                suggestion="Verificare i dati estratti",
            )
        )

    for warning in warnings:
        issues.append(
            Issue(
                rule_id="EXT-03",
                severity=Severity.REVIEW,
                message=f"Avviso estrazione: {warning}",
                json_pointer="/extraction_metadata/warnings",
                suggestion="Verificare i dati estratti",
            )
        )

    return issues
