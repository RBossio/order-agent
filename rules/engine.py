"""Motore di validazione degli ordini.

Esegue tutte le regole registrate su un ordine VOF e produce
un risultato strutturato con issues, score e percorso decisionale.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from rules.models import (
    DecisionRoute,
    Issue,
    ReferenceDataProvider,
    RuleContext,
    Severity,
    ValidationResult,
)
from rules.registry import get_all_rules

logger = logging.getLogger(__name__)


class ValidationEngine:
    """Motore di validazione dichiarativo e configurabile.
    
    Esegue le regole di validazione su un ordine VOF e produce
    un risultato strutturato con:
    - Lista delle issue con codice, severità, messaggio e JSON Pointer
    - Score complessivo (0-1)
    - Percorso decisionale (AUTO_POST, REVIEW, REJECT)
    
    La configurazione per tenant è caricata da config/rules.yaml e
    config/thresholds.yaml.
    """
    
    def __init__(
        self,
        config_dir: Path | str | None = None,
        reference_data: ReferenceDataProvider | None = None,
    ) -> None:
        """Inizializza il motore.
        
        Args:
            config_dir: Directory con i file di configurazione YAML
            reference_data: Provider per i dati di riferimento
        """
        self.config_dir = Path(config_dir) if config_dir else None
        self.reference_data = reference_data
        self._tenant_configs: dict[str, dict[str, Any]] = {}
    
    def load_config(self, tenant_id: str) -> dict[str, Any]:
        """Carica la configurazione per un tenant.
        
        La configurazione include:
        - thresholds: soglie per le regole (es. price_tolerance_pct)
        - rules: override di severità e abilitazione per regola
        """
        if tenant_id in self._tenant_configs:
            return self._tenant_configs[tenant_id]
        
        config: dict[str, Any] = {
            "thresholds": self._get_default_thresholds(),
            "rules": {},
        }
        
        if self.config_dir:
            thresholds_file = self.config_dir / "thresholds.yaml"
            if thresholds_file.exists():
                with open(thresholds_file) as f:
                    all_thresholds = yaml.safe_load(f) or {}
                    config["thresholds"].update(
                        all_thresholds.get("defaults", {})
                    )
                    config["thresholds"].update(
                        all_thresholds.get(tenant_id, {})
                    )
            
            rules_file = self.config_dir / "rules.yaml"
            if rules_file.exists():
                with open(rules_file) as f:
                    all_rules = yaml.safe_load(f) or {}
                    config["rules"].update(all_rules.get("defaults", {}))
                    config["rules"].update(all_rules.get(tenant_id, {}))
        
        self._tenant_configs[tenant_id] = config
        return config
    
    def _get_default_thresholds(self) -> dict[str, Any]:
        """Restituisce le soglie predefinite."""
        return {
            "price_tolerance_pct": 2.0,
            "total_tolerance_pct": 0.1,
            "total_tolerance_abs": 0.02,
            "line_amount_tolerance_pct": 0.5,
            "line_amount_tolerance_abs": 0.01,
            "confidence_min": 0.90,
            "fuzzy_match_min": 0.75,
            "fuzzy_match_review": 0.92,
            "po_date_future_days": 7,
            "po_date_past_days": 90,
            "quantity_anomaly_factor": 3.0,
            "duplicate_similarity_pct": 80.0,
            "duplicate_window_days": 3,
            "max_attachment_mb": 20,
        }
    
    def validate(
        self,
        vof: dict[str, Any],
        tenant_id: str | None = None,
    ) -> ValidationResult:
        """Valida un ordine VOF.
        
        Args:
            vof: Ordine nel formato VOF (schema/venture-order.v1.schema.json)
            tenant_id: ID del tenant (default: prende da vof["tenant_id"])
        
        Returns:
            ValidationResult con issues, score e percorso
        """
        tenant_id = tenant_id or vof.get("tenant_id", "default")
        config = self.load_config(tenant_id)
        
        ctx = RuleContext(
            tenant_id=tenant_id,
            reference_data=self.reference_data,
            config=config,
        )
        
        result = ValidationResult()
        
        all_rules = get_all_rules()
        for code, (rule_func, _, default_severity) in sorted(all_rules.items()):
            if not ctx.is_rule_enabled(code):
                logger.debug(f"Regola {code} disabilitata per tenant {tenant_id}")
                continue
            
            try:
                issues = rule_func(vof, ctx)
                for issue in issues:
                    actual_severity = ctx.get_rule_severity(code, default_severity)
                    issue.severity = actual_severity
                    result.add_issue(issue)
            except Exception as e:
                logger.exception("Errore nell'esecuzione della regola %s", code)
                result.add_issue(Issue(
                    code=code,
                    severity=Severity.WARN,
                    message=f"Errore interno nella validazione: {e}",
                ))
        
        self._compute_final_score(vof, result, ctx)
        self._determine_route(result, ctx)
        
        return result
    
    def _compute_final_score(
        self,
        vof: dict[str, Any],
        result: ValidationResult,
        ctx: RuleContext,
    ) -> None:
        """Calcola lo score finale basato su confidenze e issue."""
        min_confidence = 1.0
        
        evidence = vof.get("evidence", {})
        critical_paths = [
            "/header/po_number",
            "/buyer",
        ]
        
        for line_idx, line in enumerate(vof.get("lines", [])):
            critical_paths.extend([
                f"/lines/{line_idx}/quantity",
                f"/lines/{line_idx}/uom_raw",
            ])
            if line.get("resolution"):
                critical_paths.append(f"/lines/{line_idx}/resolution")
        
        for path in critical_paths:
            if path in evidence:
                conf = evidence[path].get("confidence", 1.0)
                min_confidence = min(min_confidence, conf)
        
        result.score = min(result.score, min_confidence)
        
        warn_count = sum(1 for i in result.issues if i.severity == Severity.WARN)
        result.score = max(0, result.score - (warn_count * 0.05))
    
    def _determine_route(
        self,
        result: ValidationResult,
        ctx: RuleContext,
    ) -> None:
        """Determina il percorso decisionale finale."""
        has_block = any(i.severity == Severity.BLOCK for i in result.issues)
        has_review = any(i.severity == Severity.REVIEW for i in result.issues)
        
        dup_01_02 = any(i.code in ("DUP-01", "DUP-02") for i in result.issues)
        sec_01 = any(i.code == "SEC-01" for i in result.issues)
        
        if dup_01_02 or sec_01:
            result.route = DecisionRoute.REJECT
        elif has_block or has_review:
            result.route = DecisionRoute.REVIEW
        elif result.score >= 0.97:
            result.route = DecisionRoute.AUTO_OK
        else:
            result.route = DecisionRoute.REVIEW
    
    def apply_to_vof(
        self,
        vof: dict[str, Any],
        result: ValidationResult,
    ) -> dict[str, Any]:
        """Applica il risultato della validazione al VOF.
        
        Aggiorna i campi validation e decision del VOF.
        
        Returns:
            Il VOF aggiornato
        """
        vof_copy = vof.copy()
        
        vof_copy["validation"] = {
            "issues": [issue.to_dict() for issue in result.issues]
        }
        
        vof_copy["decision"] = {
            "score": round(result.score, 2),
            "route": result.route.value,
            "reasons": list(set(result.reasons)),
        }
        
        vof_copy["status"] = result.get_final_status()
        
        return vof_copy
