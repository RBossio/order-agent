"""Validation engine that orchestrates rule execution."""

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


class ValidationEngine:
    """Engine for executing validation rules on orders."""

    def __init__(
        self,
        config_dir: Path | str | None = None,
        reference_data: ReferenceDataProvider | None = None,
    ):
        self.config_dir = Path(config_dir) if config_dir else Path("config")
        self.reference_data = reference_data
        self.thresholds = self._load_thresholds()
        self.rules_config = self._load_rules_config()

    def _load_thresholds(self) -> dict[str, Any]:
        """Load thresholds configuration."""
        path = self.config_dir / "thresholds.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return self._default_thresholds()

    def _load_rules_config(self) -> dict[str, Any]:
        """Load rules configuration."""
        path = self.config_dir / "rules.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _default_thresholds(self) -> dict[str, Any]:
        """Default thresholds when config not available."""
        return {
            "price_tolerance_pct": 2.0,
            "confidence_min": 0.90,
            "qty_anomaly_multiple": 10,
            "total_tolerance_pct": 0.01,
            "similar_order_days": 7,
            "similar_order_tolerance_pct": 5.0,
            "max_field_length": 256,
        }

    def _get_effective_severity(self, rule_code: str, default: Severity) -> Severity:
        """Get effective severity for a rule (may be overridden in config)."""
        overrides = self.rules_config.get("severity_overrides", {})
        if rule_code in overrides:
            return Severity(overrides[rule_code])
        return default

    def _is_rule_enabled(self, rule_code: str) -> bool:
        """Check if a rule is enabled."""
        disabled = self.rules_config.get("disabled_rules", [])
        return rule_code not in disabled

    def validate(
        self,
        order: dict[str, Any],
        confidence_map: dict[str, float] | None = None,
    ) -> ValidationResult:
        """Validate an order and return the result."""
        context = RuleContext(
            order=order,
            confidence_map=confidence_map or {},
            reference_data=self.reference_data,
            config=self.rules_config,
            thresholds=self.thresholds,
        )

        result = ValidationResult()
        all_rules = get_all_rules()

        for rule_code, (rule_func, _, default_severity) in all_rules.items():
            if not self._is_rule_enabled(rule_code):
                continue

            effective_severity = self._get_effective_severity(rule_code, default_severity)

            try:
                issues = rule_func(context)
                for issue in issues:
                    issue.severity = effective_severity
                    result.add_issue(issue)
            except Exception as e:
                result.add_issue(
                    Issue(
                        rule_id=rule_code,
                        severity=Severity.WARN,
                        message=f"Errore durante l'esecuzione della regola: {type(e).__name__}",
                        json_pointer="/",
                        suggestion="Verificare i dati dell'ordine",
                    )
                )

        result.score = self._compute_score(result)
        return result

    def _compute_score(self, result: ValidationResult) -> float:
        """Compute a quality score based on issues."""
        score = 100.0
        penalties = {
            Severity.BLOCK: 50.0,
            Severity.REVIEW: 10.0,
            Severity.WARN: 2.0,
            Severity.INFO: 0.5,
        }

        for issue in result.issues:
            score -= penalties.get(issue.severity, 0)

        return max(0.0, score)

    def get_decision_explanation(self, result: ValidationResult) -> str:
        """Get Italian explanation of the decision."""
        if result.decision == DecisionRoute.REJECT:
            block_count = result.summary.get("BLOCK", 0)
            return f"Ordine rifiutato: {block_count} problema/i bloccante/i rilevato/i."
        if result.decision == DecisionRoute.REVIEW:
            review_count = result.summary.get("REVIEW", 0)
            return f"Ordine in revisione: {review_count} problema/i da verificare."
        return "Ordine approvato automaticamente."
