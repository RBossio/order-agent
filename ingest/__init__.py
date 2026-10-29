"""
Modulo ingest per VentureOrder.

Legge email (.eml) o file singoli (PDF, .xlsx/.xls/.csv) e produce
un input normalizzato (NormalizedInput) per la fase successiva di estrazione IA.
"""

__version__ = "1.0.0"

from .ingestor import Ingestor
from .models import Cell, NormalizedInput, Part, Table, Warning

__all__ = [
    "Cell",
    "Ingestor",
    "NormalizedInput",
    "Part",
    "Table",
    "Warning",
]
