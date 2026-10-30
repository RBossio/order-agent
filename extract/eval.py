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

from .dates import parse_date_tuple


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
class SilentError:
    """Campo sbagliato con confidenza alta e senza avviso."""
    order_id: str
    field_path: str
    expected: Any
    extracted: Any
    confidence: float


@dataclass
class OrderScore:
    """Punteggio per un singolo ordine."""
    order_id: str
    document_path: str
    document_format: str = "UNKNOWN"
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
    silent_errors: list[SilentError] = field(default_factory=list)
    extraction_failed: bool = False
    failure_reason: str | None = None
    in_review: bool = False

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
    all_silent_errors: list[SilentError] = field(default_factory=list)
    format_scores: dict[str, dict] = field(default_factory=dict)
    extraction_failures: int = 0
    total_header_fields: int = 0
    total_line_key_fields: int = 0
    orders_in_review: int = 0

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


def parse_date(value: Any) -> tuple[int, int, int] | None:
    """Parsa una data in (year, month, day) da formati ISO, US, EU o testuali."""
    return parse_date_tuple(value)


def compare_dates(extracted: Any, expected: Any) -> bool:
    """Confronta date ignorando il formato di rappresentazione."""
    pe, px = parse_date(expected), parse_date(extracted)
    if pe and px:
        return pe == px
    return compare_values(extracted, expected, fuzzy=True)


def compare_values(extracted: Any, expected: Any, fuzzy: bool = False) -> bool:
    """Confronta due valori con tolleranza opzionale."""
    if extracted is None and expected is None:
        return True
    if extracted is None or expected is None:
        return False

    if isinstance(expected, int | float) and isinstance(extracted, int | float):
        if expected == 0:
            return extracted == 0
        return abs(extracted - expected) / abs(expected) < 0.01

    if isinstance(extracted, str) and isinstance(expected, int | float):
        try:
            extracted = float(extracted.replace(",", "").replace("$", ""))
            return compare_values(extracted, expected, fuzzy)
        except ValueError:
            pass

    if fuzzy:
        return normalize_string(str(extracted)) == normalize_string(str(expected))

    return str(extracted).strip() == str(expected).strip()


def detect_format(document_path: str) -> str:
    """Rileva il formato del documento dal path."""
    path_lower = document_path.lower()
    if ".pdf" in path_lower or "/pdf/" in path_lower:
        return "PDF"
    if ".xlsx" in path_lower or ".xls" in path_lower or "/xlsx/" in path_lower:
        return "XLSX"
    if ".eml" in path_lower or "/eml/" in path_lower:
        return "EML"
    if ".csv" in path_lower:
        return "CSV"
    return "UNKNOWN"


HIGH_CONFIDENCE_THRESHOLD = 0.8


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
        document_format=detect_format(document_path),
        is_hard_case=meta.get("is_hard_case", False),
        hard_case_types=meta.get("hard_case_types", []),
    )

    evidence = extracted.get("evidence", {})
    issues = extracted.get("validation", {}).get("issues", [])
    warned_paths = {issue.get("path") for issue in issues if issue.get("path")}
    route = (extracted.get("decision") or {}).get("route")
    score.in_review = (
        extracted.get("status") in {"NEEDS_REVIEW", "REJECTED"}
        or route in {"REVIEW", "REJECT"}
        or any(issue.get("severity") in {"BLOCK", "REVIEW"} for issue in issues)
    )

    ext_header = extracted.get("header", {})
    gt_header = ground_truth.get("header", {})

    header_fields = ["po_number", "po_date", "currency", "requested_delivery_date"]
    date_fields = {"po_date", "requested_delivery_date"}
    for field_name in header_fields:
        fs = FieldScore(total=1)
        ext_val = ext_header.get(field_name)
        gt_val = gt_header.get(field_name)
        field_path = f"/header/{field_name}"
        is_correct = False

        if gt_val is not None:
            matcher = compare_dates if field_name in date_fields else compare_values
            if matcher(ext_val, gt_val):
                fs.correct = 1
                is_correct = True
        elif ext_val is None:
            fs.correct = 1
            is_correct = True

        if not is_correct and gt_val is not None:
            confidence = evidence.get(field_path, {}).get("confidence", 0)
            if confidence >= HIGH_CONFIDENCE_THRESHOLD and field_path not in warned_paths:
                score.silent_errors.append(SilentError(
                    order_id=score.order_id,
                    field_path=field_path,
                    expected=gt_val,
                    extracted=ext_val,
                    confidence=confidence,
                ))

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

            line_idx = gt_line.get("line_no", 1) - 1
            for check_field, is_match, gt_field in [
                ("quantity", line_score.quantity_match, "quantity"),
                ("seller_item_code", line_score.seller_code_match, "seller_item_code"),
            ]:
                if not is_match and gt_line.get(gt_field) is not None:
                    line_path = f"/lines/{line_idx}/{check_field}"
                    confidence = evidence.get(line_path, {}).get(
                        "confidence",
                        evidence.get(f"/lines/{line_idx}", {}).get("confidence", 0),
                    )
                    if confidence >= HIGH_CONFIDENCE_THRESHOLD and line_path not in warned_paths:
                        score.silent_errors.append(SilentError(
                            order_id=score.order_id,
                            field_path=line_path,
                            expected=gt_line.get(gt_field),
                            extracted=matched_ext.get(check_field),
                            confidence=confidence,
                        ))

        score.line_scores.append(line_score)

    return score


def generate_report(
    results: EvalResults,
    output_path: Path | None = None,
    model_name: str = "",
    hardware_info: str = "",
) -> str:
    """Genera report Markdown dai risultati."""
    lines = []
    lines.append("# Report Valutazione Estrazione Ordini")
    lines.append("")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if model_name:
        lines.append(f"**Modello:** {model_name}")
    if hardware_info:
        lines.append(f"**Hardware:** {hardware_info}")
    lines.append("")

    header_acc = results.overall_header_accuracy()
    lines_acc = results.overall_lines_accuracy()
    field_denom = max(results.total_header_fields + results.total_line_key_fields, 1)
    silent_pct = 100 * len(results.all_silent_errors) / field_denom
    n = max(results.total_orders, 1)
    review_pct = 100 * results.orders_in_review / n
    avg_time_s = (results.total_time_ms / n / 1000) if results.total_time_ms else 0

    lines.append("## Riepilogo vs target")
    lines.append("")
    lines.append("| Metrica | Valore | Target |")
    lines.append("|---------|--------|--------|")
    lines.append(f"| Accuratezza testata | **{100*header_acc:.1f}%** | ≥98% {'✅' if header_acc >= 0.98 else '❌'} |")
    lines.append(f"| Accuratezza righe | **{100*lines_acc:.1f}%** | ≥90% {'✅' if lines_acc >= 0.90 else '❌'} |")
    lines.append(f"| Errori silenziosi | **{len(results.all_silent_errors)}** ({silent_pct:.2f}%) | ≤1% {'✅' if silent_pct <= 1.0 else '❌'} |")
    lines.append(f"| Ordini in revisione | **{results.orders_in_review}/{results.total_orders}** ({review_pct:.1f}%) | - |")
    lines.append(f"| Tempo medio/ordine | **{avg_time_s:.1f}s** | - |")
    lines.append(f"| Ordini valutati | {results.total_orders} | - |")
    lines.append(f"| Fallimenti estrazione | {results.extraction_failures} | - |")
    lines.append(f"| Casi difficili | {results.hard_cases} ({100*results.hard_cases/n:.1f}%) | - |")
    lines.append("")

    if results.format_scores:
        lines.append("## Accuratezza per Formato")
        lines.append("")
        lines.append("| Formato | Ordini | Testata | Righe | Errori silenziosi | Revisione | Tempo medio |")
        lines.append("|---------|--------|---------|-------|-------------------|-----------|-------------|")
        for fmt, data in sorted(results.format_scores.items()):
            if data.get("count", 0) > 0:
                h_acc = 100 * data.get("header_correct", 0) / max(data.get("header_total", 1), 1)
                l_acc = 100 * data.get("lines_matched", 0) / max(data.get("lines_expected", 1), 1)
                silent_n = data.get("silent_errors", 0)
                review_n = data.get("review", 0)
                avg = data.get("time_ms", 0) / max(data.get("count", 1), 1) / 1000
                lines.append(
                    f"| {fmt} | {data['count']} | {h_acc:.1f}% | {l_acc:.1f}% | "
                    f"{silent_n} | {review_n}/{data['count']} | {avg:.1f}s |"
                )
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

    if results.all_silent_errors:
        lines.append("## Errori silenziosi")
        lines.append("")
        lines.append("Campi errati con confidenza ≥80% e senza avviso di validazione.")
        lines.append("")
        lines.append("| Ordine | Campo | Atteso | Estratto | Confidenza |")
        lines.append("|--------|-------|--------|----------|------------|")
        for err in results.all_silent_errors[:25]:
            exp_str = str(err.expected)[:24] if err.expected is not None else "-"
            ext_str = str(err.extracted)[:24] if err.extracted is not None else "-"
            lines.append(
                f"| {err.order_id[:8]}... | {err.field_path} | {exp_str} | {ext_str} | "
                f"{100*err.confidence:.0f}% |"
            )
        if len(results.all_silent_errors) > 25:
            lines.append(f"| ... | ({len(results.all_silent_errors) - 25} altri) | | | |")
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
    if order_score.extraction_failed:
        results.extraction_failures += 1
    if order_score.in_review:
        results.orders_in_review += 1

    results.total_lines_expected += order_score.lines_expected
    results.total_lines_extracted += order_score.lines_extracted
    results.total_lines_matched += order_score.lines_matched

    for field_name, fs in order_score.header_fields.items():
        if field_name not in results.header_scores:
            results.header_scores[field_name] = FieldScore()
        results.header_scores[field_name].correct += fs.correct
        results.header_scores[field_name].total += fs.total
        results.total_header_fields += fs.total

    results.total_line_key_fields += order_score.lines_expected * 2
    results.total_time_ms += order_score.extraction_time_ms
    results.total_llm_calls += order_score.llm_calls
    results.all_silent_errors.extend(order_score.silent_errors)

    fmt = order_score.document_format
    if fmt not in results.format_scores:
        results.format_scores[fmt] = {
            "count": 0,
            "header_correct": 0,
            "header_total": 0,
            "lines_expected": 0,
            "lines_matched": 0,
            "silent_errors": 0,
            "review": 0,
            "time_ms": 0,
        }
    results.format_scores[fmt]["count"] += 1
    results.format_scores[fmt]["silent_errors"] += len(order_score.silent_errors)
    results.format_scores[fmt]["review"] += 1 if order_score.in_review else 0
    results.format_scores[fmt]["time_ms"] += order_score.extraction_time_ms
    results.format_scores[fmt]["header_correct"] += sum(
        f.correct for f in order_score.header_fields.values()
    )
    results.format_scores[fmt]["header_total"] += sum(
        f.total for f in order_score.header_fields.values()
    )
    results.format_scores[fmt]["lines_expected"] += order_score.lines_expected
    results.format_scores[fmt]["lines_matched"] += order_score.lines_matched

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
