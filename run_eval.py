#!/usr/bin/env python3
"""Valutazione stratificata ingest -> extract con Ollama."""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract import OrderExtractor
from extract.backends import OllamaBackend
from extract.eval import (
    EvalResults,
    _find_document,
    _update_results,
    evaluate_order,
    generate_report,
)
from ingest import Ingestor

MODEL = "qwen2.5:3b-instruct"
HARDWARE = "Intel Xeon 4 cores, 15GB RAM, CPU-only (no GPU)"
SAMPLE_SIZE = 50


def build_sample(gt_dir: Path) -> list[str]:
    random.seed(42)
    hard, normal = [], []
    for path in sorted(gt_dir.glob("order_*.json")):
        data = json.loads(path.read_text())
        meta = data.get("_synthetic_metadata", {})
        if meta.get("is_hard_case"):
            hard.append(path.stem)
        else:
            normal.append(path.stem)
    remaining = max(0, SAMPLE_SIZE - len(hard))
    sample = list(hard) + random.sample(normal, min(remaining, len(normal)))
    return sample


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)

    gt_dir = Path("synthetic/ground_truth")
    docs_dir = Path("synthetic/documents")
    sample_names = build_sample(gt_dir)

    print(f"Valutazione su {len(sample_names)} ordini (tutti i casi difficili + campionamento)", flush=True)
    print(f"Modello: {MODEL}", flush=True)
    print(f"Hardware: {HARDWARE}", flush=True)
    print("Parametri: temperature=0, repeat_penalty=1.1, num_predict=2048, format=json", flush=True)
    print(flush=True)

    backend = OllamaBackend(model=MODEL, timeout=90.0)
    if not backend.is_available():
        print("ERRORE: Ollama non disponibile", file=sys.stderr)
        return 1

    extractor = OrderExtractor(backend=backend, max_retries=0, validate_output=False)
    ingestor = Ingestor()
    results = EvalResults()
    errors: list[tuple[str, str]] = []
    start_time = time.time()

    for idx, order_name in enumerate(sample_names, 1):
        gt_file = gt_dir / f"{order_name}.json"
        ground_truth = json.loads(gt_file.read_text())
        doc_path = _find_document(docs_dir, order_name)
        if not doc_path:
            errors.append((order_name, "documento non trovato"))
            print(f"[{idx}/{len(sample_names)}] [ERR] {order_name}: documento non trovato", flush=True)
            continue

        t0 = time.time()
        try:
            normalized = ingestor.ingest(doc_path)
            extraction_result = extractor.extract(normalized.to_dict())
            extracted = extraction_result.to_dict()
            order_score = evaluate_order(extracted, ground_truth, str(doc_path))
            order_score.extraction_time_ms = extraction_result.extraction_time_ms
            order_score.llm_calls = extraction_result.llm_calls
            llm_failed = any(
                w.message.startswith("Errore LLM:") for w in extraction_result.warnings
            )
            if llm_failed:
                order_score.extraction_failed = True
                order_score.failure_reason = next(
                    w.message for w in extraction_result.warnings
                    if w.message.startswith("Errore LLM:")
                )
                errors.append((order_name, order_score.failure_reason))
            _update_results(results, order_score, ground_truth)
            elapsed = time.time() - t0
            status = "ERR" if llm_failed else ("OK" if order_score.header_accuracy() >= 0.75 else "WARN")
            kind = "HARD" if order_score.is_hard_case else "NORM"
            print(
                f"[{idx}/{len(sample_names)}] [{status}] [{kind}] {order_name}: "
                f"H={100*order_score.header_accuracy():.0f}% "
                f"L={order_score.lines_matched}/{order_score.lines_expected} "
                f"({elapsed:.1f}s)",
                flush=True,
            )
        except Exception as exc:
            errors.append((order_name, str(exc)))
            print(f"[{idx}/{len(sample_names)}] [ERR] {order_name}: {exc}", flush=True)

    total_time = time.time() - start_time
    print(flush=True)
    print(f"Completata in {total_time/60:.1f} min, errori LLM/ingest: {len(errors)}", flush=True)

    output_dir = Path("docs/eval")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = generate_report(
        results,
        output_path=None,
        model_name=f"ollama/{MODEL}",
        hardware_info=HARDWARE,
    )
    report = _append_before_after(report, results, total_time)
    (output_dir / "eval_report_qwen25_3b.md").write_text(report, encoding="utf-8")
    print(report)
    (output_dir / "eval_results.json").write_text(json.dumps({
        "model": f"ollama/{MODEL}",
        "hardware": HARDWARE,
        "sample_size": len(sample_names),
        "sample": sample_names,
        "total_time_seconds": total_time,
        "errors": errors,
        "metrics": {
            "header_accuracy": results.overall_header_accuracy(),
            "lines_accuracy": results.overall_lines_accuracy(),
            "silent_errors_count": len(results.all_silent_errors),
            "silent_error_rate": (
                len(results.all_silent_errors)
                / max(results.total_header_fields + results.total_line_key_fields, 1)
            ),
            "total_orders": results.total_orders,
            "hard_cases": results.hard_cases,
            "extraction_failures": results.extraction_failures,
            "orders_in_review": results.orders_in_review,
            "review_rate": results.orders_in_review / max(results.total_orders, 1),
            "mean_time_seconds": total_time / max(results.total_orders, 1),
        },
        "format_scores": results.format_scores,
    }, indent=2, ensure_ascii=False))
    return 0


# Misura precedente (stesso campione seed 42, qwen2.5:3b-instruct, stessi parametri).
BEFORE = {
    "header_accuracy": 0.56,
    "lines_accuracy": 0.36923076923076925,
    "silent_errors_count": 149,
    "silent_error_rate": 0.13423423423423422,
    "mean_time_seconds": 56.2,
    "review_rate": None,
    "format_scores": {
        "EML": {"count": 19, "header_correct": 33, "header_total": 76,
                "lines_expected": 242, "lines_matched": 26, "silent_errors": None},
        "PDF": {"count": 18, "header_correct": 48, "header_total": 72,
                "lines_expected": 126, "lines_matched": 56, "silent_errors": None},
        "XLSX": {"count": 13, "header_correct": 31, "header_total": 52,
                 "lines_expected": 87, "lines_matched": 86, "silent_errors": None},
    },
}


def _pct(correct: float, total: float) -> str:
    if not total:
        return "—"
    return f"{100 * correct / total:.1f}%"


def _append_before_after(report: str, results, total_time: float) -> str:
    """Aggiunge la tabella prima/dopo richiesta dalla valutazione."""
    n = max(results.total_orders, 1)
    field_denom = max(results.total_header_fields + results.total_line_key_fields, 1)
    after = {
        "header": results.overall_header_accuracy(),
        "lines": results.overall_lines_accuracy(),
        "silent_n": len(results.all_silent_errors),
        "silent": len(results.all_silent_errors) / field_denom,
        "review": results.orders_in_review / n,
        "time": total_time / n,
    }
    rows = [
        "",
        "## Prima / dopo (stesso campione, stesso modello)",
        "",
        "Campione: 50 ordini, seed 42, `qwen2.5:3b-instruct`, temperature=0, "
        "repeat_penalty=1.1, num_predict=2048, format=json.",
        "",
        "| Metrica | Prima | Dopo |",
        "|---------|-------|------|",
        f"| Testata | {100*BEFORE['header_accuracy']:.1f}% | {100*after['header']:.1f}% |",
        f"| Righe | {100*BEFORE['lines_accuracy']:.1f}% | {100*after['lines']:.1f}% |",
        f"| Errori silenziosi | {BEFORE['silent_errors_count']} "
        f"({100*BEFORE['silent_error_rate']:.2f}%) | "
        f"{after['silent_n']} ({100*after['silent']:.2f}%) |",
        f"| Ordini in revisione | n/d | {results.orders_in_review}/{results.total_orders} "
        f"({100*after['review']:.1f}%) |",
        f"| Tempo medio | {BEFORE['mean_time_seconds']:.1f}s | {after['time']:.1f}s |",
        "",
        "### Per formato",
        "",
        "| Formato | Testata prima | Testata dopo | Righe prima | Righe dopo | "
        "Errori silenziosi dopo |",
        "|---------|---------------|--------------|-------------|------------|------------------------|",
    ]
    for fmt in ("EML", "PDF", "XLSX"):
        before_fmt = BEFORE["format_scores"].get(fmt, {})
        after_fmt = results.format_scores.get(fmt, {})
        rows.append(
            f"| {fmt} | "
            f"{_pct(before_fmt.get('header_correct', 0), before_fmt.get('header_total', 0))} | "
            f"{_pct(after_fmt.get('header_correct', 0), after_fmt.get('header_total', 0))} | "
            f"{_pct(before_fmt.get('lines_matched', 0), before_fmt.get('lines_expected', 0))} | "
            f"{_pct(after_fmt.get('lines_matched', 0), after_fmt.get('lines_expected', 0))} | "
            f"{after_fmt.get('silent_errors', 0)} |"
        )
    rows.append("")
    return report.rstrip() + "\n" + "\n".join(rows)


if __name__ == "__main__":
    sys.exit(main())
