"""Evaluation offline pulita e rumorosa (senza rete né LLM)."""

from __future__ import annotations

from pathlib import Path

from ventureorder.match.eval import (
    calibrate_fuzzy_thresholds,
    evaluate_noisy_dataset,
    evaluate_synthetic_dataset,
    load_match_thresholds,
)
from ventureorder.match.noise import NOISY_CALIBRATION_SEED, NOISY_EVAL_SEED

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
    "customer_review_error_pct",
    "item_review_error_pct",
    "customer_auto_error_pct",
    "item_auto_error_pct",
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
        f"{pct['item_high_conf_error_pct']:.2f}% "
        f"err>=REVIEW={pct['customer_review_error_pct']:.2f}%/"
        f"{pct['item_review_error_pct']:.2f}% "
        f"err>=AUTO={pct['customer_auto_error_pct']:.2f}%/"
        f"{pct['item_auto_error_pct']:.2f}%"
    )
    return pct


def test_clean_and_noisy_match_eval_report(capsys) -> None:
    """Riporta precisione, copertura, ambigui ed errori sulle soglie."""
    clean = evaluate_synthetic_dataset(ground_truth_dir=GT, datagen_path=MASTER)
    noisy = evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_EVAL_SEED)
    cal = evaluate_noisy_dataset(
        ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_CALIBRATION_SEED
    )
    clean_pct = _print_report(clean)
    noisy_pct = _print_report(noisy)
    cal_pct = _print_report(cal)
    captured = capsys.readouterr()
    assert "prec" in captured.out.lower() or "clienti" in captured.out.lower()

    for key in METRIC_KEYS:
        assert key in clean_pct
        assert key in noisy_pct
        assert key in cal_pct

    assert clean.name == "clean"
    assert noisy.name == "noisy"
    assert cal.name == "noisy"
    assert noisy.seed == NOISY_EVAL_SEED
    assert cal.seed == NOISY_CALIBRATION_SEED
    assert clean.orders == 150
    assert noisy.orders >= 150
    assert noisy.orders > clean.orders
    assert clean.item_total > 0
    assert noisy.item_total > 0

    assert clean_pct["customer_precision_pct"] >= 99.0
    assert clean_pct["item_precision_pct"] >= 90.0
    assert clean_pct["customer_high_conf_error_pct"] == 0.0
    assert clean_pct["item_high_conf_error_pct"] < 1.0

    noisy_is_harder = (
        noisy_pct["item_coverage_pct"] < clean_pct["item_coverage_pct"]
        or noisy_pct["customer_coverage_pct"] < clean_pct["customer_coverage_pct"]
        or noisy_pct["item_ambiguous_pct"] > clean_pct["item_ambiguous_pct"]
        or noisy_pct["item_precision_pct"] < clean_pct["item_precision_pct"]
    )
    assert noisy_is_harder


def test_noisy_high_conf_item_errors_at_most_one_percent() -> None:
    """Regressione: sul rumoroso gli errori articoli ≥0,9 restano ≤ 1%."""
    noisy = evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_EVAL_SEED)
    pct = noisy.as_percentages()
    print(
        f"seed={NOISY_EVAL_SEED} err>=0.9 articoli={pct['item_high_conf_error_pct']:.2f}% "
        f"err>=REVIEW={pct['item_review_error_pct']:.2f}% "
        f"err>=AUTO={pct['item_auto_error_pct']:.2f}%"
    )
    assert pct["item_high_conf_error_pct"] <= 1.0
    assert pct["customer_high_conf_error_pct"] <= 1.0


def test_calibration_seed_high_conf_and_auto_review_errors() -> None:
    """Taratura seed 7: errori ≥0,9 e sopra AUTO/REVIEW, poi valida le soglie yaml."""
    chosen, cal_report, grid = calibrate_fuzzy_thresholds(
        ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_CALIBRATION_SEED
    )
    locked = load_match_thresholds()
    for key, value in chosen.items():
        assert float(locked[key]) == float(value)

    cal_pct = cal_report.as_percentages()
    print(f"taratura seed={NOISY_CALIBRATION_SEED} soglie={chosen}")
    print(
        f"err>=0.9={cal_pct['item_high_conf_error_pct']:.2f}% "
        f"err>=REVIEW={cal_pct['item_review_error_pct']:.2f}% "
        f"err>=AUTO={cal_pct['item_auto_error_pct']:.2f}%"
    )
    assert cal_pct["item_high_conf_error_pct"] <= 1.0
    assert cal_pct["item_review_error_pct"] <= 1.0
    assert cal_pct["item_auto_error_pct"] <= 1.0
    assert grid
    # Validazione seed 42 (stesse soglie yaml).
    valid = evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_EVAL_SEED)
    valid_pct = valid.as_percentages()
    print(
        f"validazione seed={NOISY_EVAL_SEED} "
        f"err>=0.9={valid_pct['item_high_conf_error_pct']:.2f}% "
        f"err>=REVIEW={valid_pct['item_review_error_pct']:.2f}% "
        f"err>=AUTO={valid_pct['item_auto_error_pct']:.2f}%"
    )
    assert valid_pct["item_high_conf_error_pct"] <= 1.0
    assert valid_pct["item_review_error_pct"] <= 1.0
    assert valid_pct["item_auto_error_pct"] <= 1.0
