#!/usr/bin/env python3
"""
Script di valutazione per il modulo extract.

Confronta gli ordini estratti con il ground truth e produce un report Markdown
con accuratezza testata e righe, separando i casi difficili.

Uso:
    python -m extract.eval --documents synthetic/documents --ground-truth synthetic/ground_truth
    python -m extract.eval --extracted extracted/ --ground-truth synthetic/ground_truth
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FieldScore:
    """Punteggio per un singolo campo."""
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


@dataclass
class LineScore:
    """Punteggio per una riga ordine."""
    line_no: int
    description_match: bool = False
    quantity_match: bool = False
    seller_code_match: bool = False
    buyer_code_match: bool = False
    uom_match: bool = False
    price_match: bool = False

    @property
    def total_correct(self) -> int:
        return sum([
            self.description_match,
            self.quantity_match,
            self.seller_code_match,
            self.buyer_code_match,
            self.uom_match,
            self.price_match,
        ])


@dataclass
class OrderScore:
    """Punteggio per un singolo ordine."""
    order_id: str
    document_path: str
    is_hard_case: bool = False
    hard_case_types: list[str] = field(default_factory=list)

    header_fields: dict[str, FieldScore] = field(default_factory=dict)
    line_scores: list[LineScore] = field(default_factory=list)

    lines_expected: int = 0
    lines_extracted: int = 0
    lines_matched: int = 0

    extraction_time_ms: int = 0
    llm_calls: int = 0
    warnings_count: int = 0

    def header_accuracy(self) -> float:
        if not self.header_fields:
            return 0.0
        total_correct = sum(f.correct for f in self.header_fields.values())
        total = sum(f.total for f in self.header_fields.values())
        return total_correct / total if total > 0 else 0.0

    def lines_accuracy(self) -> float:
        if self.lines_expected == 0:
            return 0.0
        return self.lines_matched / self.lines_expected


@dataclass
class EvalResults:
    """Risultati aggregati della valutazione."""
    total_orders: int = 0
    hard_cases: int = 0

    header_scores: dict[str, FieldScore] = field(default_factory=dict)

    total_lines_expected: int = 0
    total_lines_extracted: int = 0
    total_lines_matched: int = 0

    order_scores: list[OrderScore] = field(default_factory=list)

    total_time_ms: int = 0
    total_llm_calls: int = 0

    def overall_header_accuracy(self) -> float:
        total_correct = sum(f.correct for f in self.header_scores.values())
        total = sum(f.total for f in self.header_scores.values())
        return total_correct / total if total > 0 else 0.0

    def overall_lines_accuracy(self) -> float:
        if self.total_lines_expected == 0:
            return 0.0
        return self.total_lines_matched / self.total_lines_expected

    def hard_case_accuracy(self) -> tuple[float, float]:
        """Restituisce (header_acc, lines_acc) per soli casi difficili."""
        hard_orders = [o for o in self.order_scores if o.is_hard_case]
        if not hard_orders:
            return 0.0, 0.0

        header_acc = sum(o.header_accuracy() for o in hard_orders) / len(hard_orders)
        lines_total = sum(o.lines_expected for o in hard_orders)
        lines_matched = sum(o.lines_matched for o in hard_orders)
        lines_acc = lines_matched / lines_total if lines_total > 0 else 0.0

        return header_acc, lines_acc

    def normal_case_accuracy(self) -> tuple[float, float]:
        """Restituisce (header_acc, lines_acc) per soli casi normali."""
        normal_orders = [o for o in self.order_scores if not o.is_hard_case]
        if not normal_orders:
            return 0.0, 0.0

        header_acc = sum(o.header_accuracy() for o in normal_orders) / len(normal_orders)
        lines_total = sum(o.lines_expected for o in normal_orders)
        lines_matched = sum(o.lines_matched for o in normal_orders)
        lines_acc = lines_matched / lines_total if lines_total > 0 else 0.0

        return header_acc, lines_acc


def normalize_string(s: str | None) -> str:
    """Normalizza stringa per confronto."""
    if s is None:
        return ""
    return str(s).strip().lower().replace("-", "").replace(" ", "")


def compare_values(extracted: Any, expected: Any, fuzzy: bool = False) -> bool:
    """Confronta due valori con tolleranza opzionale."""
    if extracted is None and expected is None:
        return True
    if extracted is None or expected is None:
        return False

    if isinstance(expected, (int, float)) and isinstance(extracted, (int, float)):
        if expected == 0:
            return extracted == 0
        return abs(extracted - expected) / abs(expected) < 0.01

    if fuzzy:
        return normalize_string(str(extracted)) == normalize_string(str(expected))

    return str(extracted).strip() == str(expected).strip()


def evaluate_order(
    extracted: dict,
    ground_truth: dict,
    document_path: str = "",
) -> OrderScore:
    """Valuta un singolo ordine estratto contro il ground truth."""
    meta = ground_truth.get("_synthetic_metadata", {})

    score = OrderScore(
        order_id=ground_truth.get("order_id", "unknown"),
        document_path=document_path,
        is_hard_case=meta.get("is_hard_case", False),
        hard_case_types=meta.get("hard_case_types", []),
    )

    ext_header = extracted.get("header", {})
    gt_header = ground_truth.get("header", {})

    header_fields = ["po_number", "po_date", "currency", "requested_delivery_date"]
    for field_name in header_fields:
        fs = FieldScore(total=1)
        ext_val = ext_header.get(field_name)
        gt_val = gt_header.get(field_name)

        if gt_val is not None:
            if compare_values(ext_val, gt_val, fuzzy=(field_name == "po_date")):
                fs.correct = 1
        elif ext_val is None:
            fs.correct = 1

        score.header_fields[field_name] = fs

    gt_lines = ground_truth.get("lines", [])
    ext_lines = extracted.get("lines", [])

    score.lines_expected = len(gt_lines)
    score.lines_extracted = len(ext_lines)

    ext_by_code: dict[str, dict] = {}
    for el in ext_lines:
        code = el.get("seller_item_code") or el.get("buyer_item_code") or ""
        if code:
            ext_by_code[normalize_string(code)] = el

    for gt_line in gt_lines:
        gt_seller = gt_line.get("seller_item_code", "")
        gt_buyer = gt_line.get("buyer_item_code", "")

        matched_ext = None

        if gt_seller:
            matched_ext = ext_by_code.get(normalize_string(gt_seller))
        if not matched_ext and gt_buyer:
            matched_ext = ext_by_code.get(normalize_string(gt_buyer))

        if not matched_ext:
            gt_desc = normalize_string(gt_line.get("description", ""))
            for el in ext_lines:
                if normalize_string(el.get("description", "")) == gt_desc:
                    matched_ext = el
                    break

        if not matched_ext and gt_line.get("line_no"):
            line_no = gt_line["line_no"]
            if line_no <= len(ext_lines):
                matched_ext = ext_lines[line_no - 1]

        line_score = LineScore(line_no=gt_line.get("line_no", 0))

        if matched_ext:
            line_score.description_match = compare_values(
                matched_ext.get("description"),
                gt_line.get("description"),
                fuzzy=True,
            )
            line_score.quantity_match = compare_values(
                matched_ext.get("quantity"),
                gt_line.get("quantity"),
            )
            line_score.seller_code_match = compare_values(
                matched_ext.get("seller_item_code"),
                gt_line.get("seller_item_code"),
                fuzzy=True,
            )
            line_score.buyer_code_match = compare_values(
                matched_ext.get("buyer_item_code"),
                gt_line.get("buyer_item_code"),
                fuzzy=True,
            )
            line_score.uom_match = compare_values(
                matched_ext.get("uom_raw") or matched_ext.get("uom"),
                gt_line.get("uom_raw") or gt_line.get("uom"),
                fuzzy=True,
            )
            line_score.price_match = compare_values(
                matched_ext.get("unit_price"),
                gt_line.get("unit_price"),
            )

            key_fields_ok = (
                line_score.description_match and
                line_score.quantity_match and
                (line_score.seller_code_match or line_score.buyer_code_match or not gt_seller)
            )
            if key_fields_ok:
                score.lines_matched += 1

        score.line_scores.append(line_score)

    return score


def generate_report(results: EvalResults, output_path: Path | None = None) -> str:
    """Genera report Markdown dai risultati."""
    lines = []
    lines.append("# Report Valutazione Estrazione Ordini")
    lines.append("")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("## Riepilogo")
    lines.append("")
    lines.append("| Metrica | Valore |")
    lines.append("|---------|--------|")
    lines.append(f"| Ordini totali | {results.total_orders} |")
    lines.append(f"| Casi difficili | {results.hard_cases} ({100*results.hard_cases/results.total_orders:.1f}%) |")
    lines.append(f"| Accuratezza testata | **{100*results.overall_header_accuracy():.1f}%** |")
    lines.append(f"| Accuratezza righe | **{100*results.overall_lines_accuracy():.1f}%** |")
    lines.append(f"| Righe totali GT | {results.total_lines_expected} |")
    lines.append(f"| Righe estratte | {results.total_lines_extracted} |")
    lines.append(f"| Righe matchate | {results.total_lines_matched} |")
    lines.append("")

    lines.append("## Accuratezza per Tipo di Caso")
    lines.append("")
    normal_h, normal_l = results.normal_case_accuracy()
    hard_h, hard_l = results.hard_case_accuracy()

    lines.append("| Tipo | Ordini | Testata | Righe |")
    lines.append("|------|--------|---------|-------|")
    lines.append(f"| Normali | {results.total_orders - results.hard_cases} | {100*normal_h:.1f}% | {100*normal_l:.1f}% |")
    lines.append(f"| Difficili | {results.hard_cases} | {100*hard_h:.1f}% | {100*hard_l:.1f}% |")
    lines.append("")

    lines.append("## Accuratezza Campi Testata")
    lines.append("")
    lines.append("| Campo | Corretti | Totali | Accuratezza |")
    lines.append("|-------|----------|--------|-------------|")
    for field_name, fs in results.header_scores.items():
        lines.append(f"| {field_name} | {fs.correct} | {fs.total} | {100*fs.accuracy:.1f}% |")
    lines.append("")

    hard_orders = [o for o in results.order_scores if o.is_hard_case]
    if hard_orders:
        lines.append("## Dettaglio Casi Difficili")
        lines.append("")
        lines.append("| Ordine | Tipo | Testata | Righe GT | Righe Match |")
        lines.append("|--------|------|---------|----------|-------------|")
        for order in hard_orders[:20]:
            types_str = ", ".join(order.hard_case_types[:3]) or "N/A"
            lines.append(
                f"| {order.order_id[:8]}... | {types_str} | "
                f"{100*order.header_accuracy():.0f}% | "
                f"{order.lines_expected} | {order.lines_matched} |"
            )
        lines.append("")

    if results.total_time_ms > 0:
        lines.append("## Performance")
        lines.append("")
        avg_time = results.total_time_ms / results.total_orders if results.total_orders > 0 else 0
        lines.append(f"- Tempo totale: {results.total_time_ms / 1000:.1f}s")
        lines.append(f"- Tempo medio per ordine: {avg_time:.0f}ms")
        lines.append(f"- Chiamate LLM totali: {results.total_llm_calls}")
        lines.append("")

    report = "\n".join(lines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report


def run_evaluation(
    documents_dir: Path | None = None,
    extracted_dir: Path | None = None,
    ground_truth_dir: Path | None = None,
    backend: str = "mock",
    model: str | None = None,
    sample_size: int | None = None,
    quiet: bool = False,
) -> EvalResults:
    """
    Esegue la valutazione completa.

    Se documents_dir è fornito, estrae prima i documenti.
    Se extracted_dir è fornito, usa ordini già estratti.
    """
    from ingest import Ingestor

    from .backends import MockBackend, OllamaBackend
    from .extractor import OrderExtractor

    if ground_truth_dir is None:
        ground_truth_dir = Path("synthetic/ground_truth")

    gt_files = list(ground_truth_dir.glob("order_*.json"))
    if sample_size:
        gt_files = gt_files[:sample_size]

    if not quiet:
        print(f"Trovati {len(gt_files)} file ground truth")

    results = EvalResults()

    if documents_dir:
        if backend == "ollama":
            llm_backend = OllamaBackend(model=model)
            if not llm_backend.is_available():
                print("Errore: Ollama non disponibile", file=sys.stderr)
                return results
        else:
            llm_backend = MockBackend()

        extractor = OrderExtractor(backend=llm_backend)
        ingestor = Ingestor()

        for gt_file in gt_files:
            with open(gt_file) as f:
                ground_truth = json.load(f)

            order_name = gt_file.stem
            doc_path = _find_document(documents_dir, order_name)

            if not doc_path:
                if not quiet:
                    print(f"[SKIP] {order_name}: documento non trovato")
                continue

            try:
                normalized = ingestor.ingest(doc_path)
                extraction_result = extractor.extract(normalized.to_dict())
                extracted = extraction_result.to_dict()

                order_score = evaluate_order(extracted, ground_truth, str(doc_path))
                order_score.extraction_time_ms = extraction_result.extraction_time_ms
                order_score.llm_calls = extraction_result.llm_calls

                _update_results(results, order_score, ground_truth)

                if not quiet:
                    status = "OK" if order_score.header_accuracy() > 0.5 else "WARN"
                    print(f"[{status}] {order_name}: H={100*order_score.header_accuracy():.0f}% L={order_score.lines_matched}/{order_score.lines_expected}")

            except Exception as e:  # noqa: BLE001
                if not quiet:
                    print(f"[ERR] {order_name}: {e}", file=sys.stderr)

    elif extracted_dir:
        for gt_file in gt_files:
            with open(gt_file) as f:
                ground_truth = json.load(f)

            order_name = gt_file.stem
            ext_file = extracted_dir / f"{order_name}_extracted.json"

            if not ext_file.exists():
                ext_file = extracted_dir / f"{order_name}.json"

            if not ext_file.exists():
                continue

            with open(ext_file) as f:
                extracted = json.load(f)

            order_score = evaluate_order(extracted, ground_truth, str(ext_file))
            _update_results(results, order_score, ground_truth)

    return results


def _find_document(documents_dir: Path, order_name: str) -> Path | None:
    """Trova il documento sorgente per un ordine."""
    for ext in [".eml", ".pdf", ".xlsx", ".xls", ".csv"]:
        for subdir in ["eml", "pdf", "xlsx", ""]:
            path = documents_dir / subdir / f"{order_name}{ext}"
            if path.exists():
                return path
            path = documents_dir / subdir / f"{order_name.replace('order_', '')}{ext}"
            if path.exists():
                return path

    for subdir in ["eml", "pdf", "xlsx", ""]:
        for path in (documents_dir / subdir).glob(f"*{order_name.split('_')[1]}*"):
            if path.is_file():
                return path

    return None


def _update_results(results: EvalResults, order_score: OrderScore, ground_truth: dict) -> None:
    """Aggiorna i risultati aggregati con un nuovo ordine."""
    results.total_orders += 1
    if order_score.is_hard_case:
        results.hard_cases += 1

    results.total_lines_expected += order_score.lines_expected
    results.total_lines_extracted += order_score.lines_extracted
    results.total_lines_matched += order_score.lines_matched

    for field_name, fs in order_score.header_fields.items():
        if field_name not in results.header_scores:
            results.header_scores[field_name] = FieldScore()
        results.header_scores[field_name].correct += fs.correct
        results.header_scores[field_name].total += fs.total

    results.total_time_ms += order_score.extraction_time_ms
    results.total_llm_calls += order_score.llm_calls

    results.order_scores.append(order_score)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valuta estrazione ordini contro ground truth.",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--documents",
        type=Path,
        help="Directory con documenti sorgente (estrae e valuta).",
    )
    group.add_argument(
        "--extracted",
        type=Path,
        help="Directory con ordini già estratti.",
    )

    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("synthetic/ground_truth"),
        help="Directory con ground truth (default: synthetic/ground_truth).",
    )

    parser.add_argument(
        "--backend",
        choices=["mock", "ollama"],
        default="mock",
        help="Backend LLM per estrazione (default: mock).",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Modello Ollama da usare.",
    )

    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Numero di ordini da valutare (default: tutti).",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="File di output per report Markdown.",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Non stampare avanzamento.",
    )

    args = parser.parse_args()

    results = run_evaluation(
        documents_dir=args.documents,
        extracted_dir=args.extracted,
        ground_truth_dir=args.ground_truth,
        backend=args.backend,
        model=args.model,
        sample_size=args.sample,
        quiet=args.quiet,
    )

    report = generate_report(results, args.output)

    if not args.output:
        print(report)
    else:
        print(f"Report salvato in: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
