"""Evaluation offline del riconoscimento su dataset sintetico (senza rete né LLM)."""

from __future__ import annotations

from pathlib import Path

from ventureorder.match.eval import evaluate_synthetic_dataset

REPO = Path(__file__).resolve().parent.parent


def test_synthetic_match_precision_report(capsys) -> None:
    """Calcola e riporta la precisione clienti/articoli sul ground truth sintetico."""
    report = evaluate_synthetic_dataset(
        ground_truth_dir=REPO / "synthetic" / "ground_truth",
        datagen_path=REPO / "datagen" / "master",
    )
    pct = report.as_percentages()
    print(report.summary_text())
    print(
        f"precisione clienti={pct['customer_precision_pct']:.2f}% "
        f"precisione articoli={pct['item_precision_pct']:.2f}%"
    )
    captured = capsys.readouterr()
    assert "precisione clienti" in captured.out.lower() or "clienti" in captured.out.lower()

    assert report.orders == 150
    assert report.customer_total == 150
    assert report.item_total > 0
    assert pct["customer_precision_pct"] >= 99.0
    assert pct["item_precision_pct"] >= 90.0
    assert pct["customer_coverage_pct"] >= 90.0
    assert pct["item_coverage_pct"] >= 80.0
