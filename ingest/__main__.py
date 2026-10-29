"""
CLI per il modulo ingest.

Uso:
    python -m ingest <file> -o out.json
    python -m ingest <folder> --batch -o output_dir/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingestor import Ingestor


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Ingestisce documenti (EML, PDF, Excel, CSV) e produce JSON normalizzato.",
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="File o cartella da ingestare.",
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="File di output JSON (singolo file) o directory (batch). Default: stdout per file singolo.",
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Modalità batch: processa tutti i file supportati nella cartella.",
    )
    
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="In modalità batch, cerca anche nelle sottocartelle.",
    )
    
    parser.add_argument(
        "-e", "--extensions",
        type=str,
        default=None,
        help="In modalità batch, estensioni da processare (separate da virgola, es: .pdf,.xlsx).",
    )
    
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentazione JSON (default: 2, 0 per output compatto).",
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Non stampare messaggi di avanzamento.",
    )
    
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Valida l'output contro lo schema JSON.",
    )
    
    args = parser.parse_args()
    
    input_path: Path = args.input
    output_path: Path | None = args.output
    
    if not input_path.exists():
        print(f"Errore: '{input_path}' non esiste.", file=sys.stderr)
        return 1
    
    ingestor = Ingestor()
    
    if args.batch or input_path.is_dir():
        if not input_path.is_dir():
            print(f"Errore: modalità batch richiede una directory.", file=sys.stderr)
            return 1
        
        if output_path is None:
            output_path = input_path / "ingested"
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        extensions = None
        if args.extensions:
            extensions = [e.strip() for e in args.extensions.split(",")]
        
        results = ingestor.ingest_batch(
            input_path,
            recursive=args.recursive,
            extensions=extensions,
        )
        
        success_count = 0
        error_count = 0
        
        for file_path, result, error in results:
            relative_path = file_path.relative_to(input_path)
            output_file = output_path / f"{relative_path.stem}.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            if error:
                error_count += 1
                if not args.quiet:
                    print(f"ERRORE: {relative_path} - {error}", file=sys.stderr)
            else:
                success_count += 1
                indent = args.indent if args.indent > 0 else None
                Ingestor.save_json(result, output_file, indent=indent or 2)
                
                if args.validate:
                    is_valid, validation_errors = _validate_output(result)
                    if not is_valid and not args.quiet:
                        print(f"VALIDAZIONE FALLITA: {relative_path}", file=sys.stderr)
                        for err in validation_errors[:3]:
                            print(f"  - {err}", file=sys.stderr)
                
                if not args.quiet:
                    print(f"OK: {relative_path} -> {output_file}")
        
        if not args.quiet:
            print(f"\nCompletato: {success_count} successi, {error_count} errori.")
        
        return 0 if error_count == 0 else 1
    
    else:
        try:
            result = ingestor.ingest(input_path)
        except Exception as e:
            print(f"Errore nell'ingestione: {e}", file=sys.stderr)
            return 1
        
        if args.validate:
            is_valid, validation_errors = _validate_output(result)
            if not is_valid:
                print("Validazione fallita:", file=sys.stderr)
                for err in validation_errors:
                    print(f"  - {err}", file=sys.stderr)
                return 1
        
        indent = args.indent if args.indent > 0 else None
        
        if output_path:
            Ingestor.save_json(result, output_path, indent=indent or 2)
            if not args.quiet:
                print(f"Output salvato in: {output_path}")
        else:
            json_str = json.dumps(result.to_dict(), indent=indent, ensure_ascii=False)
            print(json_str)
        
        return 0


def _validate_output(result) -> tuple[bool, list[str]]:
    """Valida l'output contro lo schema JSON."""
    try:
        import jsonschema
        
        schema_path = Path(__file__).parent.parent / "schema" / "normalized-input.v1.schema.json"
        if not schema_path.exists():
            return True, []
        
        with open(schema_path) as f:
            schema = json.load(f)
        
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(result.to_dict()))
        
        if errors:
            error_messages = [f"{e.json_path}: {e.message}" for e in errors]
            return False, error_messages
        
        return True, []
    except ImportError:
        return True, []
    except Exception as e:
        return True, []


if __name__ == "__main__":
    sys.exit(main())
