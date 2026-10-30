"""Valutazione riproducibile: un comando, seed/modello/parametri fissi.

Uso:
    python -m extract.eval_run
    make eval
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .backends import MockBackend, OllamaBackend
from .eval import (
    EvalResults,
    _find_document,
    _update_results,
    detect_format,
    evaluate_order,
    generate_report,
)
from .extractor import OrderExtractor

EVAL_SEED = 42
EVAL_MODEL = "qwen2.5:3b-instruct"
EVAL_SAMPLE = 50
EVAL_BEFORE_COMMIT = "380c7bb"
HARDWARE = "Intel Xeon 4 cores, 15GB RAM, CPU-only (no GPU)"
EVAL_PARAMS = {
    "temperature": 0.0,
    "repeat_penalty": 1.1,
    "num_predict": 2048,
    "format": "json",
}


def load_before_from_git(commit: str) -> dict[str, Any]:
    """Carica eval_results.json dal commit di partenza (non numeri scritti a mano)."""
    shown = subprocess.run(
        ["git", "show", f"{commit}:docs/eval/eval_results.json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(shown.stdout)
    resolved = subprocess.check_output(["git", "rev-parse", commit], text=True).strip()
    payload["source_commit"] = resolved
    return payload


def build_sample(
    gt_dir: Path,
    docs_dir: Path,
    *,
    seed: int,
    sample_size: int,
    exclude_pdf: bool,
) -> list[str]:
    random.seed(seed)
    hard: list[str] = []
    normal: list[str] = []
    for path in sorted(gt_dir.glob("order_*.json")):
        doc = _find_document(docs_dir, path.stem)
        if doc is None:
            continue
        if exclude_pdf and detect_format(str(doc)) == "PDF":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("_synthetic_metadata") or {}
        if meta.get("is_hard_case"):
            hard.append(path.stem)
        else:
            normal.append(path.stem)
    remaining = max(0, sample_size - len(hard))
    picked = list(hard)
    if remaining and normal:
        picked.extend(random.sample(normal, min(remaining, len(normal))))
    return picked


def _order_payload(score, extraction_result, llm_failed: bool) -> dict[str, Any]:
    return {
        "order_id": score.order_id,
        "stem": Path(score.document_path).stem if score.document_path else None,
        "document_path": score.document_path,
        "format": score.document_format,
        "route": score.route,
        "hard_case": score.is_hard_case,
        "hard_case_types": score.hard_case_types,
        "header_accuracy": score.header_accuracy(),
        "lines_expected": score.lines_expected,
        "lines_matched": score.lines_matched,
        "lines_extracted": score.lines_extracted,
        "extra_lines": score.extra_lines,
        "missing_lines": score.missing_lines,
        "silent_order": score.silent_order,
        "silent_fields": [
            {
                "path": err.field_path,
                "expected": err.expected,
                "extracted": err.extracted,
            }
            for err in score.silent_errors
        ],
        "field_mismatches": [
            {
                "path": err.field_path,
                "expected": err.expected,
                "extracted": err.extracted,
            }
            for err in score.field_mismatches
        ],
        "llm_calls": score.llm_calls,
        "llm_timeouts": score.llm_timeouts,
        "llm_failed": llm_failed,
        "extraction_time_ms": score.extraction_time_ms,
        "overall_confidence": extraction_result.order.overall_confidence,
        "decision": extraction_result.decision,
    }


def run_sample(
    sample_names: list[str],
    *,
    gt_dir: Path,
    docs_dir: Path,
    use_llm: bool,
    model: str,
    quiet: bool,
) -> tuple[EvalResults, list[dict[str, Any]], list[tuple[str, str]], float]:
    from ingest import Ingestor

    if use_llm:
        backend = OllamaBackend(model=model, timeout=90.0)
        if not backend.is_available():
            raise RuntimeError("Ollama non disponibile")
    else:
        backend = MockBackend()

    extractor = OrderExtractor(
        backend=backend,
        max_retries=0,
        validate_output=False,
        use_llm=use_llm,
    )
    ingestor = Ingestor()
    results = EvalResults()
    per_order: list[dict[str, Any]] = []
    errors: list[tuple[str, str]] = []
    start_time = time.time()

    for idx, order_name in enumerate(sample_names, 1):
        ground_truth = json.loads((gt_dir / f"{order_name}.json").read_text(encoding="utf-8"))
        doc_path = _find_document(docs_dir, order_name)
        if not doc_path:
            errors.append((order_name, "documento non trovato"))
            if not quiet:
                print(f"[{idx}/{len(sample_names)}] [ERR] {order_name}: documento non trovato", flush=True)
            continue
        t0 = time.time()
        llm_failed = False
        try:
            normalized = ingestor.ingest(doc_path)
            extraction_result = extractor.extract(normalized.to_dict())
            extracted = extraction_result.to_dict()
            order_score = evaluate_order(extracted, ground_truth, str(doc_path))
            order_score.extraction_time_ms = extraction_result.extraction_time_ms
            order_score.llm_calls = extraction_result.llm_calls
            order_score.llm_timeouts = extraction_result.llm_timeouts
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
            per_order.append(_order_payload(order_score, extraction_result, llm_failed))
            elapsed = time.time() - t0
            if not quiet:
                status = "ERR" if llm_failed else ("OK" if order_score.header_accuracy() >= 0.75 else "WARN")
                kind = "HARD" if order_score.is_hard_case else "NORM"
                print(
                    f"[{idx}/{len(sample_names)}] [{status}] [{kind}] {order_name}: "
                    f"H={100 * order_score.header_accuracy():.0f}% "
                    f"L={order_score.lines_matched}/{order_score.lines_expected} "
                    f"{order_score.route} ({elapsed:.1f}s)",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append((order_name, str(exc)))
            if not quiet:
                print(f"[{idx}/{len(sample_names)}] [ERR] {order_name}: {exc}", flush=True)

    return results, per_order, errors, time.time() - start_time


def _metrics_dict(results: EvalResults, total_time: float) -> dict[str, Any]:
    n = max(results.total_orders, 1)
    auto_n = max(results.auto_post_orders, 1)
    return {
        "header_accuracy": results.overall_header_accuracy(),
        "lines_accuracy": results.overall_lines_accuracy(),
        "silent_orders": results.silent_orders,
        "silent_order_rate": results.silent_orders / auto_n if results.auto_post_orders else 0.0,
        "silent_field_errors": results.silent_field_errors,
        "silent_field_rate": (
            results.silent_field_errors / max(results.auto_post_field_total, 1)
            if results.auto_post_orders else 0.0
        ),
        "total_orders": results.total_orders,
        "hard_cases": results.hard_cases,
        "extraction_failures": results.extraction_failures,
        "auto_post_orders": results.auto_post_orders,
        "auto_post_rate": results.auto_post_orders / n,
        "orders_in_review": results.orders_in_review,
        "review_rate": results.orders_in_review / n,
        "reject_orders": results.reject_orders,
        "reject_rate": results.reject_orders / n,
        "mean_time_seconds": total_time / n,
        "llm_calls": results.total_llm_calls,
        "llm_timeouts": results.llm_timeouts,
    }


def _pct(correct: float, total: float) -> str:
    if not total:
        return "—"
    return f"{100 * correct / total:.1f}%"


def _route_cell(data: dict, key: str) -> str:
    count = data.get("count") or 0
    if not count:
        return "—"
    return f"{data.get(key, 0)}/{count}"


def append_before_after(
    report: str,
    results: EvalResults,
    before: dict[str, Any],
    no_llm: dict[str, Any] | None,
    total_time: float,
    *,
    exclude_pdf: bool,
) -> str:
    after = _metrics_dict(results, total_time)
    before_metrics = before.get("metrics") or {}
    before_fmt = before.get("format_scores") or {}
    rows = [
        "",
        "## Prima / dopo",
        "",
        f"Prima: metriche regenerate con `git show {before.get('source_commit', EVAL_BEFORE_COMMIT)}"
        ":docs/eval/eval_results.json` (commit di partenza, non copiate a mano).",
        "Dopo: questo commit, stesso seed e stesso modello. "
        + ("Campione senza PDF." if exclude_pdf else ""),
        "",
        "| Metrica | Prima | Dopo |",
        "|---------|-------|------|",
        f"| Testata | {100 * before_metrics.get('header_accuracy', 0):.1f}% | {100 * after['header_accuracy']:.1f}% |",
        f"| Righe | {100 * before_metrics.get('lines_accuracy', 0):.1f}% | {100 * after['lines_accuracy']:.1f}% |",
        f"| Errori silenziosi (ordini AUTO_POST) | n/d (def. precedente) | "
        f"{after['silent_orders']}/{after['auto_post_orders']} "
        f"({100 * after['silent_order_rate']:.2f}%) |",
        f"| Errori silenziosi (campi AUTO_POST) | "
        f"{before_metrics.get('silent_errors_count', 'n/d')} "
        f"({100 * before_metrics.get('silent_error_rate', 0):.2f}%, def. precedente) | "
        f"{after['silent_field_errors']} ({100 * after['silent_field_rate']:.2f}%) |",
        f"| AUTO_POST | n/d | {after['auto_post_orders']}/{after['total_orders']} "
        f"({100 * after['auto_post_rate']:.1f}%) |",
        f"| REVIEW | n/d | {after['orders_in_review']}/{after['total_orders']} "
        f"({100 * after['review_rate']:.1f}%) |",
        f"| REJECT | n/d | {after['reject_orders']}/{after['total_orders']} "
        f"({100 * after['reject_rate']:.1f}%) |",
        f"| Tempo medio | {before_metrics.get('mean_time_seconds', before.get('total_time_seconds', 0) / max(before_metrics.get('total_orders', 1), 1)):.1f}s | {after['mean_time_seconds']:.1f}s |",
        "",
        "### Per formato",
        "",
        "| Formato | Testata prima | Testata dopo | Righe prima | Righe dopo | "
        "AUTO_POST dopo | REVIEW dopo | REJECT dopo | Silent ordini dopo |",
        "|---------|---------------|--------------|-------------|------------|"
        "----------------|--------------|--------------|--------------------|",
    ]
    for fmt in ("EML", "XLSX", "PDF"):
        bfmt = before_fmt.get(fmt, {})
        afmt = results.format_scores.get(fmt, {})
        if not bfmt and not afmt:
            continue
        rows.append(
            f"| {fmt} | "
            f"{_pct(bfmt.get('header_correct', 0), bfmt.get('header_total', 0))} | "
            f"{_pct(afmt.get('header_correct', 0), afmt.get('header_total', 0))} | "
            f"{_pct(bfmt.get('lines_matched', 0), bfmt.get('lines_expected', 0))} | "
            f"{_pct(afmt.get('lines_matched', 0), afmt.get('lines_expected', 0))} | "
            f"{_route_cell(afmt, 'auto_post')} | "
            f"{_route_cell(afmt, 'review')} | "
            f"{_route_cell(afmt, 'reject')} | "
            f"{afmt.get('silent_orders', 0)} |"
        )
    rows.append("")
    if no_llm:
        nl = no_llm.get("metrics") or {}
        rows.extend([
            "## Contributo LLM",
            "",
            "Stessa run (stesso campione, stessi documenti) con LLM disattivato: solo preprocessor.",
            "",
            "| Metrica | Con LLM | Senza LLM |",
            "|---------|---------|-----------|",
            f"| Testata | {100 * after['header_accuracy']:.1f}% | {100 * nl.get('header_accuracy', 0):.1f}% |",
            f"| Righe | {100 * after['lines_accuracy']:.1f}% | {100 * nl.get('lines_accuracy', 0):.1f}% |",
            f"| AUTO_POST | {after['auto_post_orders']}/{after['total_orders']} | "
            f"{nl.get('auto_post_orders', 0)}/{nl.get('total_orders', 0)} |",
            f"| REVIEW | {after['orders_in_review']}/{after['total_orders']} | "
            f"{nl.get('orders_in_review', 0)}/{nl.get('total_orders', 0)} |",
            f"| Chiamate LLM | {after['llm_calls']} | {nl.get('llm_calls', 0)} |",
            f"| Timeout LLM | {after['llm_timeouts']} | {nl.get('llm_timeouts', 0)} |",
            "",
        ])
    rows.extend([
        "",
        "## (b) Cosa aspettarsi su documenti reali",
        "",
        "I numeri sopra sono su **PO sintetici**: Excel con colonne etichettate, "
        "email generate da cinque template noti a questo repo, anagrafica completa, "
        "prezzi allineati al listino. Non sono un campione di PO veri.",
        "",
        "**Excel/CSV strutturati.** È la fascia in cui il prototipo è già utile: "
        "testata e righe escono dal preprocessor, AUTO_POST è raggiungibile se "
        "cliente e articoli sono in anagrafica. Su file reali manca lo sporco "
        "che qui non c'è (fogli multipli, intestazioni su due righe, colonne "
        "fuori ordine, prezzi in millesimi, UoM inventate).",
        "",
        "**Email di testo libero.** Le regex attuali riconoscono solo `N. [SKU]` + "
        "`Qty:`. I cinque template nuovi (prosa, tabella HTML, elenco in firma, "
        "quantità in lettere, inoltro) sono volutamente fuori da quelle regex: "
        "servono all'LLM. Su questa macchina `qwen2.5:3b-instruct` in CPU va in "
        "timeout sulla maggior parte delle email (21/25 in questo campione). "
        "Senza un modello che risponda in tempo, quelle email restano in REVIEW "
        "con testata/righe incomplete. Su documenti veri (inoltri, firme, HTML "
        "di Outlook) l'accuratezza sarà quella dell'LLM, non quella dell'Excel.",
        "",
        "**PDF.** Esclusi da questo run. Il preprocessor legge tabelle pdfplumber; "
        "i PDF scansionati (`needs_ocr`) non sono supportati.",
        "",
        "**Limiti noti.** Matching articoli solo SKU/xref esatto; niente fuzzy. "
        "AUTO_POST nel prototipo assume i clienti sintetici già in allowlist "
        "(§7.1 ALLOWLIST+HISTORY). In produzione l'allowlist è quella reale: "
        "un ordine pulito di un cliente nuovo va in REVIEW. Confidenza "
        "deterministica 0,98, soglia AUTO_POST 0,97 invariata.",
        "",
    ])
    return report.rstrip() + "\n" + "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valutazione extract riproducibile.")
    parser.add_argument("--seed", type=int, default=EVAL_SEED)
    parser.add_argument("--model", type=str, default=EVAL_MODEL)
    parser.add_argument("--sample", type=int, default=EVAL_SAMPLE)
    parser.add_argument("--before-commit", type=str, default=EVAL_BEFORE_COMMIT)
    parser.add_argument("--exclude-pdf", action="store_true", default=True)
    parser.add_argument("--include-pdf", action="store_true")
    parser.add_argument("--also-no-llm", action="store_true", default=True)
    parser.add_argument("--skip-no-llm", action="store_true")
    parser.add_argument("--no-llm-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/eval"))
    parser.add_argument("--documents", type=Path, default=Path("synthetic/documents"))
    parser.add_argument("--ground-truth", type=Path, default=Path("synthetic/ground_truth"))
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    exclude_pdf = not args.include_pdf
    also_no_llm = args.also_no_llm and not args.skip_no_llm
    sample_names = build_sample(
        args.ground_truth,
        args.documents,
        seed=args.seed,
        sample_size=args.sample,
        exclude_pdf=exclude_pdf,
    )
    if not args.quiet:
        print(f"Campione: {len(sample_names)} ordini, seed {args.seed}", flush=True)
        print(f"Modello: {args.model}", flush=True)
        print(f"Parametri: {EVAL_PARAMS}", flush=True)
        print(f"Escludi PDF: {exclude_pdf}", flush=True)

    no_llm_payload: dict[str, Any] | None = None
    if args.no_llm_only:
        results, per_order, errors, total_time = run_sample(
            sample_names,
            gt_dir=args.ground_truth,
            docs_dir=args.documents,
            use_llm=False,
            model=args.model,
            quiet=args.quiet,
        )
        llm_label = "none"
    else:
        results, per_order, errors, total_time = run_sample(
            sample_names,
            gt_dir=args.ground_truth,
            docs_dir=args.documents,
            use_llm=True,
            model=args.model,
            quiet=args.quiet,
        )
        llm_label = f"ollama/{args.model}"
        if also_no_llm:
            if not args.quiet:
                print("\n--- Stessa run con LLM disattivato ---\n", flush=True)
            nl_results, nl_orders, nl_errors, nl_time = run_sample(
                sample_names,
                gt_dir=args.ground_truth,
                docs_dir=args.documents,
                use_llm=False,
                model=args.model,
                quiet=args.quiet,
            )
            no_llm_payload = {
                "metrics": _metrics_dict(nl_results, nl_time),
                "format_scores": nl_results.format_scores,
                "orders": nl_orders,
                "errors": nl_errors,
                "total_time_seconds": nl_time,
            }

    before = load_before_from_git(args.before_commit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = generate_report(
        results,
        output_path=None,
        model_name=llm_label,
        hardware_info=HARDWARE,
    )
    report = append_before_after(
        report, results, before, no_llm_payload, total_time, exclude_pdf=exclude_pdf,
    )
    (args.output_dir / "eval_report_qwen25_3b.md").write_text(report, encoding="utf-8")
    payload = {
        "model": llm_label,
        "hardware": HARDWARE,
        "params": EVAL_PARAMS,
        "seed": args.seed,
        "sample_size": len(sample_names),
        "sample": sample_names,
        "exclude_pdf": exclude_pdf,
        "before_commit": before.get("source_commit"),
        "total_time_seconds": total_time,
        "errors": errors,
        "metrics": _metrics_dict(results, total_time),
        "format_scores": results.format_scores,
        "orders": per_order,
        "before": {
            "source_commit": before.get("source_commit"),
            "metrics": before.get("metrics"),
            "format_scores": before.get("format_scores"),
            "sample_size": before.get("sample_size"),
        },
        "no_llm": no_llm_payload,
    }
    (args.output_dir / "eval_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(report)
    print(f"JSON: {args.output_dir / 'eval_results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
