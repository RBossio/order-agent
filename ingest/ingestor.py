"""Ingestor principale che coordina tutti i parser."""

from __future__ import annotations

import json
from pathlib import Path

from .config import DEFAULT_CONFIG, IngestConfig
from .models import FileType, NormalizedInput, Warning, WarningCodes, WarningSeverity
from .parsers.csv_parser import CsvParser
from .parsers.eml_parser import EmlParser
from .parsers.excel_parser import ExcelParser
from .parsers.pdf_parser import PdfParser
from .security import (
    DetectedFileType,
    detect_file_type,
    is_dangerous_file_type,
    is_extension_type_mismatch,
    sanitize_filename,
    validate_file_for_ingest,
)


class Ingestor:
    """
    Classe principale per l'ingestione di documenti.
    
    Supporta file .eml, PDF, Excel (.xlsx, .xls) e CSV.
    
    Args:
        config: Configurazione personalizzata (opzionale)
    """

    EXTENSION_MAP = {
        ".eml": FileType.EML,
        ".pdf": FileType.PDF,
        ".xlsx": FileType.XLSX,
        ".xls": FileType.XLS,
        ".csv": FileType.CSV,
    }
    
    # Mappa da DetectedFileType a FileType
    DETECTED_TO_FILE_TYPE = {
        DetectedFileType.PDF: FileType.PDF,
        DetectedFileType.XLSX: FileType.XLSX,
        DetectedFileType.XLS: FileType.XLS,
        DetectedFileType.CSV: FileType.CSV,
        DetectedFileType.EML: FileType.EML,
        DetectedFileType.TEXT: FileType.CSV,  # Tratta testo come CSV per default
    }

    def __init__(self, config: IngestConfig | None = None):
        self.config = config or DEFAULT_CONFIG
        
        self.eml_parser = EmlParser(config=self.config)
        self.pdf_parser = PdfParser()
        self.excel_parser = ExcelParser(config=self.config)
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
        
        # Leggi il contenuto per validazione
        with open(file_path, "rb") as f:
            content = f.read()
        
        # Validazione di sicurezza
        validation = validate_file_for_ingest(
            content=content,
            filename=file_path.name,
            max_file_size=self.config.max_file_size_bytes,
            max_xlsx_decompressed_size=self.config.max_xlsx_decompressed_size_bytes,
            max_filename_length=self.config.max_filename_length,
            reject_executables=self.config.reject_executables,
            reject_macros=self.config.reject_macros,
            warn_extension_mismatch=self.config.warn_extension_mismatch,
        )
        
        # Se ci sono errori critici, restituisci NormalizedInput con solo errori
        if not validation.is_valid:
            return self._create_error_result(
                file_path.name,
                content,
                validation.errors,
                validation.warnings,
                str(file_path),
            )
        
        # Determina il tipo di file
        # Prima prova dal tipo rilevato, poi fallback all'estensione
        ext = file_path.suffix.lower()
        file_type = None
        
        if validation.detected_type and validation.detected_type in self.DETECTED_TO_FILE_TYPE:
            file_type = self.DETECTED_TO_FILE_TYPE[validation.detected_type]
        
        if file_type is None:
            file_type = self.EXTENSION_MAP.get(ext)
        
        if file_type is None:
            raise ValueError(f"Tipo di file non supportato: {ext}")
        
        # Parsing
        if file_type == FileType.EML:
            result = self.eml_parser.parse_bytes(content, filename=file_path.name, file_path=str(file_path))
        elif file_type == FileType.PDF:
            result = self.pdf_parser.parse_bytes(content, filename=file_path.name, file_path=str(file_path))
        elif file_type in (FileType.XLSX, FileType.XLS):
            result = self.excel_parser.parse_bytes(content, filename=file_path.name, file_path=str(file_path), file_type=file_type)
        elif file_type == FileType.CSV:
            result = self.csv_parser.parse_bytes(content, filename=file_path.name, file_path=str(file_path))
        else:
            raise ValueError(f"Parser non disponibile per: {file_type}")
        
        # Aggiungi warning dalla validazione
        for warn_msg in validation.warnings:
            result.warnings.append(Warning(
                code=WarningCodes.TYPE_MISMATCH if "estensione" in warn_msg.lower() else WarningCodes.NAME_SANITIZED,
                message=warn_msg,
                severity=WarningSeverity.WARNING,
            ))
        
        return result
    
    def _create_error_result(
        self,
        filename: str,
        content: bytes,
        errors: list[str],
        warnings: list[str],
        file_path: str | None = None,
    ) -> NormalizedInput:
        """Crea un NormalizedInput con solo errori (file rifiutato)."""
        import hashlib
        from .models import Source
        
        # Rileva tipo per il source
        detected = detect_file_type(content)
        file_type = self.DETECTED_TO_FILE_TYPE.get(detected.detected_type, FileType.PDF)
        
        sha256 = hashlib.sha256(content).hexdigest()
        source = Source(
            filename=filename,
            sha256=sha256,
            file_type=file_type,
            file_path=file_path,
            file_size_bytes=len(content),
        )
        
        result = NormalizedInput(source=source)
        
        # Aggiungi errori come warning con severity ERROR
        for error_msg in errors:
            # Determina il codice appropriato
            code = WarningCodes.TYPE_UNSUPPORTED
            if "troppo grande" in error_msg.lower() or "dimensione" in error_msg.lower():
                code = WarningCodes.SIZE_FILE_TOO_LARGE
            elif "zip bomb" in error_msg.lower():
                code = WarningCodes.SIZE_ZIP_BOMB
            elif "eseguibile" in error_msg.lower():
                code = WarningCodes.TYPE_EXECUTABLE
            elif "macro" in error_msg.lower():
                code = WarningCodes.TYPE_MACRO
            
            result.warnings.append(Warning(
                code=code,
                message=error_msg,
                severity=WarningSeverity.ERROR,
            ))
        
        # Aggiungi warning
        for warn_msg in warnings:
            result.warnings.append(Warning(
                code=WarningCodes.NAME_SANITIZED,
                message=warn_msg,
                severity=WarningSeverity.WARNING,
            ))
        
        return result

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
        # Validazione di sicurezza
        validation = validate_file_for_ingest(
            content=content,
            filename=filename,
            max_file_size=self.config.max_file_size_bytes,
            max_xlsx_decompressed_size=self.config.max_xlsx_decompressed_size_bytes,
            max_filename_length=self.config.max_filename_length,
            reject_executables=self.config.reject_executables,
            reject_macros=self.config.reject_macros,
            warn_extension_mismatch=self.config.warn_extension_mismatch,
        )
        
        # Se ci sono errori critici, restituisci NormalizedInput con solo errori
        if not validation.is_valid:
            return self._create_error_result(
                filename,
                content,
                validation.errors,
                validation.warnings,
            )
        
        # Determina il tipo di file
        if file_type is None:
            # Prima prova dal tipo rilevato
            if validation.detected_type and validation.detected_type in self.DETECTED_TO_FILE_TYPE:
                file_type = self.DETECTED_TO_FILE_TYPE[validation.detected_type]
            else:
                ext = Path(filename).suffix.lower()
                file_type = self.EXTENSION_MAP.get(ext)
        
        if file_type is None:
            raise ValueError(f"Tipo di file non supportato: {filename}")
        
        # Usa il nome file sanificato
        safe_filename = validation.sanitized_filename or filename
        
        if file_type == FileType.EML:
            result = self.eml_parser.parse_bytes(content, filename=safe_filename)
        elif file_type == FileType.PDF:
            result = self.pdf_parser.parse_bytes(content, filename=safe_filename)
        elif file_type in (FileType.XLSX, FileType.XLS):
            result = self.excel_parser.parse_bytes(content, filename=safe_filename, file_type=file_type)
        elif file_type == FileType.CSV:
            result = self.csv_parser.parse_bytes(content, filename=safe_filename)
        else:
            raise ValueError(f"Parser non disponibile per: {file_type}")
        
        # Aggiungi warning dalla validazione
        for warn_msg in validation.warnings:
            result.warnings.append(Warning(
                code=WarningCodes.TYPE_MISMATCH if "estensione" in warn_msg.lower() else WarningCodes.NAME_SANITIZED,
                message=warn_msg,
                severity=WarningSeverity.WARNING,
            ))
        
        return result

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
