"""Regole di validazione per l'estrazione e la confidenza (EXT).

EXT-01: Confidenza < 0.90 su un campo critico (REVIEW)
EXT-02: Valore non "ancorato" (snippet non trovato nel documento) (REVIEW)
EXT-03: Output LLM non valido rispetto allo schema dopo 2 tentativi (REVIEW)
"""

from __future__ import annotations

from typing import Any

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule

CRITICAL_PATHS = [
    "/header/po_number",
    "/buyer",
    "/buyer/name",
]


def _get_critical_paths_for_lines(vof: dict[str, Any]) -> list[str]:
    """Genera i path critici per ogni riga dell'ordine."""
    paths = list(CRITICAL_PATHS)
    
    for idx, line in enumerate(vof.get("lines", [])):
        paths.extend([
            f"/lines/{idx}/quantity",
            f"/lines/{idx}/uom_raw",
            f"/lines/{idx}/description",
        ])
        if line.get("unit_price") is not None:
            paths.append(f"/lines/{idx}/unit_price")
        if line.get("buyer_item_code"):
            paths.append(f"/lines/{idx}/buyer_item_code")
        if line.get("resolution"):
            paths.append(f"/lines/{idx}/resolution")
    
    return paths


@rule("EXT-01", Severity.REVIEW)
def rule_ext_01(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Confidenza < 0.90 su un campo critico."""
    issues: list[Issue] = []
    evidence = vof.get("evidence", {})
    
    if not evidence:
        return issues
    
    min_confidence = ctx.get_threshold("confidence_min", 0.90)
    critical_paths = _get_critical_paths_for_lines(vof)
    
    for path in critical_paths:
        if path in evidence:
            conf = evidence[path].get("confidence", 1.0)
            if conf < min_confidence:
                field_name = path.split("/")[-1]
                issues.append(Issue(
                    code="EXT-01",
                    severity=Severity.REVIEW,
                    message=f"Campo '{field_name}' estratto con confidenza bassa ({conf:.2f} < {min_confidence}).",
                    path=path,
                    suggestion="Verificare manualmente il valore estratto.",
                    details={
                        "confidence": conf,
                        "threshold": min_confidence,
                        "snippet": evidence[path].get("snippet"),
                    },
                ))
    
    return issues


@rule("EXT-02", Severity.REVIEW)
def rule_ext_02(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Valore non 'ancorato': lo snippet dell'evidenza non si trova nel testo estratto."""
    issues: list[Issue] = []
    evidence = vof.get("evidence", {})
    
    if not evidence:
        return issues
    
    for path, ev in evidence.items():
        snippet = ev.get("snippet")
        if not snippet:
            continue
        
        if ev.get("confidence", 1.0) >= 0.95:
            continue
        
        value = _get_value_at_path(vof, path)
        if value is None:
            continue
        
        value_str = str(value).strip()
        snippet_clean = snippet.strip()
        
        if value_str and snippet_clean and value_str not in snippet_clean and snippet_clean not in value_str:
            field_name = path.split("/")[-1]
            issues.append(Issue(
                code="EXT-02",
                severity=Severity.REVIEW,
                message=f"Campo '{field_name}' con valore '{value_str}' non trovato nello snippet '{snippet_clean[:50]}...'.",
                path=path,
                suggestion="Il valore potrebbe essere stato allucinato dall'LLM. Verificare nel documento originale.",
                details={
                    "value": value_str,
                    "snippet": snippet_clean[:100],
                },
            ))
    
    return issues


def _get_value_at_path(obj: dict[str, Any], path: str) -> Any:
    """Recupera un valore da un dizionario usando un JSON Pointer."""
    if not path.startswith("/"):
        return None
    
    parts = path[1:].split("/")
    current = obj
    
    for part in parts:
        if not part:
            continue
        
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
        
        if current is None:
            return None
    
    return current


@rule("EXT-03", Severity.REVIEW)
def rule_ext_03(vof: dict[str, Any], ctx: RuleContext) -> list[Issue]:
    """Output LLM non valido rispetto allo schema dopo 2 tentativi."""
    processing = vof.get("processing", {})
    
    extraction_errors = processing.get("extraction_errors", [])
    llm_retries = processing.get("llm_retries", 0)
    
    if llm_retries >= 2 or extraction_errors:
        error_msgs = extraction_errors[:3] if extraction_errors else ["Schema validation failed"]
        return [Issue(
            code="EXT-03",
            severity=Severity.REVIEW,
            message=f"Estrazione LLM con errori dopo {llm_retries} tentativi. Richiesta revisione manuale.",
            path="/processing",
            suggestion="L'estrazione automatica non è riuscita a produrre un output valido. Inserire i dati manualmente.",
            details={
                "retries": llm_retries,
                "errors": error_msgs,
            },
        )]
    
    return []
