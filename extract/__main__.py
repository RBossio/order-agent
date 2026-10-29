"""
CLI per il modulo extract.

Uso:
    python -m extract <normalized.json> -o order.json
    python -m extract <folder> --batch -o output_dir/
    python -m extract <file> --backend ollama --model qwen2.5:7b-instruct
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .backends import LLMBackend, MockBackend, OllamaBackend
from .extractor import OrderExtractor


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="extract",
        description="Estrae ordini da NormalizedInput usando LLM locale.",
    )

    parser.add_argument(
        "input",
        type=Path,
        help="File JSON NormalizedInput o cartella per batch.",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="File di output JSON (singolo) o directory (batch). Default: stdout.",
    )

    parser.add_argument(
        "--batch",
        action="store_true",
        help="Modalità batch: processa tutti i file .json nella cartella.",
    )

    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="In modalità batch, cerca anche nelle sottocartelle.",
    )

    parser.add_argument(
        "--backend",
        choices=["mock", "ollama"],
        default="mock",
        help="Backend LLM da usare (default: mock).",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Nome del modello per Ollama (default: qwen2.5:7b-instruct).",
    )

    parser.add_argument(
        "--ollama-host",
        type=str,
        default=None,
        help="URL host Ollama (default: http://localhost:11434).",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Numero massimo di retry dopo errore validazione (default: 1).",
    )

    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Disabilita validazione output contro schema.",
    )

    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentazione JSON (default: 2, 0 per compatto).",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Non stampare messaggi di avanzamento.",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Output dettagliato con statistiche.",
    )

    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path | None = args.output

    if not input_path.exists():
        print(f"Errore: '{input_path}' non esiste.", file=sys.stderr)
        return 1

    backend = _create_backend(args)

    if args.backend == "ollama" and not backend.is_available():
        print("Errore: Ollama non raggiungibile. Verifica che sia in esecuzione.", file=sys.stderr)
        print(f"  Host: {backend.host}", file=sys.stderr)
        return 1

    extractor = OrderExtractor(
        backend=backend,
        max_retries=args.max_retries,
        validate_output=not args.no_validate,
    )

    if args.batch or input_path.is_dir():
        return _run_batch(extractor, input_path, output_path, args)
    else:
        return _run_single(extractor, input_path, output_path, args)


def _create_backend(args) -> LLMBackend:
    """Crea il backend LLM appropriato."""
    if args.backend == "ollama":
        return OllamaBackend(
            host=args.ollama_host,
            model=args.model,
        )
    else:
        return MockBackend()


def _run_single(
    extractor: OrderExtractor,
    input_path: Path,
    output_path: Path | None,
    args,
) -> int:
    """Esegue estrazione su singolo file."""
    try:
        result = extractor.extract_from_file(input_path)
    except Exception as e:  # noqa: BLE001
        print(f"Errore nell'estrazione: {e}", file=sys.stderr)
        return 1

    output_dict = result.to_dict()
    indent = args.indent if args.indent > 0 else None

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_dict, f, indent=indent, ensure_ascii=False)
        if not args.quiet:
            print(f"Output salvato in: {output_path}")
    else:
        print(json.dumps(output_dict, indent=indent, ensure_ascii=False))

    if args.verbose and not args.quiet:
        _print_stats(result)

    has_blocking = any(w.severity.value == "BLOCK" for w in result.warnings)
    return 1 if has_blocking else 0


def _run_batch(
    extractor: OrderExtractor,
    input_dir: Path,
    output_dir: Path | None,
    args,
) -> int:
    """Esegue estrazione batch su directory."""
    if not input_dir.is_dir():
        print("Errore: modalità batch richiede una directory.", file=sys.stderr)
        return 1

    if output_dir is None:
        output_dir = input_dir / "extracted"

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.recursive:
        files = list(input_dir.rglob("*.json"))
    else:
        files = list(input_dir.glob("*.json"))

    files = [f for f in files if not f.name.startswith("order_") or "normalized" in f.name.lower()]

    if not files:
        files = list(input_dir.glob("*.json"))

    success_count = 0
    error_count = 0
    total_time = 0
    total_tokens = 0

    for file_path in sorted(files):
        try:
            result = extractor.extract_from_file(file_path)

            output_file = output_dir / f"{file_path.stem}_extracted.json"
            indent = args.indent if args.indent > 0 else None

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=indent, ensure_ascii=False)

            success_count += 1
            total_time += result.extraction_time_ms
            total_tokens += result.llm_tokens_used

            if not args.quiet:
                status = "OK" if result.order.status == "EXTRACTED" else "REVIEW"
                print(f"[{status}] {file_path.name} -> {output_file.name}")

        except Exception as e:  # noqa: BLE001
            error_count += 1
            if not args.quiet:
                print(f"[ERRORE] {file_path.name}: {e}", file=sys.stderr)

    if not args.quiet:
        print(f"\nCompletato: {success_count} successi, {error_count} errori")
        if success_count > 0:
            print(f"Tempo medio: {total_time // success_count}ms")
            print(f"Token totali: {total_tokens}")

    return 0 if error_count == 0 else 1


def _print_stats(result) -> None:
    """Stampa statistiche dell'estrazione."""
    print("\n--- Statistiche ---", file=sys.stderr)
    print(f"Status: {result.order.status}", file=sys.stderr)
    print(f"Righe estratte: {len(result.order.lines)}", file=sys.stderr)
    print(f"Chiamate LLM: {result.llm_calls}", file=sys.stderr)
    print(f"Token usati: {result.llm_tokens_used}", file=sys.stderr)
    print(f"Tempo: {result.extraction_time_ms}ms", file=sys.stderr)
    print(f"Campi pre-elaborati: {len(result.preprocessed_fields)}", file=sys.stderr)

    if result.warnings:
        print(f"\nAvvisi ({len(result.warnings)}):", file=sys.stderr)
        for w in result.warnings[:5]:
            print(f"  [{w.severity.value}] {w.code}: {w.message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
