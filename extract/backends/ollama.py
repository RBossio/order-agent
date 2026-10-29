"""Backend Ollama per LLM locale."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMBackend, LLMResponse


class OllamaBackend(LLMBackend):
    """
    Backend per Ollama (LLM locale via HTTP).
    
    Configurazione via variabili d'ambiente:
    - OLLAMA_HOST: URL base (default: http://localhost:11434)
    - OLLAMA_MODEL: Nome del modello (default: qwen2.5:7b-instruct)
    """

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:7b-instruct"

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ):
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)
        self._model = model or os.environ.get("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    def is_available(self) -> bool:
        """Verifica se Ollama è raggiungibile."""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def list_models(self) -> list[str]:
        """Elenca i modelli disponibili su Ollama."""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Genera una risposta usando Ollama.
        
        Usa format="json" se json_schema è fornito.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_schema is not None:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP error {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e.reason}") from e

        message = result.get("message", {})
        content = message.get("content", "")

        tokens_prompt = result.get("prompt_eval_count", 0)
        tokens_completion = result.get("eval_count", 0)
        done_reason = result.get("done_reason", "stop")

        return LLMResponse(
            content=content,
            model=self.model_name,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            finish_reason=done_reason,
            raw_response=result,
        )
