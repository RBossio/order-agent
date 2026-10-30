"""Valutazione offline del riconoscimento su ground truth sintetico."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ventureorder.match.pipeline import apply_matches
from ventureorder.rules.reference import DatagenReferenceDataProvider

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class MatchEvalReport:
    """Precisione e copertura del riconoscimento clienti/articoli."""

    customer_total: int = 0
    customer_resolved: int = 0
    customer_correct: int = 0
    customer_incorrect: int = 0
    item_total: int = 0
    item_resolved: int = 0
    item_correct: int = 0
    item_incorrect: int = 0
    orders: int = 0
    methods_customer: dict[str, int] = field(default_factory=dict)
    methods_item: dict[str, int] = field(default_factory=dict)

    @property
    def customer_precision(self) -> float:
        """Precisione clienti: corretti / (corretti + errati) tra i risolti."""
        denom = self.customer_correct + self.customer_incorrect
        return self.customer_correct / denom if denom else 0.0

    @property
    def item_precision(self) -> float:
        """Precisione articoli: SKU corretti / (corretti + errati) tra i risolti."""
        denom = self.item_correct + self.item_incorrect
        return self.item_correct / denom if denom else 0.0

    @property
    def customer_coverage(self) -> float:
        return self.customer_resolved / self.customer_total if self.customer_total else 0.0

    @property
    def item_coverage(self) -> float:
        return self.item_resolved / self.item_total if self.item_total else 0.0

    def as_percentages(self) -> dict[str, float]:
        """Percentuali arrotondate da riportare in CLI e test."""
        return {
            "customer_precision_pct": round(self.customer_precision * 100.0, 2),
            "item_precision_pct": round(self.item_precision * 100.0, 2),
            "customer_coverage_pct": round(self.customer_coverage * 100.0, 2),
            "item_coverage_pct": round(self.item_coverage * 100.0, 2),
        }

    def summary_text(self) -> str:
        pct = self.as_percentages()
        return (
            "Riconoscimento sintetico: "
            f"clienti {pct['customer_precision_pct']:.2f}% "
            f"(copertura {pct['customer_coverage_pct']:.2f}%, "
            f"{self.customer_correct}/{self.customer_resolved} risolti), "
            f"articoli {pct['item_precision_pct']:.2f}% "
            f"(copertura {pct['item_coverage_pct']:.2f}%, "
            f"{self.item_correct}/{self.item_resolved} risolti) "
            f"su {self.orders} ordini."
        )


def strip_resolutions(vof: dict[str, Any]) -> dict[str, Any]:
    """Toglie ``buyer.resolved`` e ``line.resolution`` (ordine come estratto)."""
    payload = copy.deepcopy(vof)
    buyer = payload.get("buyer")
    if isinstance(buyer, dict):
        buyer["resolved"] = None
    for line in payload.get("lines") or []:
        if isinstance(line, dict):
            line["resolution"] = None
    return payload


def evaluate_synthetic_dataset(
    ground_truth_dir: Path | str | None = None,
    datagen_path: Path | str | None = None,
    *,
    limit: int | None = None,
) -> MatchEvalReport:
    """Misura la precisione su ``synthetic/ground_truth`` senza rete né LLM."""
    gt_dir = Path(ground_truth_dir) if ground_truth_dir else _default_gt_dir()
    master = Path(datagen_path) if datagen_path else None
    provider = DatagenReferenceDataProvider.from_datagen(datagen_path=master)
    report = MatchEvalReport()
    files = sorted(gt_dir.glob("*.json"))
    if limit is not None:
        files = files[:limit]
    for path in files:
        with path.open(encoding="utf-8") as handle:
            truth = json.load(handle)
        extracted = strip_resolutions(truth)
        apply_matches(extracted, provider, overwrite=True)
        report.orders += 1
        _score_customer(report, truth, extracted)
        _score_items(report, truth, extracted)
    return report


def _score_customer(
    report: MatchEvalReport, truth: dict[str, Any], predicted: dict[str, Any]
) -> None:
    expected = ((truth.get("buyer") or {}).get("resolved") or {}).get("erp_partner_ref")
    got_info = (predicted.get("buyer") or {}).get("resolved") or {}
    got = got_info.get("erp_partner_ref")
    method = str(got_info.get("method") or "UNRESOLVED")
    report.customer_total += 1
    if got:
        report.customer_resolved += 1
        report.methods_customer[method] = report.methods_customer.get(method, 0) + 1
        if expected and str(got) == str(expected):
            report.customer_correct += 1
        else:
            report.customer_incorrect += 1
    else:
        if expected:
            report.methods_customer["UNRESOLVED"] = report.methods_customer.get("UNRESOLVED", 0) + 1


def _score_items(report: MatchEvalReport, truth: dict[str, Any], predicted: dict[str, Any]) -> None:
    truth_lines = truth.get("lines") or []
    pred_lines = predicted.get("lines") or []
    by_no = {line.get("line_no"): line for line in pred_lines if isinstance(line, dict)}
    for truth_line in truth_lines:
        if not isinstance(truth_line, dict):
            continue
        expected = (truth_line.get("resolution") or {}).get("sku")
        report.item_total += 1
        pred_line = by_no.get(truth_line.get("line_no")) or {}
        resolution = pred_line.get("resolution") or {}
        got = resolution.get("sku")
        method = str(resolution.get("method") or "UNRESOLVED")
        if got and method != "UNRESOLVED":
            report.item_resolved += 1
            report.methods_item[method] = report.methods_item.get(method, 0) + 1
            if expected and str(got) == str(expected):
                report.item_correct += 1
            else:
                report.item_incorrect += 1
        else:
            report.methods_item["UNRESOLVED"] = report.methods_item.get("UNRESOLVED", 0) + 1


def _default_gt_dir() -> Path:
    candidates = [
        Path.cwd() / "synthetic" / "ground_truth",
        REPO_ROOT / "synthetic" / "ground_truth",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("synthetic/ground_truth non trovato.")
