"""Evaluation offline pulita e rumorosa (senza rete né LLM)."""

from __future__ import annotations

from pathlib import Path

from ventureorder.match.eval import evaluate_noisy_dataset, evaluate_synthetic_dataset
from ventureorder.match.noise import NOISY_EVAL_SEED

REPO = Path(__file__).resolve().parent.parent
GT = REPO / "synthetic" / "ground_truth"
MASTER = REPO / "datagen" / "master"

METRIC_KEYS = (
    "customer_precision_pct",
    "item_precision_pct",
    "customer_coverage_pct",
    "item_coverage_pct",
    "customer_ambiguous_pct",
    "item_ambiguous_pct",
    "customer_high_conf_error_pct",
    "item_high_conf_error_pct",
)


def _print_report(report) -> dict[str, float]:
    pct = report.as_percentages()
    print(report.summary_text())
    print(
        f"precisione clienti={pct['customer_precision_pct']:.2f}% "
        f"articoli={pct['item_precision_pct']:.2f}% "
        f"copertura={pct['customer_coverage_pct']:.2f}%/{pct['item_coverage_pct']:.2f}% "
        f"ambigui={pct['customer_ambiguous_pct']:.2f}%/{pct['item_ambiguous_pct']:.2f}% "
        f"errori>=0.9={pct['customer_high_conf_error_pct']:.2f}%/"
        f"{pct['item_high_conf_error_pct']:.2f}%"
    )
    return pct


def test_clean_and_noisy_match_eval_report(capsys) -> None:
    """Riporta precisione, copertura, ambigui ed errori ≥0,9 sui due set."""
    clean = evaluate_synthetic_dataset(ground_truth_dir=GT, datagen_path=MASTER)
    noisy = evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_EVAL_SEED)
    clean_pct = _print_report(clean)
    noisy_pct = _print_report(noisy)
    captured = capsys.readouterr()
    assert "prec" in captured.out.lower() or "clienti" in captured.out.lower()

    for key in METRIC_KEYS:
        assert key in clean_pct
        assert key in noisy_pct

    assert clean.name == "clean"
    assert noisy.name == "noisy"
    assert clean.orders == 150
    assert noisy.orders >= 150
    assert noisy.orders > clean.orders  # copie extra dei casi difficili
    assert clean.item_total > 0
    assert noisy.item_total > 0

    # Set pulito: i campi estratti coincidono col master, ma senza ID attesi.
    assert clean_pct["customer_precision_pct"] >= 99.0
    assert clean_pct["item_precision_pct"] >= 90.0
    assert clean_pct["customer_high_conf_error_pct"] == 0.0
    assert clean_pct["item_high_conf_error_pct"] < 1.0

    # Set rumoroso: non è una copia del ground truth (altrimenti 100% ovunque).
    noisy_is_harder = (
        noisy_pct["item_coverage_pct"] < clean_pct["item_coverage_pct"]
        or noisy_pct["customer_coverage_pct"] < clean_pct["customer_coverage_pct"]
        or noisy_pct["item_ambiguous_pct"] > clean_pct["item_ambiguous_pct"]
        or noisy_pct["item_precision_pct"] < clean_pct["item_precision_pct"]
    )
    assert noisy_is_harder
