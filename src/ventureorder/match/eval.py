"""Valutazione offline del riconoscimento su ground truth sintetico."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from ventureorder.match.customer import CustomerMatcher
from ventureorder.match.fields import sanitize_extracted_order
from ventureorder.match.items import ItemMatcher
from ventureorder.match.models import CustomerMatch, ItemMatch
from ventureorder.match.noise import (
    NOISY_CALIBRATION_SEED,
    NOISY_EVAL_SEED,
    apply_variants,
    is_hard_case,
    select_kinds_for_order,
    variant_rng,
)
from ventureorder.rules.reference import DatagenReferenceDataProvider, ReferenceDataProvider

REPO_ROOT = Path(__file__).resolve().parents[3]
HIGH_CONFIDENCE = 0.9
REVIEW_THRESHOLD = 0.92  # soglia FUZZY alto / revisione matching
AUTO_THRESHOLD = 0.97  # auto_post_min_score


@dataclass
class MatchEvalReport:
    """Precisione, copertura, ambiguità ed errori ad alta confidenza."""

    name: str = "clean"
    customer_total: int = 0
    customer_resolved: int = 0
    customer_correct: int = 0
    customer_incorrect: int = 0
    customer_ambiguous: int = 0
    customer_high_conf_errors: int = 0
    customer_review_errors: int = 0
    customer_auto_errors: int = 0
    item_total: int = 0
    item_resolved: int = 0
    item_correct: int = 0
    item_incorrect: int = 0
    item_ambiguous: int = 0
    item_high_conf_errors: int = 0
    item_review_errors: int = 0
    item_auto_errors: int = 0
    orders: int = 0
    seed: int | None = None
    methods_customer: dict[str, int] = field(default_factory=dict)
    methods_item: dict[str, int] = field(default_factory=dict)

    @property
    def customer_precision(self) -> float:
        denom = self.customer_correct + self.customer_incorrect
        return self.customer_correct / denom if denom else 0.0

    @property
    def item_precision(self) -> float:
        denom = self.item_correct + self.item_incorrect
        return self.item_correct / denom if denom else 0.0

    @property
    def customer_coverage(self) -> float:
        return self.customer_resolved / self.customer_total if self.customer_total else 0.0

    @property
    def item_coverage(self) -> float:
        return self.item_resolved / self.item_total if self.item_total else 0.0

    @property
    def customer_ambiguous_rate(self) -> float:
        return self.customer_ambiguous / self.customer_total if self.customer_total else 0.0

    @property
    def item_ambiguous_rate(self) -> float:
        return self.item_ambiguous / self.item_total if self.item_total else 0.0

    @property
    def customer_high_conf_error_rate(self) -> float:
        return self.customer_high_conf_errors / self.customer_total if self.customer_total else 0.0

    @property
    def item_high_conf_error_rate(self) -> float:
        return self.item_high_conf_errors / self.item_total if self.item_total else 0.0

    @property
    def customer_review_error_rate(self) -> float:
        return self.customer_review_errors / self.customer_total if self.customer_total else 0.0

    @property
    def item_review_error_rate(self) -> float:
        return self.item_review_errors / self.item_total if self.item_total else 0.0

    @property
    def customer_auto_error_rate(self) -> float:
        return self.customer_auto_errors / self.customer_total if self.customer_total else 0.0

    @property
    def item_auto_error_rate(self) -> float:
        return self.item_auto_errors / self.item_total if self.item_total else 0.0

    def as_percentages(self) -> dict[str, float]:
        """Percentuali arrotondate da riportare in CLI e test."""
        return {
            "customer_precision_pct": round(self.customer_precision * 100.0, 2),
            "item_precision_pct": round(self.item_precision * 100.0, 2),
            "customer_coverage_pct": round(self.customer_coverage * 100.0, 2),
            "item_coverage_pct": round(self.item_coverage * 100.0, 2),
            "customer_ambiguous_pct": round(self.customer_ambiguous_rate * 100.0, 2),
            "item_ambiguous_pct": round(self.item_ambiguous_rate * 100.0, 2),
            "customer_high_conf_error_pct": round(self.customer_high_conf_error_rate * 100.0, 2),
            "item_high_conf_error_pct": round(self.item_high_conf_error_rate * 100.0, 2),
            "customer_review_error_pct": round(self.customer_review_error_rate * 100.0, 2),
            "item_review_error_pct": round(self.item_review_error_rate * 100.0, 2),
            "customer_auto_error_pct": round(self.customer_auto_error_rate * 100.0, 2),
            "item_auto_error_pct": round(self.item_auto_error_rate * 100.0, 2),
        }

    def summary_text(self) -> str:
        pct = self.as_percentages()
        return (
            f"[{self.name}] clienti prec {pct['customer_precision_pct']:.2f}% "
            f"cop {pct['customer_coverage_pct']:.2f}% "
            f"amb {pct['customer_ambiguous_pct']:.2f}% "
            f"err≥0.9 {pct['customer_high_conf_error_pct']:.2f}% "
            f"err≥REVIEW {pct['customer_review_error_pct']:.2f}% "
            f"err≥AUTO {pct['customer_auto_error_pct']:.2f}% "
            f"| articoli prec {pct['item_precision_pct']:.2f}% "
            f"cop {pct['item_coverage_pct']:.2f}% "
            f"amb {pct['item_ambiguous_pct']:.2f}% "
            f"err≥0.9 {pct['item_high_conf_error_pct']:.2f}% "
            f"err≥REVIEW {pct['item_review_error_pct']:.2f}% "
            f"err≥AUTO {pct['item_auto_error_pct']:.2f}% "
            f"| {self.orders} ordini" + (f" seed={self.seed}" if self.seed is not None else "")
        )


def load_match_thresholds() -> dict[str, Any]:
    """Soglie da ``config/thresholds.yaml`` (fallback: default del matcher)."""
    path = REPO_ROOT / "config" / "thresholds.yaml"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def evaluate_synthetic_dataset(
    ground_truth_dir: Path | str | None = None,
    datagen_path: Path | str | None = None,
    *,
    limit: int | None = None,
    thresholds: dict[str, Any] | None = None,
) -> MatchEvalReport:
    """Set pulito: campi estratti sanitizzati, senza ID attesi."""
    truths, provider = _load(ground_truth_dir, datagen_path, limit)
    return _evaluate_truths(truths, provider, name="clean", thresholds=thresholds)


def evaluate_noisy_dataset(
    ground_truth_dir: Path | str | None = None,
    datagen_path: Path | str | None = None,
    *,
    seed: int = NOISY_EVAL_SEED,
    limit: int | None = None,
    thresholds: dict[str, Any] | None = None,
) -> MatchEvalReport:
    """Set rumoroso: casi difficili + varianti a seed fisso."""
    truths, provider = _load(ground_truth_dir, datagen_path, limit=None)
    merged = {**load_match_thresholds(), **(thresholds or {})}
    customer_matcher = CustomerMatcher(provider, merged)
    item_matcher = ItemMatcher(provider, merged)
    report = MatchEvalReport(name="noisy", seed=seed)
    cases = list(_iter_noisy_cases(truths, seed=seed))
    if limit is not None:
        cases = cases[:limit]
    for truth, extracted, _kinds in cases:
        _evaluate_one(report, truth, extracted, customer_matcher, item_matcher)
    return report


FUZZY_CALIBRATION_GRID: tuple[dict[str, float], ...] = (
    {"item_fuzzy_cap": 0.85, "item_fuzzy_confirm_min": 2, "item_fuzzy_margin": 0.08},
    {"item_fuzzy_cap": 0.85, "item_fuzzy_confirm_min": 1, "item_fuzzy_margin": 0.08},
    {"item_fuzzy_cap": 0.80, "item_fuzzy_confirm_min": 2, "item_fuzzy_margin": 0.08},
    {"item_fuzzy_cap": 0.85, "item_fuzzy_confirm_min": 2, "item_fuzzy_margin": 0.10},
)


def calibrate_fuzzy_thresholds(
    ground_truth_dir: Path | str | None = None,
    datagen_path: Path | str | None = None,
    *,
    seed: int = NOISY_CALIBRATION_SEED,
) -> tuple[dict[str, float], MatchEvalReport, list[tuple[dict[str, float], MatchEvalReport]]]:
    """Sceglie le soglie FUZZY sul set rumoroso di taratura (seed 7).

    Criterio: errori ≥ 0,9 ≤ 1%, poi massima copertura articoli, poi precisione.
    """
    base = load_match_thresholds()
    ranked: list[tuple[dict[str, float], MatchEvalReport]] = []
    for extra in FUZZY_CALIBRATION_GRID:
        merged = {**base, **extra}
        report = evaluate_noisy_dataset(
            ground_truth_dir=ground_truth_dir,
            datagen_path=datagen_path,
            seed=seed,
            thresholds=merged,
        )
        ranked.append((dict(extra), report))
    ranked.sort(
        key=lambda item: (
            item[1].item_high_conf_error_rate,
            -item[1].item_coverage,
            -item[1].item_precision,
        )
    )
    chosen, report = ranked[0]
    if report.item_high_conf_error_rate > 0.01:
        # Nessuna combinazione sotto l'1%: si tiene il cap più conservativo.
        chosen = dict(FUZZY_CALIBRATION_GRID[0])
        report = ranked[0][1]
    return chosen, report, ranked


def _load(
    ground_truth_dir: Path | str | None,
    datagen_path: Path | str | None,
    limit: int | None,
) -> tuple[list[dict[str, Any]], ReferenceDataProvider]:
    gt_dir = Path(ground_truth_dir) if ground_truth_dir else _default_gt_dir()
    master = Path(datagen_path) if datagen_path else None
    provider = DatagenReferenceDataProvider.from_datagen(datagen_path=master)
    files = sorted(gt_dir.glob("*.json"))
    if limit is not None:
        files = files[:limit]
    truths: list[dict[str, Any]] = []
    for path in files:
        with path.open(encoding="utf-8") as handle:
            truths.append(json.load(handle))
    return truths, provider


def _evaluate_truths(
    truths: list[dict[str, Any]],
    provider: ReferenceDataProvider,
    *,
    name: str,
    thresholds: dict[str, Any] | None = None,
) -> MatchEvalReport:
    merged = {**load_match_thresholds(), **(thresholds or {})}
    customer_matcher = CustomerMatcher(provider, merged)
    item_matcher = ItemMatcher(provider, merged)
    report = MatchEvalReport(name=name)
    for truth in truths:
        extracted = sanitize_extracted_order(truth)
        _evaluate_one(report, truth, extracted, customer_matcher, item_matcher)
    return report


def _iter_noisy_cases(
    truths: list[dict[str, Any]],
    *,
    seed: int,
) -> list[tuple[dict[str, Any], dict[str, Any], list[str]]]:
    cases: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
    for index, truth in enumerate(truths):
        order_id = str(truth.get("order_id") or index)
        hard = is_hard_case(truth)
        rng = variant_rng(seed, order_id, "variant")
        kinds = select_kinds_for_order(index, hard=False, rng=rng)
        extracted = apply_variants(sanitize_extracted_order(truth), kinds, rng)
        cases.append((truth, extracted, kinds))
        if hard:
            rng_h = variant_rng(seed, order_id, "hard")
            hard_kinds = select_kinds_for_order(index, hard=True, rng=rng_h)
            noisy = apply_variants(sanitize_extracted_order(truth), hard_kinds, rng_h)
            cases.append((truth, noisy, hard_kinds))
    return cases


def _evaluate_one(
    report: MatchEvalReport,
    truth: dict[str, Any],
    extracted: dict[str, Any],
    customer_matcher: CustomerMatcher,
    item_matcher: ItemMatcher,
) -> None:
    report.orders += 1
    customer_match = customer_matcher.resolve(extracted)
    expected_ref = ((truth.get("buyer") or {}).get("resolved") or {}).get("erp_partner_ref")
    _score_customer(report, expected_ref, customer_match)
    customer_ref = (
        customer_match.customer.erp_partner_ref
        if customer_match.resolved and customer_match.customer
        else None
    )
    pred_lines = extracted.get("lines") or []
    truth_lines = truth.get("lines") or []
    by_no = {line.get("line_no"): line for line in pred_lines if isinstance(line, dict)}
    for truth_line in truth_lines:
        if not isinstance(truth_line, dict):
            continue
        expected_sku = (truth_line.get("resolution") or {}).get("sku")
        pred_line = by_no.get(truth_line.get("line_no")) or {}
        item_match = item_matcher.resolve(
            pred_line if isinstance(pred_line, dict) else {},
            customer_ref,
        )
        _score_item(report, expected_sku, item_match)


def _score_customer(report: MatchEvalReport, expected_ref: Any, match: CustomerMatch) -> None:
    report.customer_total += 1
    if match.ambiguous:
        report.customer_ambiguous += 1
        report.methods_customer["AMBIGUOUS"] = report.methods_customer.get("AMBIGUOUS", 0) + 1
        return
    if not match.resolved or match.customer is None:
        report.methods_customer["UNRESOLVED"] = report.methods_customer.get("UNRESOLVED", 0) + 1
        return
    report.customer_resolved += 1
    report.methods_customer[match.method] = report.methods_customer.get(match.method, 0) + 1
    got = match.customer.erp_partner_ref
    if expected_ref and str(got) == str(expected_ref):
        report.customer_correct += 1
    else:
        report.customer_incorrect += 1
        _tally_threshold_errors(report, match.score, kind="customer")


def _score_item(report: MatchEvalReport, expected_sku: Any, match: ItemMatch) -> None:
    report.item_total += 1
    predicted = match.product.sku if match.product is not None else None
    wrong = bool(predicted and expected_sku and str(predicted) != str(expected_sku))
    if match.ambiguous:
        report.item_ambiguous += 1
        report.methods_item["AMBIGUOUS"] = report.methods_item.get("AMBIGUOUS", 0) + 1
        if wrong:
            _tally_threshold_errors(report, match.score, kind="item")
        return
    if match.method == "UNRESOLVED" or predicted is None:
        report.methods_item["UNRESOLVED"] = report.methods_item.get("UNRESOLVED", 0) + 1
        return
    report.item_resolved += 1
    report.methods_item[match.method] = report.methods_item.get(match.method, 0) + 1
    if expected_sku and str(predicted) == str(expected_sku):
        report.item_correct += 1
    else:
        report.item_incorrect += 1
        _tally_threshold_errors(report, match.score, kind="item")


def _tally_threshold_errors(report: MatchEvalReport, score: float, *, kind: str) -> None:
    """Conta errori ≥0,9, ≥REVIEW (0,92) e ≥AUTO (0,97)."""
    if kind == "item":
        if score >= HIGH_CONFIDENCE:
            report.item_high_conf_errors += 1
        if score >= REVIEW_THRESHOLD:
            report.item_review_errors += 1
        if score >= AUTO_THRESHOLD:
            report.item_auto_errors += 1
        return
    if score >= HIGH_CONFIDENCE:
        report.customer_high_conf_errors += 1
    if score >= REVIEW_THRESHOLD:
        report.customer_review_errors += 1
    if score >= AUTO_THRESHOLD:
        report.customer_auto_errors += 1


def _default_gt_dir() -> Path:
    candidates = [
        Path.cwd() / "synthetic" / "ground_truth",
        REPO_ROOT / "synthetic" / "ground_truth",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("synthetic/ground_truth non trovato.")
