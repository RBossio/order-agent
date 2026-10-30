#!/usr/bin/env python3
"""Valutazione offline del riconoscimento clienti e articoli.

Usa solo dati sintetici in-repo (datagen/master + synthetic/ground_truth).
Nessuna chiamata di rete e nessun LLM.

Il matcher non legge gli ID attesi (customer_id / sku già risolti).
Vedi ``ventureorder.match.fields``.

Uso:
    python eval/match_eval.py
    python eval/match_eval.py --set noisy
    python eval/match_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(REPO_ROOT))

from ventureorder.match.eval import (  # noqa: E402
    MatchEvalReport,
    evaluate_noisy_dataset,
    evaluate_synthetic_dataset,
)
from ventureorder.match.noise import NOISY_EVAL_SEED  # noqa: E402


def _payload(report: MatchEvalReport) -> dict:
    return {
        "name": report.name,
        **report.as_percentages(),
        "orders": report.orders,
        "customer_total": report.customer_total,
        "customer_resolved": report.customer_resolved,
        "customer_correct": report.customer_correct,
        "customer_ambiguous": report.customer_ambiguous,
        "customer_high_conf_errors": report.customer_high_conf_errors,
        "item_total": report.item_total,
        "item_resolved": report.item_resolved,
        "item_correct": report.item_correct,
        "item_ambiguous": report.item_ambiguous,
        "item_high_conf_errors": report.item_high_conf_errors,
        "methods_customer": report.methods_customer,
        "methods_item": report.methods_item,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precisione del riconoscimento clienti/articoli sul dataset sintetico.",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=REPO_ROOT / "synthetic" / "ground_truth",
        help="Cartella dei JSON di ground truth.",
    )
    parser.add_argument(
        "--datagen",
        type=Path,
        default=REPO_ROOT / "datagen" / "master",
        help="Cartella datagen/master.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Massimo numero di ordini (set pulito)."
    )
    parser.add_argument(
        "--set",
        dest="which",
        choices=["clean", "noisy", "both"],
        default="both",
        help="Quale evaluation eseguire (default: entrambe).",
    )
    parser.add_argument(
        "--seed", type=int, default=NOISY_EVAL_SEED, help="Seed delle varianti rumorose."
    )
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON.")
    args = parser.parse_args()

    reports: list[MatchEvalReport] = []
    if args.which in {"clean", "both"}:
        reports.append(
            evaluate_synthetic_dataset(
                ground_truth_dir=args.ground_truth,
                datagen_path=args.datagen,
                limit=args.limit,
            )
        )
    if args.which in {"noisy", "both"}:
        reports.append(
            evaluate_noisy_dataset(
                ground_truth_dir=args.ground_truth,
                datagen_path=args.datagen,
                seed=args.seed,
            )
        )

    if args.json:
        print(json.dumps([_payload(r) for r in reports], indent=2, ensure_ascii=False))
    else:
        for report in reports:
            print(report.summary_text())
            pct = report.as_percentages()
            print(
                f"  [{report.name}] precisione clienti {pct['customer_precision_pct']:.2f}%  "
                f"articoli {pct['item_precision_pct']:.2f}%  |  "
                f"copertura {pct['customer_coverage_pct']:.2f}% / {pct['item_coverage_pct']:.2f}%  |  "
                f"ambigui {pct['customer_ambiguous_pct']:.2f}% / {pct['item_ambiguous_pct']:.2f}%  |  "
                f"errori ≥0.9 {pct['customer_high_conf_error_pct']:.2f}% / "
                f"{pct['item_high_conf_error_pct']:.2f}%"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
