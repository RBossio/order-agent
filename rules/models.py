"""Modelli per il motore di regole di validazione."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(str, Enum):
    """Livelli di severità delle issue.
    
    - BLOCK: L'ordine non può essere approvato finché la issue non è risolta
    - REVIEW: Revisione umana obbligatoria, impedisce AUTO_POST
    - WARN: Mostrato in console, non blocca
    - INFO: Solo traccia (es. conversioni applicate)
    """
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class Issue:
    """Issue generata da una regola di validazione.
    
    Attributes:
        code: Codice della regola nel formato AAA-00 (es. HDR-01, ITM-03)
        severity: Livello di severità
        message: Messaggio in italiano che descrive il problema
        path: JSON Pointer del campo coinvolto (es. /header/po_number, /lines/0/quantity)
        suggestion: Suggerimento di correzione opzionale
        details: Dettagli aggiuntivi per il debugging
    """
    code: str
    severity: Severity
    message: str
    path: str | None = None
    suggestion: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte l'issue in dizionario per il VOF."""
        d: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.path:
            d["path"] = self.path
        if self.suggestion:
            d["suggestion"] = self.suggestion
        if self.details:
            d["details"] = self.details
        return d


class ReferenceDataProvider(Protocol):
    """Interfaccia per i dati di riferimento (articoli, clienti, xref).
    
    Interfaccia sostituibile come richiesto per il formato di datagen/master
    che arriverà con PR #4.
    """
    
    def get_customer_by_id(self, partner_id: int) -> dict[str, Any] | None:
        """Recupera un cliente per ID ERP."""
        ...
    
    def get_customer_by_email_domain(self, domain: str) -> dict[str, Any] | None:
        """Recupera un cliente per dominio email."""
        ...
    
    def get_product_by_id(self, product_id: int) -> dict[str, Any] | None:
        """Recupera un prodotto per ID ERP."""
        ...
    
    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Recupera un prodotto per SKU."""
        ...
    
    def get_xref(
        self, tenant_id: str, partner_id: int, customer_code: str
    ) -> dict[str, Any] | None:
        """Recupera cross-reference cliente-articolo."""
        ...
    
    def get_customer_ship_to_addresses(self, partner_id: int) -> list[dict[str, Any]]:
        """Recupera gli indirizzi di consegna di un cliente."""
        ...
    
    def get_order_history(
        self, tenant_id: str, partner_id: int, po_number: str
    ) -> list[dict[str, Any]]:
        """Recupera lo storico ordini per controllo duplicati."""
        ...
    
    def get_product_history_stats(
        self, tenant_id: str, partner_id: int, product_id: int
    ) -> dict[str, Any] | None:
        """Recupera le statistiche storiche di un prodotto per un cliente."""
        ...


@dataclass
class RuleContext:
    """Contesto per l'esecuzione delle regole.
    
    Contiene i dati di riferimento e la configurazione per tenant.
    """
    tenant_id: str
    reference_data: ReferenceDataProvider | None = None
    config: dict[str, Any] = field(default_factory=dict)
    processed_documents: set[str] = field(default_factory=set)
    processed_message_ids: set[str] = field(default_factory=set)
    
    def get_threshold(self, key: str, default: float) -> float:
        """Recupera una soglia dalla configurazione."""
        thresholds = self.config.get("thresholds", {})
        return float(thresholds.get(key, default))
    
    def get_rule_severity(self, rule_code: str, default: Severity) -> Severity:
        """Recupera la severità di una regola dalla configurazione."""
        rules_config = self.config.get("rules", {})
        rule_config = rules_config.get(rule_code, {})
        severity_str = rule_config.get("severity")
        if severity_str:
            return Severity(severity_str)
        return default
    
    def is_rule_enabled(self, rule_code: str) -> bool:
        """Verifica se una regola è abilitata."""
        rules_config = self.config.get("rules", {})
        rule_config = rules_config.get(rule_code, {})
        return rule_config.get("enabled", True)


class DecisionRoute(str, Enum):
    """Percorso decisionale dell'ordine."""
    AUTO_OK = "AUTO_POST"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass
class ValidationResult:
    """Risultato della validazione di un ordine.
    
    Attributes:
        issues: Lista delle issue trovate
        route: Percorso decisionale (AUTO_POST, REVIEW, REJECT)
        score: Score complessivo dell'ordine (0-1)
        reasons: Lista dei codici delle regole che hanno determinato il percorso
    """
    issues: list[Issue] = field(default_factory=list)
    route: DecisionRoute = DecisionRoute.AUTO_OK
    score: float = 1.0
    reasons: list[str] = field(default_factory=list)
    
    def add_issue(self, issue: Issue) -> None:
        """Aggiunge una issue e aggiorna il percorso."""
        self.issues.append(issue)
        
        if issue.severity == Severity.BLOCK:
            if self.route != DecisionRoute.REJECT:
                self.route = DecisionRoute.REVIEW
            self.reasons.append(issue.code)
            self.score = min(self.score, 0.5)
        elif issue.severity == Severity.REVIEW:
            if self.route == DecisionRoute.AUTO_OK:
                self.route = DecisionRoute.REVIEW
            self.reasons.append(issue.code)
            self.score = min(self.score, 0.8)
        elif issue.severity == Severity.WARN:
            self.score = max(0, self.score - 0.05)
    
    def has_blocking_issues(self) -> bool:
        """Verifica se ci sono issue bloccanti."""
        return any(i.severity == Severity.BLOCK for i in self.issues)
    
    def has_review_issues(self) -> bool:
        """Verifica se ci sono issue che richiedono revisione."""
        return any(i.severity in (Severity.BLOCK, Severity.REVIEW) for i in self.issues)
    
    def to_dict(self) -> dict[str, Any]:
        """Converte il risultato in dizionario per il VOF."""
        return {
            "validation": {
                "issues": [issue.to_dict() for issue in self.issues]
            },
            "decision": {
                "score": round(self.score, 2),
                "route": self.route.value,
                "reasons": list(set(self.reasons)),
            }
        }
    
    def get_final_status(self) -> str:
        """Determina lo stato finale dell'ordine."""
        if self.route == DecisionRoute.REJECT:
            return "REJECTED"
        elif self.route == DecisionRoute.REVIEW:
            return "NEEDS_REVIEW"
        else:
            return "VALIDATED"
