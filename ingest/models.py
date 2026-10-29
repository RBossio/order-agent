"""Modelli dati per NormalizedInput."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class FileType(str, Enum):
    EML = "EML"
    PDF = "PDF"
    XLSX = "XLSX"
    XLS = "XLS"
    CSV = "CSV"


class PartType(str, Enum):
    EMAIL_BODY = "EMAIL_BODY"
    EMAIL_BODY_HTML = "EMAIL_BODY_HTML"
    EMAIL_SIGNATURE = "EMAIL_SIGNATURE"
    EMAIL_QUOTED = "EMAIL_QUOTED"
    PDF_PAGE = "PDF_PAGE"
    EXCEL_SHEET = "EXCEL_SHEET"
    CSV_DATA = "CSV_DATA"
    ATTACHMENT = "ATTACHMENT"


@dataclass
class Cell:
    """Cella di una tabella."""
    value: str | int | float | bool | None
    raw_value: str | None = None
    cell_ref: str | None = None
    is_merged: bool = False
    merge_range: str | None = None
    row_span: int | None = None
    col_span: int | None = None

    def to_dict(self) -> dict:
        d = {"value": self.value}
        if self.raw_value is not None:
            d["raw_value"] = self.raw_value
        if self.cell_ref is not None:
            d["cell_ref"] = self.cell_ref
        if self.is_merged:
            d["is_merged"] = True
        if self.merge_range is not None:
            d["merge_range"] = self.merge_range
        if self.row_span is not None:
            d["row_span"] = self.row_span
        if self.col_span is not None:
            d["col_span"] = self.col_span
        return d


@dataclass
class Table:
    """Tabella rilevata."""
    table_id: str = field(default_factory=lambda: f"tbl-{uuid.uuid4().hex[:8]}")
    header_row_index: int | None = None
    rows: list[list[Cell]] = field(default_factory=list)
    bbox: list[float] | None = None
    page_number: int | None = None

    def to_dict(self) -> dict:
        d = {
            "table_id": self.table_id,
            "rows": [[cell.to_dict() for cell in row] for row in self.rows],
        }
        if self.header_row_index is not None:
            d["header_row_index"] = self.header_row_index
        if self.bbox is not None:
            d["bbox"] = self.bbox
        if self.page_number is not None:
            d["page_number"] = self.page_number
        return d


class WarningSeverity(str, Enum):
    """Livello di gravità di un avviso."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Warning:
    """Avviso non bloccante."""
    code: str
    message: str
    part_id: str | None = None
    details: dict[str, Any] | None = None
    severity: WarningSeverity = WarningSeverity.WARNING

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.part_id is not None:
            d["part_id"] = self.part_id
        if self.details is not None:
            d["details"] = self.details
        if self.severity != WarningSeverity.WARNING:
            d["severity"] = self.severity.value
        return d


# Codici di errore/warning standardizzati
class WarningCodes:
    """Codici di warning/errore standardizzati."""
    # Limiti dimensione
    SIZE_FILE_TOO_LARGE = "SIZ-01"
    SIZE_EMAIL_TOO_LARGE = "SIZ-02"
    SIZE_TOO_MANY_ATTACHMENTS = "SIZ-03"
    SIZE_ZIP_BOMB = "SIZ-04"
    
    # Tipo file
    TYPE_MISMATCH = "TYP-01"
    TYPE_UNSUPPORTED = "TYP-02"
    TYPE_EXECUTABLE = "TYP-03"
    TYPE_MACRO = "TYP-04"
    TYPE_UNKNOWN = "TYP-05"
    
    # Nome file
    NAME_SANITIZED = "NAM-01"
    NAME_PATH_TRAVERSAL = "NAM-02"
    NAME_RESERVED = "NAM-03"
    NAME_TRUNCATED = "NAM-04"
    
    # Allegati (esistenti)
    ATT_UNSUPPORTED = "ATT-01"
    ATT_PARSE_ERROR = "ATT-02"
    ATT_SKIPPED = "ATT-03"
    
    # PDF (esistenti)
    PDF_NEEDS_OCR = "PDF-01"
    PDF_PARSE_ERROR = "PDF-02"
    PDF_TABLE_ERROR = "PDF-03"
    
    # Excel (esistenti)
    XLS_PARSE_ERROR = "XLS-01"
    XLS_XLRD_MISSING = "XLS-02"
    XLS_XLS_ERROR = "XLS-03"
    
    # CSV (esistenti)
    CSV_PARSE_ERROR = "CSV-01"


@dataclass
class EmailAddress:
    """Indirizzo email con nome opzionale."""
    name: str | None = None
    address: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "address": self.address}


@dataclass
class EmailMetadata:
    """Metadati email."""
    message_id: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    to_addresses: list[EmailAddress] = field(default_factory=list)
    cc_addresses: list[EmailAddress] = field(default_factory=list)
    subject: str | None = None
    date: str | None = None
    date_parsed: str | None = None

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "to_addresses": [a.to_dict() for a in self.to_addresses],
            "cc_addresses": [a.to_dict() for a in self.cc_addresses],
            "subject": self.subject,
            "date": self.date,
            "date_parsed": self.date_parsed,
        }


@dataclass
class Source:
    """Metadati del file sorgente."""
    filename: str
    sha256: str
    file_type: FileType
    file_path: str | None = None
    file_size_bytes: int | None = None

    def to_dict(self) -> dict:
        d = {
            "filename": self.filename,
            "sha256": self.sha256,
            "file_type": self.file_type.value,
        }
        if self.file_path is not None:
            d["file_path"] = self.file_path
        if self.file_size_bytes is not None:
            d["file_size_bytes"] = self.file_size_bytes
        return d


@dataclass
class Part:
    """Parte di un documento."""
    part_id: str = field(default_factory=lambda: f"part-{uuid.uuid4().hex[:8]}")
    part_type: PartType = PartType.EMAIL_BODY
    source_filename: str | None = None
    mime_type: str | None = None
    sha256: str = ""
    text: str | None = None
    text_layout: str | None = None
    tables: list[Table] = field(default_factory=list)
    page_number: int | None = None
    sheet_name: str | None = None
    sheet_index: int | None = None
    needs_ocr: bool = False
    metadata: dict[str, Any] | None = None

    def compute_sha256(self, content: bytes | str) -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.sha256 = hashlib.sha256(content).hexdigest()
        return self.sha256

    def to_dict(self) -> dict:
        d = {
            "part_id": self.part_id,
            "part_type": self.part_type.value,
            "sha256": self.sha256,
        }
        if self.source_filename is not None:
            d["source_filename"] = self.source_filename
        if self.mime_type is not None:
            d["mime_type"] = self.mime_type
        if self.text is not None:
            d["text"] = self.text
        if self.text_layout is not None:
            d["text_layout"] = self.text_layout
        if self.tables:
            d["tables"] = [t.to_dict() for t in self.tables]
        if self.page_number is not None:
            d["page_number"] = self.page_number
        if self.sheet_name is not None:
            d["sheet_name"] = self.sheet_name
        if self.sheet_index is not None:
            d["sheet_index"] = self.sheet_index
        if self.needs_ocr:
            d["needs_ocr"] = True
        if self.metadata is not None:
            d["metadata"] = self.metadata
        return d


@dataclass
class NormalizedInput:
    """Documento normalizzato pronto per l'estrazione IA."""
    input_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: Source | None = None
    email_metadata: EmailMetadata | None = None
    ingested_at: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    parts: list[Part] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "schema_version": "1.0",
            "input_id": self.input_id,
            "source": self.source.to_dict() if self.source else None,
            "ingested_at": self.ingested_at,
            "parts": [p.to_dict() for p in self.parts],
        }
        if self.email_metadata is not None:
            d["email_metadata"] = self.email_metadata.to_dict()
        if self.warnings:
            d["warnings"] = [w.to_dict() for w in self.warnings]
        return d
