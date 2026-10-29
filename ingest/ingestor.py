"""Ingestor principale che coordina tutti i parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FileType, NormalizedInput, Warning
from .parsers.csv_parser import CsvParser
from .parsers.eml_parser import EmlParser
from .parsers.excel_parser import ExcelParser
from .parsers.pdf_parser import PdfParser


class Ingestor:
    """
    Classe principale per l'ingestione di documenti.
    
    Supporta file .eml, PDF, Excel (.xlsx, .xls) e CSV.
    """

    EXTENSION_MAP = {
        ".eml": FileType.EML,
        ".pdf": FileType.PDF,
        ".xlsx": FileType.XLSX,
        ".xls": FileType.XLS,
        ".csv": FileType.CSV,
    }

    def __init__(self):
        self.eml_parser = EmlParser()
        self.pdf_parser = PdfParser()
        self.excel_parser = ExcelParser()
        self.csv_parser = CsvParser()
        
        self.eml_parser.set_attachment_parsers({
            "PdfParser": self.pdf_parser,
            "ExcelParser": self.excel_parser,
            "CsvParser": self.csv_parser,
        })

    def ingest(self, file_path: Path | str) -> NormalizedInput:
        """
        Ingesta un singolo file e ritorna un NormalizedInput.
        
        Args:
            file_path: Percorso al file da ingestare.
            
        Returns:
            NormalizedInput contenente i dati estratti.
            
        Raises:
            ValueError: Se il tipo di file non è supportato.
            FileNotFoundError: Se il file non esiste.
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File non trovato: {file_path}")
        
        ext = file_path.suffix.lower()
        file_type = self.EXTENSION_MAP.get(ext)
        
        if file_type is None:
            raise ValueError(f"Tipo di file non supportato: {ext}")
        
        if file_type == FileType.EML:
            return self.eml_parser.parse(file_path)
        elif file_type == FileType.PDF:
            return self.pdf_parser.parse(file_path)
        elif file_type in (FileType.XLSX, FileType.XLS):
            return self.excel_parser.parse(file_path)
        elif file_type == FileType.CSV:
            return self.csv_parser.parse(file_path)
        else:
            raise ValueError(f"Parser non disponibile per: {file_type}")

    def ingest_bytes(
        self,
        content: bytes,
        filename: str,
        file_type: FileType | None = None
    ) -> NormalizedInput:
        """
        Ingesta contenuto da bytes.
        
        Args:
            content: Contenuto del file in bytes.
            filename: Nome del file (usato per determinare il tipo).
            file_type: Tipo di file (opzionale, altrimenti dedotto da filename).
            
        Returns:
            NormalizedInput contenente i dati estratti.
        """
        if file_type is None:
            ext = Path(filename).suffix.lower()
            file_type = self.EXTENSION_MAP.get(ext)
        
        if file_type is None:
            raise ValueError(f"Tipo di file non supportato: {filename}")
        
        if file_type == FileType.EML:
            return self.eml_parser.parse_bytes(content, filename=filename)
        elif file_type == FileType.PDF:
            return self.pdf_parser.parse_bytes(content, filename=filename)
        elif file_type in (FileType.XLSX, FileType.XLS):
            return self.excel_parser.parse_bytes(content, filename=filename, file_type=file_type)
        elif file_type == FileType.CSV:
            return self.csv_parser.parse_bytes(content, filename=filename)
        else:
            raise ValueError(f"Parser non disponibile per: {file_type}")

    def ingest_batch(
        self,
        folder_path: Path | str,
        recursive: bool = False,
        extensions: list[str] | None = None
    ) -> list[tuple[Path, NormalizedInput | None, Exception | None]]:
        """
        Ingesta tutti i file supportati da una cartella.
        
        Args:
            folder_path: Percorso alla cartella.
            recursive: Se True, cerca anche nelle sottocartelle.
            extensions: Lista di estensioni da processare (default: tutte supportate).
            
        Returns:
            Lista di tuple (path, result, error) per ogni file processato.
        """
        folder_path = Path(folder_path)
        
        if not folder_path.is_dir():
            raise NotADirectoryError(f"Non è una directory: {folder_path}")
        
        if extensions is None:
            extensions = list(self.EXTENSION_MAP.keys())
        else:
            extensions = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions]
        
        results: list[tuple[Path, NormalizedInput | None, Exception | None]] = []
        
        if recursive:
            files = [f for f in folder_path.rglob("*") if f.is_file()]
        else:
            files = [f for f in folder_path.iterdir() if f.is_file()]
        
        for file_path in sorted(files):
            if file_path.suffix.lower() not in extensions:
                continue
            
            try:
                result = self.ingest(file_path)
                results.append((file_path, result, None))
            except Exception as e:
                results.append((file_path, None, e))
        
        return results

    @staticmethod
    def to_json(result: NormalizedInput, indent: int = 2) -> str:
        """Converte un NormalizedInput in JSON."""
        return json.dumps(result.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def save_json(result: NormalizedInput, output_path: Path | str, indent: int = 2) -> None:
        """Salva un NormalizedInput come file JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=indent, ensure_ascii=False)
