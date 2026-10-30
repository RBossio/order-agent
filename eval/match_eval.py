#!/usr/bin/env python3
"""Valutazione offline del riconoscimento clienti e articoli.

Usa solo dati sintetici in-repo (datagen/master + synthetic/ground_truth).
Nessuna chiamata di rete e nessun LLM.

Uso:
    python eval/match_eval.py
    python eval/match_eval.py --limit 20
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

from ventureorder.match.eval import evaluate_synthetic_dataset  # noqa: E402


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
    parser.add_argument("--limit", type=int, default=None, help="Massimo numero di ordini.")
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON.")
    args = parser.parse_args()

    report = evaluate_synthetic_dataset(
        ground_truth_dir=args.ground_truth,
        datagen_path=args.datagen,
        limit=args.limit,
    )
    if args.json:
        payload = {
            **report.as_percentages(),
            "orders": report.orders,
            "customer_total": report.customer_total,
            "customer_resolved": report.customer_resolved,
            "customer_correct": report.customer_correct,
            "item_total": report.item_total,
            "item_resolved": report.item_resolved,
            "item_correct": report.item_correct,
            "methods_customer": report.methods_customer,
            "methods_item": report.methods_item,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(report.summary_text())
        pct = report.as_percentages()
        print(
            f"  precisione clienti: {pct['customer_precision_pct']:.2f}%  "
            f"precisione articoli: {pct['item_precision_pct']:.2f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
