"""
Pre-elaborazione deterministica prima dell'LLM.

Estrae dati strutturati da tabelle Excel/CSV e PDF quando possibile,
riducendo il carico sul modello AI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PreprocessedLine:
    """Riga pre-elaborata da tabella strutturata."""
    row_index: int
    raw_cells: list[Any]
    seller_item_code: str | None = None
    buyer_item_code: str | None = None
    description: str | None = None
    quantity: float | None = None
    uom_raw: str | None = None
    unit_price: float | None = None
    line_amount: float | None = None
    confidence: float = 1.0
    source: str = "table"
    needs_llm: bool = False


@dataclass
class PreprocessedHeader:
    """Testata pre-elaborata."""
    po_number: str | None = None
    po_date: str | None = None
    currency: str | None = None
    buyer_name: str | None = None
    buyer_code: str | None = None
    ship_to_name: str | None = None
    delivery_date: str | None = None
    payment_terms: str | None = None
    notes: str | None = None
    confidence: float = 1.0
    source: str = "structured"


@dataclass
class PreprocessedData:
    """Dati pre-elaborati da un NormalizedInput."""
    header: PreprocessedHeader | None = None
    lines: list[PreprocessedLine] = field(default_factory=list)
    unstructured_text: str = ""
    ambiguous_rows: list[dict] = field(default_factory=list)
    extraction_notes: list[str] = field(default_factory=list)


COMMON_HEADER_PATTERNS = {
    "po_number": [
        r"(?:PO|P\.O\.|Purchase\s*Order|Order)\s*(?:#|No\.?|Number)?[\s:]*([A-Z0-9]+-?[A-Z0-9-]+)",
        r"(?:Ordine|N\.?\s*Ordine)[\s:]*([A-Z0-9]+-?[A-Z0-9-]+)",
    ],
    "po_date": [
        r"(?:Date|Order\s*Date|PO\s*Date)[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(?:Date|Order\s*Date|PO\s*Date)[\s:]*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        r"(?:Data|Data\s*Ordine)[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ],
    "currency": [
        r"\b(USD|EUR|GBP|CAD|CHF)\b",
    ],
    "delivery_date": [
        r"(?:Delivery|Ship|Required)\s*(?:Date|By)[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(?:Consegna|Data\s*Consegna)[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ],
}

COLUMN_MAPPINGS = {
    "item_code": ["item", "code", "sku", "part", "articolo", "codice", "product", "item no", "item #"],
    "customer_code": ["your code", "customer code", "your item", "vs codice", "codice cliente"],
    "description": ["description", "descrizione", "desc", "item description", "product name"],
    "quantity": ["qty", "quantity", "qta", "quantità", "order qty", "ord qty"],
    "uom": ["uom", "unit", "um", "unità", "u/m", "each"],
    "price": ["price", "unit price", "prezzo", "$/unit", "cost", "unit cost"],
    "amount": ["amount", "total", "ext", "extended", "importo", "totale", "line total"],
}


class Preprocessor:
    """
    Pre-elaboratore deterministico per NormalizedInput.

    Estrae dati strutturati (tabelle Excel/CSV, metadati email) senza LLM,
    lasciando solo i casi ambigui per l'elaborazione AI.
    """

    def __init__(self):
        self._column_patterns = self._compile_column_patterns()

    def _compile_column_patterns(self) -> dict[str, re.Pattern]:
        """Compila pattern per riconoscimento colonne."""
        patterns = {}
        for field_name, keywords in COLUMN_MAPPINGS.items():
            pattern = "|".join(re.escape(kw) for kw in keywords)
            patterns[field_name] = re.compile(pattern, re.IGNORECASE)
        return patterns

    def preprocess(self, normalized_input: dict) -> PreprocessedData:
        """
        Pre-elabora un NormalizedInput.

        Args:
            normalized_input: Dizionario con la struttura NormalizedInput.

        Returns:
            PreprocessedData con campi estratti e testo residuo.
        """
        result = PreprocessedData()

        email_meta = normalized_input.get("email_metadata")
        if email_meta:
            result.header = self._extract_header_from_email(email_meta)

        parts = normalized_input.get("parts", [])
        text_parts = []

        for part in parts:
            part_type = part.get("part_type", "")

            if part_type in ("EXCEL_SHEET", "CSV_DATA"):
                tables = part.get("tables", [])
                for table in tables:
                    lines, ambiguous = self._extract_lines_from_table(table)
                    result.lines.extend(lines)
                    result.ambiguous_rows.extend(ambiguous)

            elif part_type == "PDF_PAGE":
                tables = part.get("tables", [])
                for table in tables:
                    lines, ambiguous = self._extract_lines_from_table(table)
                    result.lines.extend(lines)
                    result.ambiguous_rows.extend(ambiguous)

                text = part.get("text") or part.get("text_layout") or ""
                if text:
                    text_parts.append(text)

            elif part_type in ("EMAIL_BODY", "EMAIL_BODY_HTML"):
                text = part.get("text", "")
                if text:
                    text_parts.append(text)
                    if not result.header:
                        result.header = self._extract_header_from_text(text)

        result.unstructured_text = "\n\n".join(text_parts)

        if result.unstructured_text and not result.header:
            result.header = self._extract_header_from_text(result.unstructured_text)

        result.lines = self._renumber_lines(result.lines)

        return result

    def _extract_header_from_email(self, email_meta: dict) -> PreprocessedHeader:
        """Estrae testata da metadati email."""
        header = PreprocessedHeader(source="email_metadata")

        subject = email_meta.get("subject", "")
        if subject:
            for pattern in COMMON_HEADER_PATTERNS["po_number"]:
                match = re.search(pattern, subject, re.IGNORECASE)
                if match:
                    header.po_number = match.group(1)
                    break

        from_name = email_meta.get("from_name", "")
        if from_name:
            header.buyer_name = from_name

        date_parsed = email_meta.get("date_parsed")
        if date_parsed:
            header.po_date = date_parsed[:10] if date_parsed else None

        return header

    def _extract_header_from_text(self, text: str) -> PreprocessedHeader:
        """Estrae testata da testo libero usando pattern."""
        header = PreprocessedHeader(source="text_pattern")

        for field_name, patterns in COMMON_HEADER_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    setattr(header, field_name, match.group(1))
                    break

        return header

    def _extract_lines_from_table(
        self,
        table: dict
    ) -> tuple[list[PreprocessedLine], list[dict]]:
        """
        Estrae righe ordine da una tabella strutturata.

        Returns:
            Tuple di (righe estratte, righe ambigue che richiedono LLM).
        """
        rows = table.get("rows", [])
        if not rows:
            return [], []

        header_idx = table.get("header_row_index")
        if header_idx is None:
            header_idx = self._detect_header_row(rows)

        if header_idx is None or header_idx >= len(rows):
            return [], [{"table_id": table.get("table_id"), "reason": "no_header"}]

        header_row = rows[header_idx]
        column_map = self._map_columns(header_row)

        if not column_map.get("description") and not column_map.get("item_code"):
            return [], [{"table_id": table.get("table_id"), "reason": "missing_key_columns"}]

        lines = []
        ambiguous = []

        for row_idx, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
            cells = [self._get_cell_value(c) for c in row]

            if self._is_empty_or_total_row(cells):
                continue

            line = PreprocessedLine(row_index=row_idx, raw_cells=cells)

            if "item_code" in column_map:
                line.seller_item_code = self._safe_str(cells, column_map["item_code"])

            if "customer_code" in column_map:
                line.buyer_item_code = self._safe_str(cells, column_map["customer_code"])

            if "description" in column_map:
                line.description = self._safe_str(cells, column_map["description"])

            if "quantity" in column_map:
                line.quantity = self._safe_float(cells, column_map["quantity"])

            if "uom" in column_map:
                line.uom_raw = self._safe_str(cells, column_map["uom"]) or "EA"
            else:
                line.uom_raw = "EA"

            if "price" in column_map:
                line.unit_price = self._safe_float(cells, column_map["price"])

            if "amount" in column_map:
                line.line_amount = self._safe_float(cells, column_map["amount"])

            if not line.description and not line.seller_item_code:
                ambiguous.append({
                    "row_index": row_idx,
                    "cells": cells,
                    "reason": "missing_description_and_code",
                })
                continue

            if line.quantity is None:
                line.needs_llm = True
                line.confidence = 0.5

            if not line.description:
                line.description = line.seller_item_code or "Unknown"

            lines.append(line)

        return lines, ambiguous

    def _detect_header_row(self, rows: list) -> int | None:
        """Rileva automaticamente la riga di intestazione."""
        for idx, row in enumerate(rows[:5]):
            cells = [self._get_cell_value(c) for c in row]
            text_cells = [str(c).lower() for c in cells if c]

            matches = 0
            for pattern in self._column_patterns.values():
                if any(pattern.search(t) for t in text_cells):
                    matches += 1

            if matches >= 2:
                return idx

        return 0 if rows else None

    def _map_columns(self, header_row: list) -> dict[str, int]:
        """Mappa i nomi delle colonne agli indici."""
        column_map = {}

        for idx, cell in enumerate(header_row):
            value = self._get_cell_value(cell)
            if not value:
                continue

            text = str(value).lower().strip()

            for field_name, pattern in self._column_patterns.items():
                if pattern.search(text):
                    column_map[field_name] = idx
                    break

        return column_map

    def _get_cell_value(self, cell: Any) -> Any:
        """Estrae il valore da una cella (dict o valore diretto)."""
        if isinstance(cell, dict):
            return cell.get("value")
        return cell

    def _safe_str(self, cells: list, idx: int) -> str | None:
        """Estrae stringa sicura da lista celle."""
        if idx < len(cells):
            val = cells[idx]
            if val is not None:
                return str(val).strip()
        return None

    def _safe_float(self, cells: list, idx: int) -> float | None:
        """Estrae float sicuro da lista celle."""
        if idx < len(cells):
            val = cells[idx]
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).replace(",", "").replace("$", "").replace("€", "").strip()
            try:
                return float(s)
            except ValueError:
                return None
        return None

    def _is_empty_or_total_row(self, cells: list) -> bool:
        """Verifica se la riga è vuota o è una riga di totale."""
        non_empty = [c for c in cells if c is not None and str(c).strip()]
        if not non_empty:
            return True

        first_text = str(non_empty[0]).lower() if non_empty else ""
        total_keywords = ["total", "subtotal", "totale", "sub-total", "grand total", "shipping", "tax"]
        return any(kw in first_text for kw in total_keywords)

    def _renumber_lines(self, lines: list[PreprocessedLine]) -> list[PreprocessedLine]:
        """Rinumera le righe sequenzialmente."""
        for idx, line in enumerate(lines, start=1):
            line.row_index = idx
        return lines
