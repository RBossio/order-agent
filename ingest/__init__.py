"""
Modulo ingest per VentureOrder.

Legge email (.eml) o file singoli (PDF, .xlsx/.xls/.csv) e produce
un input normalizzato (NormalizedInput) per la fase successiva di estrazione IA.

Funzionalità di sicurezza (v1.1.0):
- Limite dimensione file configurabile
- Rilevamento tipo file reale via magic number
- Protezione zip bomb per file XLSX
- Sanificazione nomi file allegati
- Rifiuto file eseguibili e macro
"""

__version__ = "1.1.0"

from .config import DEFAULT_CONFIG, IngestConfig
from .ingestor import Ingestor
from .models import (
    Cell,
    NormalizedInput,
    Part,
    Table,
    Warning,
    WarningCodes,
    WarningSeverity,
)
from .security import (
    DetectedFileType,
    detect_file_type,
    sanitize_filename,
    validate_file_for_ingest,
)

__all__ = [
    "DEFAULT_CONFIG",
    "Cell",
    "DetectedFileType",
    "IngestConfig",
    "Ingestor",
    "NormalizedInput",
    "Part",
    "Table",
    "Warning",
    "WarningCodes",
    "WarningSeverity",
    "detect_file_type",
    "sanitize_filename",
    "validate_file_for_ingest",
]
