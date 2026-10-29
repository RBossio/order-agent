"""Backend LLM per l'estrazione ordini."""

from .base import LLMBackend, LLMResponse
from .mock import MockBackend
from .ollama import OllamaBackend

__all__ = ["LLMBackend", "LLMResponse", "MockBackend", "OllamaBackend"]
