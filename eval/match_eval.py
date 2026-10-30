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
    calibrate_fuzzy_thresholds,
    evaluate_noisy_dataset,
    evaluate_synthetic_dataset,
)
from ventureorder.match.noise import (  # noqa: E402
    NOISY_CALIBRATION_SEED,
    NOISY_EVAL_SEED,
)


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
        "customer_review_errors": report.customer_review_errors,
        "customer_auto_errors": report.customer_auto_errors,
        "item_total": report.item_total,
        "item_resolved": report.item_resolved,
        "item_correct": report.item_correct,
        "item_ambiguous": report.item_ambiguous,
        "item_high_conf_errors": report.item_high_conf_errors,
        "item_review_errors": report.item_review_errors,
        "item_auto_errors": report.item_auto_errors,
        "item_proposed": report.item_proposed,
        "item_proposed_correct": report.item_proposed_correct,
        "item_ambiguous_wrong": report.item_ambiguous_wrong,
        "seed": report.seed,
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
        help="Quale evaluation eseguire (default: pulito + rumoroso 42 e 7).",
    )
    parser.add_argument(
        "--seed", type=int, default=NOISY_EVAL_SEED, help="Seed delle varianti rumorose."
    )
    parser.add_argument(
        "--calibrate-seed",
        type=int,
        default=NOISY_CALIBRATION_SEED,
        help="Seed di taratura (default 7).",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Sceglie le soglie FUZZY sul seed di taratura e stampa la griglia.",
    )
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON.")
    args = parser.parse_args()

    if args.calibrate:
        chosen, cal_report, grid = calibrate_fuzzy_thresholds(
            ground_truth_dir=args.ground_truth,
            datagen_path=args.datagen,
            seed=args.calibrate_seed,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "chosen": chosen,
                        "calibration": _payload(cal_report),
                        "grid": [{"thresholds": extra, **_payload(rep)} for extra, rep in grid],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"soglie scelte sul seed {args.calibrate_seed}: {chosen}")
            print(cal_report.summary_text())
            for extra, rep in grid:
                pct = rep.as_percentages()
                print(
                    f"  {extra} → err≥0.9 {pct['item_high_conf_error_pct']:.2f}% "
                    f"cop {pct['item_coverage_pct']:.2f}%"
                )
        return 0

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
        if args.which == "both" and args.seed != args.calibrate_seed:
            reports.append(
                evaluate_noisy_dataset(
                    ground_truth_dir=args.ground_truth,
                    datagen_path=args.datagen,
                    seed=args.calibrate_seed,
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
                f"prec.escl.amb {pct['item_precision_excl_ambiguous_pct']:.2f}%  "
                f"acc.proposti {pct['item_proposed_accuracy_pct']:.2f}%  |  "
                f"errori ≥0.9 {pct['customer_high_conf_error_pct']:.2f}% / "
                f"{pct['item_high_conf_error_pct']:.2f}%  |  "
                f"err≥REVIEW {pct['customer_review_error_pct']:.2f}% / "
                f"{pct['item_review_error_pct']:.2f}%  |  "
                f"err≥AUTO {pct['customer_auto_error_pct']:.2f}% / "
                f"{pct['item_auto_error_pct']:.2f}%  |  "
                f"amb.sbagliate {report.item_ambiguous_wrong} "
                f"recall@3 {pct['item_recall_at_3_pct']:.2f}%"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
