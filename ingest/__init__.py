"""
Modulo ingest per VentureOrder.

Legge email (.eml) o file singoli (PDF, .xlsx/.xls/.csv) e produce
un input normalizzato (NormalizedInput) per la fase successiva di estrazione IA.
"""

__version__ = "1.0.0"

from .models import NormalizedInput, Part, Table, Cell, Warning
from .ingestor import Ingestor

__all__ = [
    "NormalizedInput",
    "Part", 
    "Table",
    "Cell",
    "Warning",
    "Ingestor",
]
