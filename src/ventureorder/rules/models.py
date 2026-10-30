"""Modelli del motore di validazione (severità, issue, contesto, esito)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Severità di una issue, come da §7.1 dell'architettura."""

    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    WARN = "WARN"
    INFO = "INFO"

    def at_least(self, minimum: Severity) -> Severity:
        """Restituisce la più alta tra questa severità e ``minimum``."""
        rank = {Severity.INFO: 0, Severity.WARN: 1, Severity.REVIEW: 2, Severity.BLOCK: 3}
        return self if rank[self] >= rank[minimum] else minimum


class DecisionRoute(StrEnum):
    """Esito di routing dell'ordine."""

    AUTO_POST = "AUTO_POST"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass
class Issue:
    """Issue emessa da una regola, allineata a ``validation.issues`` del VOF."""

    rule_id: str
    severity: Severity
    message: str
    json_pointer: str
    suggestion: str | None = None
    details: dict[str, Any] | None = None
    from_exception: bool = False

    def to_schema(self) -> dict[str, Any]:
        """Serializza nel formato dello schema VOF (``code`` / ``path``)."""
        payload: dict[str, Any] = {
            "code": self.rule_id,
            "severity": self.severity.value,
            "path": self.json_pointer,
            "message": self.message,
        }
        return payload


@dataclass
class SecurityHints:
    """Segnali di sicurezza non rappresentabili nel VOF chiuso (ingestione)."""

    encrypted: bool = False
    has_macros: bool = False
    file_size_bytes: int | None = None
    disallowed_type: bool = False
    filename: str | None = None
    spf_pass: bool | None = None
    dkim_pass: bool | None = None


@dataclass
class RuleContext:
    """Contesto di esecuzione di una regola: VOF, anagrafica, soglie, orologio.

    ``as_of`` rende deterministiche le regole sulle date (test e replay).
    """

    vof: dict[str, Any]
    as_of: date = field(default_factory=date.today)
    reference_data: Any = None
    config: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    document_text: str | None = None
    declared_line_count: int | None = None
    export_target: str | None = None
    security: SecurityHints | None = None
    llm_schema_attempts: int = 0
    llm_schema_valid: bool = True

    @property
    def header(self) -> dict[str, Any]:
        value = self.vof.get("header")
        return value if isinstance(value, dict) else {}

    @property
    def lines(self) -> list[dict[str, Any]]:
        value = self.vof.get("lines")
        return value if isinstance(value, list) else []

    @property
    def buyer(self) -> dict[str, Any]:
        value = self.vof.get("buyer")
        return value if isinstance(value, dict) else {}

    @property
    def seller(self) -> dict[str, Any]:
        value = self.vof.get("seller")
        return value if isinstance(value, dict) else {}

    @property
    def ship_to(self) -> dict[str, Any]:
        value = self.vof.get("ship_to")
        return value if isinstance(value, dict) else {}

    @property
    def source(self) -> dict[str, Any]:
        value = self.vof.get("source")
        return value if isinstance(value, dict) else {}

    @property
    def charges(self) -> list[dict[str, Any]]:
        value = self.vof.get("charges")
        return value if isinstance(value, list) else []

    @property
    def totals(self) -> dict[str, Any]:
        value = self.vof.get("totals")
        return value if isinstance(value, dict) else {}

    @property
    def evidence(self) -> dict[str, Any]:
        value = self.vof.get("evidence")
        return value if isinstance(value, dict) else {}

    @property
    def processing(self) -> dict[str, Any]:
        value = self.vof.get("processing")
        return value if isinstance(value, dict) else {}


@dataclass
class ValidationResult:
    """Esito dell'esecuzione di tutte le regole su un VOF."""

    issues: list[Issue] = field(default_factory=list)
    decision: DecisionRoute = DecisionRoute.REVIEW
    score: float = 1.0
    reasons: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def add_issue(self, issue: Issue) -> None:
        """Aggiunge una issue e aggiorna il riepilogo per severità."""
        self.issues.append(issue)
        key = issue.severity.value
        self.summary[key] = self.summary.get(key, 0) + 1

    def to_vof_fields(self) -> dict[str, Any]:
        """Campi ``validation`` e ``decision`` da unire al VOF."""
        return {
            "validation": {"issues": [issue.to_schema() for issue in self.issues]},
            "decision": {
                "score": round(self.score, 4),
                "route": self.decision.value,
                "reasons": list(self.reasons),
            },
        }
