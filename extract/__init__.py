"""
Modulo extract - Estrazione ordini da NormalizedInput a VentureOrder.

Questo modulo converte documenti normalizzati (NormalizedInput) in ordini
strutturati secondo lo schema venture-order.v1, usando un LLM locale.
"""

from .extractor import OrderExtractor
from .models import (
    ExtractionResult,
    ExtractedOrder,
    ExtractedLine,
    FieldConfidence,
    ExtractionWarning,
)
from .backends import LLMBackend, OllamaBackend, MockBackend

__all__ = [
    "OrderExtractor",
    "ExtractionResult",
    "ExtractedOrder",
    "ExtractedLine",
    "FieldConfidence",
    "ExtractionWarning",
    "LLMBackend",
    "OllamaBackend",
    "MockBackend",
]
