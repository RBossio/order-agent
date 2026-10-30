"""Motore che esegue le regole registrate e calcola routing/score."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from ventureorder.rules.access import as_float, resolved, threshold
from ventureorder.rules.models import (
    DecisionRoute,
    Issue,
    RuleContext,
    SecurityHints,
    Severity,
    ValidationResult,
)
from ventureorder.rules.reference import ReferenceDataProvider, customer_of
from ventureorder.rules.registry import get_all_rules

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "price_tolerance_pct": 2.0,
    "confidence_min": 0.90,
    "po_date_future_days": 7,
    "po_date_past_days": 90,
    "qty_anomaly_multiple": 3.0,
    "max_line_qty": 10000,
    "line_amount_abs_tol": 0.01,
    "line_amount_pct_tol": 0.5,
    "total_abs_tol": 0.02,
    "total_pct_tol": 0.1,
    "similar_order_days": 3,
    "similar_line_overlap": 0.80,
    "auto_post_min_score": 0.97,
    "auto_post_min_approved_orders": 20,
    "warn_score_penalty": 0.05,
    "max_attachment_bytes": 20 * 1024 * 1024,
    "x12_imd_max_length": 35,
}

REJECT_RULES = frozenset({"SEC-01", "DUP-01", "DUP-02"})


class ValidationEngine:
    """Esegue il catalogo di regole su un documento VOF."""

    def __init__(
        self,
        config_dir: Path | str | None = None,
        reference_data: ReferenceDataProvider | None = None,
        as_of: date | None = None,
    ) -> None:
        self.config_dir = Path(config_dir) if config_dir else _default_config_dir()
        self.reference_data = reference_data
        self.as_of = as_of or date.today()
        self.thresholds = self._load_yaml("thresholds.yaml", DEFAULT_THRESHOLDS)
        self.rules_config = self._load_yaml("rules.yaml", {})

    def _load_yaml(self, name: str, fallback: dict[str, Any]) -> dict[str, Any]:
        path = self.config_dir / name
        if not path.exists():
            return dict(fallback)
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            return dict(fallback)
        merged = dict(fallback)
        merged.update(loaded)
        return merged

    def _is_enabled(self, code: str) -> bool:
        disabled = self.rules_config.get("disabled_rules") or []
        return code not in disabled

    def _effective_severity(self, code: str, default: Severity) -> Severity:
        overrides = self.rules_config.get("severity_overrides") or {}
        if code in overrides:
            return Severity(str(overrides[code]))
        return default

    def validate(
        self,
        vof: dict[str, Any],
        *,
        document_text: str | None = None,
        declared_line_count: int | None = None,
        export_target: str | None = None,
        security: SecurityHints | None = None,
        llm_schema_attempts: int = 0,
        llm_schema_valid: bool = True,
        as_of: date | None = None,
    ) -> ValidationResult:
        """Valida un VOF e restituisce issue, score e route."""
        context = RuleContext(
            vof=vof,
            as_of=as_of or self.as_of,
            reference_data=self.reference_data,
            config=self.rules_config,
            thresholds=self.thresholds,
            document_text=document_text,
            declared_line_count=declared_line_count,
            export_target=export_target,
            security=security,
            llm_schema_attempts=llm_schema_attempts,
            llm_schema_valid=llm_schema_valid,
        )
        result = ValidationResult()
        _ensure_rules_loaded()
        for code, (func, default_severity) in get_all_rules().items():
            if not self._is_enabled(code):
                continue
            effective = self._effective_severity(code, default_severity)
            try:
                issues = func(context)
            except Exception as exc:  # noqa: BLE001 — una regola non deve far cadere il motore
                result.add_issue(
                    Issue(
                        rule_id=code,
                        severity=effective.at_least(Severity.REVIEW),
                        message=(
                            f"Errore durante l'esecuzione della regola {code}: "
                            f"{type(exc).__name__}"
                        ),
                        json_pointer="/",
                        suggestion="Verificare i dati dell'ordine",
                        from_exception=True,
                    )
                )
                continue
            for item in issues:
                item.severity = effective
                result.add_issue(item)

        result.score = self._compute_score(context, result)
        result.decision, result.reasons = self._route(context, result)
        return result

    def _compute_score(self, ctx: RuleContext, result: ValidationResult) -> float:
        """Minimo delle confidenze critiche e degli score riga, −0,05 per WARN."""
        values: list[float] = []
        evidence = ctx.evidence
        po_ev = evidence.get("/header/po_number") or {}
        if isinstance(po_ev, dict) and po_ev.get("confidence") is not None:
            values.append(float(po_ev["confidence"]))
        buyer_score = as_float(resolved(ctx.buyer).get("score"))
        if buyer_score is not None:
            values.append(buyer_score)
        for index, line in enumerate(ctx.lines):
            resolution = line.get("resolution") or {}
            line_score = as_float(resolution.get("score"))
            if line_score is not None:
                values.append(line_score)
            for field in ("quantity", "uom", "unit_price", "buyer_item_code"):
                pointer = f"/lines/{index}/{field}"
                field_ev = evidence.get(pointer) or {}
                if isinstance(field_ev, dict) and field_ev.get("confidence") is not None:
                    values.append(float(field_ev["confidence"]))
        score = min(values) if values else 1.0
        penalty = float(threshold(ctx, "warn_score_penalty", 0.05))
        warn_count = sum(1 for issue in result.issues if issue.severity == Severity.WARN)
        score -= penalty * warn_count
        return max(0.0, min(1.0, score))

    def _route(
        self, ctx: RuleContext, result: ValidationResult
    ) -> tuple[DecisionRoute, list[str]]:
        """Applica §7.1: REJECT (SEC/DUP), REVIEW, AUTO_POST simulato."""
        reject_codes = [
            issue.rule_id
            for issue in result.issues
            if issue.rule_id in REJECT_RULES and not issue.from_exception
        ]
        if reject_codes:
            return DecisionRoute.REJECT, sorted(set(reject_codes))

        blocking_or_review = [
            issue.rule_id
            for issue in result.issues
            if issue.severity in {Severity.BLOCK, Severity.REVIEW}
        ]
        if blocking_or_review:
            return DecisionRoute.REVIEW, sorted(set(blocking_or_review))

        min_score = float(threshold(ctx, "auto_post_min_score", 0.97))
        min_approved = int(threshold(ctx, "auto_post_min_approved_orders", 20))
        customer = customer_of(ctx.reference_data, ctx.vof)
        reasons: list[str] = []
        if result.score < min_score:
            reasons.append("SCORE")
        if customer is None or not customer.allowlisted:
            reasons.append("ALLOWLIST")
        if customer is None or customer.approved_orders_without_corrections < min_approved:
            reasons.append("HISTORY")
        if reasons:
            return DecisionRoute.REVIEW, reasons
        return DecisionRoute.AUTO_POST, []

    def get_decision_explanation(self, result: ValidationResult) -> str:
        """Spiega in italiano la route calcolata."""
        if result.decision == DecisionRoute.REJECT:
            return (
                "Ordine scartato: quarantena di sicurezza o duplicato esatto "
                f"({', '.join(result.reasons) or 'SEC/DUP'})."
            )
        if result.decision == DecisionRoute.REVIEW:
            return (
                "Ordine in revisione: "
                f"{', '.join(result.reasons) or 'issue BLOCK/REVIEW o AUTO_POST non ammissibile'}."
            )
        return "Ordine ammissibile per AUTO_POST (simulato nel prototipo)."


def _ensure_rules_loaded() -> None:
    """Importa i moduli di area: il decoratore ``@rule`` riempie il registro."""
    from ventureorder.rules import (  # noqa: F401
        cus,
        dup,
        exp,
        ext,
        hdr,
        itm,
        prc,
        qty,
        sec,
        tot,
        uom,
    )


def _default_config_dir() -> Path:
    """Directory ``config/`` del repo, con fallback sul CWD."""
    candidates = [Path.cwd() / "config", REPO_ROOT / "config"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path("config")
