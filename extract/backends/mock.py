"""Backend mock deterministico per test."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .base import LLMBackend, LLMResponse


class MockBackend(LLMBackend):
    """
    Backend deterministico per test (nessuna GPU richiesta).
    
    Estrae informazioni dal prompt usando regex e pattern matching.
    Utile per test CI dove non è disponibile un LLM reale.
    """

    def __init__(self, deterministic_seed: int = 42):
        self._seed = deterministic_seed
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return "mock/deterministic"

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Genera una risposta deterministica basata sul prompt.
        
        Estrae informazioni usando pattern matching e heuristics.
        """
        self._call_count += 1
        
        content = self._extract_from_prompt(prompt)
        
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        tokens_estimate = len(prompt.split()) + len(content.split())
        
        return LLMResponse(
            content=content,
            model=self.model_name,
            tokens_prompt=len(prompt.split()),
            tokens_completion=len(content.split()),
            finish_reason="stop",
            raw_response={"mock": True, "prompt_hash": prompt_hash},
        )

    def _extract_from_prompt(self, prompt: str) -> str:
        """Estrae dati dal prompt usando heuristics."""
        result: dict[str, Any] = {
            "header": {},
            "buyer": {},
            "lines": [],
        }
        
        po_match = re.search(
            r'(?:PO|P\.O\.|Purchase Order|Order)[\s#:]*([A-Z0-9]+-?[A-Z0-9]+)',
            prompt,
            re.IGNORECASE
        )
        if po_match:
            result["header"]["po_number"] = po_match.group(1)
        
        date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, prompt, re.IGNORECASE)
            if date_match:
                result["header"]["po_date"] = date_match.group(1)
                break
        
        if "po_date" not in result["header"]:
            result["header"]["po_date"] = "2026-01-01"
        
        currency_match = re.search(r'\b(USD|EUR|GBP|CAD)\b', prompt)
        result["header"]["currency"] = currency_match.group(1) if currency_match else "USD"
        
        buyer_patterns = [
            r'(?:From|Buyer|Customer|Company)[:\s]+([A-Za-z0-9\s&.,]+?)(?:\n|$)',
            r'([A-Za-z]+(?:\s+[A-Za-z]+)*\s+(?:Inc\.|LLC|Corp\.|Ltd\.))',
        ]
        for pattern in buyer_patterns:
            buyer_match = re.search(pattern, prompt)
            if buyer_match:
                result["buyer"]["name"] = buyer_match.group(1).strip()
                break
        
        lines = self._extract_lines_from_prompt(prompt)
        result["lines"] = lines
        
        return json.dumps(result, ensure_ascii=False)

    def _extract_lines_from_prompt(self, prompt: str) -> list[dict]:
        """Estrae righe ordine dal prompt."""
        lines = []
        line_no = 1
        
        line_pattern = re.compile(
            r'(\d+)\s*[|\t]+\s*'
            r'([A-Z0-9]+-?[A-Z0-9-]*)\s*[|\t]+\s*'
            r'([^|\t\n]+?)\s*[|\t]+\s*'
            r'(\d+(?:\.\d+)?)\s*[|\t]+\s*'
            r'([A-Z]{2,3})\s*[|\t]*'
            r'(?:\$?\s*(\d+(?:\.\d{2})?)\s*[|\t]*)?'
        )
        
        for match in line_pattern.finditer(prompt):
            lines.append({
                "line_no": int(match.group(1)) if match.group(1).isdigit() else line_no,
                "seller_item_code": match.group(2),
                "description": match.group(3).strip(),
                "quantity": float(match.group(4)),
                "uom_raw": match.group(5),
                "unit_price": float(match.group(6)) if match.group(6) else None,
            })
            line_no += 1
        
        if not lines:
            simple_pattern = re.compile(
                r'([A-Z]{2,4}-[A-Z0-9-]+)\s+'
                r'([^0-9\n]{5,50}?)\s+'
                r'(\d+(?:\.\d+)?)\s*'
                r'(EA|CS|BX|PK|DZ|CT|GAL|LB|KG)?'
            )
            for match in simple_pattern.finditer(prompt):
                lines.append({
                    "line_no": line_no,
                    "seller_item_code": match.group(1),
                    "description": match.group(2).strip(),
                    "quantity": float(match.group(3)),
                    "uom_raw": match.group(4) or "EA",
                })
                line_no += 1
        
        if not lines:
            lines.append({
                "line_no": 1,
                "description": "Unknown item",
                "quantity": 1,
                "uom_raw": "EA",
            })
        
        return lines

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset_call_count(self) -> None:
        self._call_count = 0
