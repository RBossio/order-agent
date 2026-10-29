"""
Modulo extract - Estrazione ordini da NormalizedInput a VentureOrder.

Questo modulo converte documenti normalizzati (NormalizedInput) in ordini
strutturati secondo lo schema venture-order.v1, usando un LLM locale.
"""

from .backends import LLMBackend, MockBackend, OllamaBackend
from .extractor import OrderExtractor
from .models import (
    ExtractedLine,
    ExtractedOrder,
    ExtractionResult,
    ExtractionWarning,
    FieldConfidence,
)

__all__ = [
    "ExtractedLine",
    "ExtractedOrder",
    "ExtractionResult",
    "ExtractionWarning",
    "FieldConfidence",
    "LLMBackend",
    "MockBackend",
    "OllamaBackend",
    "OrderExtractor",
]
