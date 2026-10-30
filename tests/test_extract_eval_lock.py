"""Regressione make eval senza LLM: AUTO_POST 29/50, 0 errori silenziosi."""

from __future__ import annotations

from pathlib import Path

from extract.eval_run import EVAL_SAMPLE, EVAL_SEED, build_sample, run_sample

REPO = Path(__file__).resolve().parent.parent
GT = REPO / "synthetic" / "ground_truth"
DOCS = REPO / "synthetic" / "documents"


def test_make_eval_no_llm_auto_post_lock() -> None:
    """Stesso campione di ``make eval`` (seed 42, 50, no PDF, no LLM)."""
    sample = build_sample(
        GT,
        DOCS,
        seed=EVAL_SEED,
        sample_size=EVAL_SAMPLE,
        exclude_pdf=True,
    )
    assert len(sample) == 50
    results, _orders, errors, _elapsed = run_sample(
        sample,
        gt_dir=GT,
        docs_dir=DOCS,
        use_llm=False,
        model="mock",
        quiet=True,
    )
    assert not errors
    assert results.total_orders == 50
    assert results.auto_post_orders == 29, (
        f"AUTO_POST {results.auto_post_orders}/50 "
        f"(atteso 29/50, silent {results.silent_orders})"
    )
    assert results.silent_orders == 0
