"""Interfaccia astratta per backend LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Risposta da un backend LLM."""
    content: str
    model: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    finish_reason: str = "stop"
    raw_response: dict[str, Any] | None = None

    @property
    def total_tokens(self) -> int:
        return self.tokens_prompt + self.tokens_completion


class LLMBackend(ABC):
    """
    Interfaccia astratta per backend LLM.
    
    Implementazioni:
    - OllamaBackend: Ollama locale via HTTP
    - MockBackend: Backend deterministico per test
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Genera una risposta dal modello.
        
        Args:
            prompt: Prompt utente.
            system_prompt: Prompt di sistema opzionale.
            json_schema: Schema JSON per output vincolato (se supportato).
            temperature: Temperatura di campionamento (0 = deterministico).
            max_tokens: Massimo numero di token in output.
            
        Returns:
            LLMResponse con il contenuto generato.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se il backend è disponibile."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nome del modello in uso."""
