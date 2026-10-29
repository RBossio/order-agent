"""Backend LLM per l'estrazione ordini."""

from .base import LLMBackend, LLMResponse
from .ollama import OllamaBackend
from .mock import MockBackend

__all__ = ["LLMBackend", "LLMResponse", "OllamaBackend", "MockBackend"]
