"""Configurazione per il modulo di ingestione."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IngestConfig:
    """
    Configurazione dei limiti e parametri per l'ingestione.

    Attributes:
        max_file_size_bytes: Dimensione massima per singolo file (default 25 MB)
        max_email_total_size_bytes: Dimensione massima totale per email + allegati (default 50 MB)
        max_attachments: Numero massimo di allegati per email (default 20)
        max_xlsx_decompressed_size_bytes: Dimensione massima decompressa per XLSX (protezione zip bomb, default 100 MB)
        max_filename_length: Lunghezza massima nome file (default 255)
        allowed_extensions: Estensioni consentite (se vuoto, usa le estensioni di default)
        reject_executables: Se True, rifiuta file eseguibili (default True)
        reject_macros: Se True, rifiuta file con macro come .xlsm (default True)
        warn_extension_mismatch: Se True, emette warning se estensione non corrisponde al tipo reale (default True)
        strict_mode: Se True, fallisce invece di emettere warning per problemi non critici (default False)
    """

    max_file_size_bytes: int = 25 * 1024 * 1024  # 25 MB
    max_email_total_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_attachments: int = 20
    max_xlsx_decompressed_size_bytes: int = 100 * 1024 * 1024  # 100 MB
    max_filename_length: int = 255
    allowed_extensions: set[str] = field(default_factory=set)
    reject_executables: bool = True
    reject_macros: bool = True
    warn_extension_mismatch: bool = True
    strict_mode: bool = False

    def __post_init__(self):
        if not self.allowed_extensions:
            self.allowed_extensions = {".eml", ".pdf", ".xlsx", ".xls", ".csv"}


DEFAULT_CONFIG = IngestConfig()
