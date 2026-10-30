"""Evaluation offline pulita e rumorosa (senza rete né LLM)."""

from __future__ import annotations

from pathlib import Path

from ventureorder.match.eval import (
    calibrate_fuzzy_thresholds,
    evaluate_noisy_dataset,
    evaluate_synthetic_dataset,
    load_match_thresholds,
)
from ventureorder.match.noise import (
    NOISY_CALIBRATION_SEED,
    NOISY_CALIBRATION_SEEDS,
    NOISY_EVAL_SEED,
)

REPO = Path(__file__).resolve().parent.parent
GT = REPO / "synthetic" / "ground_truth"
MASTER = REPO / "datagen" / "master"

METRIC_KEYS = (
    "customer_precision_pct",
    "item_precision_excl_ambiguous_pct",
    "item_precision_pct",
    "item_proposed_accuracy_pct",
    "item_ambiguous_wrong",
    "item_ambiguous_wrong_pct",
    "item_recall_at_3_pct",
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

# Target errori senza avviso ≤ 1%; si richiede 1 punto di margine → ≤ 0%.
SILENT_ERROR_MAX_PCT = 0.0


def _print_report(report) -> dict[str, float]:
    pct = report.as_percentages()
    print(report.summary_text())
    print(
        f"precisione esclusi gli ambigui clienti={pct['customer_precision_pct']:.2f}% "
        f"articoli={pct['item_precision_excl_ambiguous_pct']:.2f}% "
        f"acc.proposti={pct['item_proposed_accuracy_pct']:.2f}% "
        f"copertura={pct['customer_coverage_pct']:.2f}%/{pct['item_coverage_pct']:.2f}% "
        f"ambigui={pct['customer_ambiguous_pct']:.2f}%/{pct['item_ambiguous_pct']:.2f}% "
        f"amb.sbagliate={int(pct['item_ambiguous_wrong'])} "
        f"({pct['item_ambiguous_wrong_pct']:.2f}%) "
        f"recall@3={pct['item_recall_at_3_pct']:.2f}% "
        f"errori>=0.9={pct['customer_high_conf_error_pct']:.2f}%/"
        f"{pct['item_high_conf_error_pct']:.2f}%"
    )
    return pct


def test_clean_and_noisy_match_eval_report(capsys) -> None:
    """Riporta precisione esclusi gli ambigui, accuratezza sui proposti, top-3."""
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
    assert noisy.seed == NOISY_EVAL_SEED
    assert clean.orders == 150
    assert noisy.orders > clean.orders
    assert clean.item_total > 0
    assert noisy.item_total > 0
    assert noisy.item_proposed > 0

    assert clean_pct["customer_precision_pct"] >= 99.0
    assert clean_pct["item_precision_excl_ambiguous_pct"] >= 90.0
    assert clean_pct["item_high_conf_error_pct"] <= SILENT_ERROR_MAX_PCT
    print(
        f"ambigue sbagliate seed {NOISY_EVAL_SEED}: {noisy.item_ambiguous_wrong} "
        f"su {noisy.item_ambiguous}"
    )
    assert noisy.item_ambiguous_wrong >= 0

    noisy_is_harder = (
        noisy_pct["item_coverage_pct"] < clean_pct["item_coverage_pct"]
        or noisy_pct["customer_coverage_pct"] < clean_pct["customer_coverage_pct"]
        or noisy_pct["item_ambiguous_pct"] > clean_pct["item_ambiguous_pct"]
        or noisy_pct["item_proposed_accuracy_pct"] < clean_pct["item_proposed_accuracy_pct"]
    )
    assert noisy_is_harder


def test_noisy_high_conf_item_errors_at_most_one_percent() -> None:
    """Regressione: errori articoli ≥0,9 sul rumoroso, con 1% di margine sul target."""
    noisy = evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=NOISY_EVAL_SEED)
    pct = noisy.as_percentages()
    print(
        f"seed={NOISY_EVAL_SEED} err>=0.9 articoli={pct['item_high_conf_error_pct']:.2f}% "
        f"acc.proposti={pct['item_proposed_accuracy_pct']:.2f}% "
        f"amb.sbagliate={noisy.item_ambiguous_wrong} "
        f"recall@3={pct['item_recall_at_3_pct']:.2f}%"
    )
    assert pct["item_high_conf_error_pct"] <= SILENT_ERROR_MAX_PCT
    assert pct["customer_high_conf_error_pct"] <= SILENT_ERROR_MAX_PCT
    assert pct["item_auto_error_pct"] <= SILENT_ERROR_MAX_PCT


def test_calibration_seed_high_conf_and_auto_review_errors() -> None:
    """Taratura su più seed; validate yaml e holdout 42."""
    chosen, cal_report, grid = calibrate_fuzzy_thresholds(
        ground_truth_dir=GT,
        datagen_path=MASTER,
        seed=NOISY_CALIBRATION_SEED,
        seeds=(NOISY_CALIBRATION_SEED,),
    )
    locked = load_match_thresholds()
    for key, value in chosen.items():
        assert float(locked[key]) == float(value)

    for seed in (*NOISY_CALIBRATION_SEEDS, NOISY_EVAL_SEED):
        report = (
            cal_report
            if seed == NOISY_CALIBRATION_SEED
            else evaluate_noisy_dataset(ground_truth_dir=GT, datagen_path=MASTER, seed=seed)
        )
        pct = report.as_percentages()
        print(
            f"seed={seed} err>=0.9={pct['item_high_conf_error_pct']:.2f}% "
            f"err>=REVIEW={pct['item_review_error_pct']:.2f}% "
            f"err>=AUTO={pct['item_auto_error_pct']:.2f}% "
            f"acc.proposti={pct['item_proposed_accuracy_pct']:.2f}% "
            f"amb.sbagliate={report.item_ambiguous_wrong} "
            f"recall@3={pct['item_recall_at_3_pct']:.2f}%"
        )
        assert pct["item_high_conf_error_pct"] <= SILENT_ERROR_MAX_PCT
        assert pct["item_review_error_pct"] <= SILENT_ERROR_MAX_PCT
        assert pct["item_auto_error_pct"] <= SILENT_ERROR_MAX_PCT
    assert grid
