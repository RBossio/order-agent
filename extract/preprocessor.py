"""
Pre-elaborazione deterministica prima dell'LLM.

Estrae dati strutturati da tabelle Excel/CSV e PDF (pdfplumber) quando possibile:
testata (PO, data) e colonne (codice, quantità, UoM, prezzo). L'LLM resta
ripiego e per le email.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_WORD_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_WORD_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

TEXT_PART_TYPES = {
    "EMAIL_BODY", "EMAIL_BODY_HTML", "EMAIL_SIGNATURE", "EMAIL_QUOTED",
}
TABLE_PART_TYPES = {"EXCEL_SHEET", "CSV_DATA", "PDF_PAGE"}


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
    total_amount: float | None = None
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
    source_disagreement: bool = False
    total_amount: float | None = None


COMMON_HEADER_PATTERNS = {
    "po_number": [
        r"(?:PO|P\.O\.|Purchase\s*Order)(?:\s+(?:#|No\.?|Number))?[ \t:]+([A-Z0-9][A-Z0-9-]{3,})",
        r"(?:Ordine|N\.?\s*Ordine)[ \t:]+([A-Z0-9][A-Z0-9-]{3,})",
    ],
    "po_date": [
        r"(?:PO\s*Date|Order\s*Date)[ \t:]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        r"(?:PO\s*Date|Order\s*Date)[ \t:]+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        r"(?:PO\s*Date|Order\s*Date)[ \t:]+(\d{1,2}[-/\s]+[A-Za-z]{3,9}[-/\s,]+\d{2,4})",
        r"(?:PO\s*Date|Order\s*Date)[ \t:]+([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
        r"(?:^|\n)Date[ \t:]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        r"(?:^|\n)Date[ \t:]+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        r"(?:^|\n)Date[ \t:]+(\d{1,2}[-/\s]+[A-Za-z]{3,9}[-/\s,]+\d{2,4})",
        r"(?:^|\n)Date[ \t:]+([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
        r"(?:Data|Data\s*Ordine)[ \t:]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
    ],
    "currency": [
        r"\b(USD|EUR|GBP|CAD|CHF)\b",
    ],
    "delivery_date": [
        r"(?:Delivery requested by|Need by)[ \t:]+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        r"(?:Delivery|Ship|Required)\s*(?:Date|By)[ \t:]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        r"(?:Delivery|Ship|Required)\s*(?:Date|By)[ \t:]+(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
        r"(?:Delivery|Ship|Required)\s*(?:Date|By)[ \t:]+(\d{1,2}[-/\s]+[A-Za-z]{3,9}[-/\s,]+\d{2,4})",
        r"(?:Consegna|Data\s*Consegna)[ \t:]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
    ],
}

EMAIL_ITEM_RE = re.compile(
    r"^\s*(\d+)\.\s*\[([^\]]+)\]\s*(.+?)\s*$",
    re.MULTILINE,
)
EMAIL_QTY_RE = re.compile(
    r"Qty:\s*([A-Za-z-]+|\d+(?:\.\d+)?)\s+([A-Za-z]+)\s*(?:@\s*\$?\s*([\d.,]+))?",
    re.IGNORECASE,
)

COLUMN_PHRASES: list[tuple[str, tuple[str, ...]]] = [
    ("customer_code", (
        "your code", "customer code", "your item", "vs codice", "codice cliente",
    )),
    ("item_code", (
        "item code", "item no", "item #", "item number", "part number",
        "codice articolo", "product code", "sku", "articolo", "codice", "item", "code",
    )),
    ("description", (
        "item description", "product name", "description", "descrizione", "desc",
    )),
    ("quantity", (
        "order qty", "ord qty", "quantity", "quantità", "qty", "qta",
    )),
    ("price", (
        "unit price", "unit cost", "$/unit", "prezzo unitario", "price", "prezzo", "cost",
    )),
    ("amount", (
        "line total", "line amount", "ext price", "extended", "importo",
        "totale riga", "amount",
    )),
    ("uom", (
        "uom", "u/m", "unità", "uom code", "unit of measure",
    )),
]

KV_LABELS: dict[str, tuple[str, ...]] = {
    "po_number": ("po number", "p.o. number", "po #", "po no", "order number", "purchase order no"),
    "po_date": ("order date", "po date", "date"),
    "delivery_date": ("delivery date", "need by", "ship date", "required date", "delivery requested by"),
    "buyer_name": ("company", "customer", "from", "buyer", "bill to"),
    "ship_to_name": ("ship to", "deliver to", "ship-to"),
    "currency": ("currency",),
    "payment_terms": ("payment terms", "terms"),
}


class Preprocessor:
    """
    Pre-elaboratore deterministico per NormalizedInput.

    Estrae dati strutturati (tabelle Excel/CSV/PDF, metadati email) senza LLM,
    lasciando solo i casi ambigui per l'elaborazione AI.
    """

    def preprocess(self, normalized_input: dict) -> PreprocessedData:
        """Pre-elabora un NormalizedInput."""
        result = PreprocessedData()

        email_meta = normalized_input.get("email_metadata")
        if email_meta:
            result.header = self._extract_header_from_email(email_meta)

        parts = normalized_input.get("parts", [])
        text_parts: list[str] = []
        table_lines: list[PreprocessedLine] = []
        email_lines: list[PreprocessedLine] = []
        totals: list[float] = []

        for part in parts:
            part_type = part.get("part_type", "")
            part_text = part.get("text") or part.get("text_layout") or ""

            if part_type in TABLE_PART_TYPES:
                for table in part.get("tables") or []:
                    lines, ambiguous, total = self._extract_lines_from_table(table)
                    table_lines.extend(lines)
                    result.ambiguous_rows.extend(ambiguous)
                    if total is not None:
                        totals.append(total)
                    kv_header = self._extract_header_from_table_kv(table)
                    if result.header is None:
                        result.header = kv_header
                    else:
                        self._overlay_header(result.header, kv_header)
                if part_text:
                    text_parts.append(part_text)
                    text_header = self._extract_header_from_text(part_text)
                    if result.header is None:
                        result.header = text_header
                    else:
                        self._overlay_header(result.header, text_header)

            elif part_type in TEXT_PART_TYPES:
                if part_text:
                    text_parts.append(part_text)
                    text_header = self._extract_header_from_text(part_text)
                    if result.header is None:
                        result.header = text_header
                    else:
                        self._overlay_header(result.header, text_header)
                    email_lines.extend(self._extract_lines_from_email_text(part_text))

        result.unstructured_text = "\n\n".join(text_parts)

        if result.unstructured_text:
            text_header = self._extract_header_from_text(result.unstructured_text)
            if result.header is None:
                result.header = text_header
            else:
                self._overlay_header(result.header, text_header)
            if not email_lines:
                email_lines.extend(self._extract_lines_from_email_text(result.unstructured_text))

        if email_lines and table_lines:
            if self._lines_disagree(email_lines, table_lines):
                result.lines = email_lines
                result.source_disagreement = True
                result.extraction_notes.append("email_attachment_disagreement")
                for line in result.lines:
                    line.confidence = min(line.confidence, 0.45)
            else:
                result.lines = table_lines
        elif table_lines:
            result.lines = table_lines
        else:
            result.lines = email_lines

        if totals:
            result.total_amount = totals[-1]
            if result.header:
                result.header.total_amount = totals[-1]

        if result.header and result.header.currency is None:
            if "$" in result.unstructured_text:
                result.header.currency = "USD"

        result.lines = self._renumber_lines(result.lines)
        return result

    @staticmethod
    def _looks_like_po(value: str | None) -> bool:
        if not value:
            return False
        token = value.strip()
        if token.upper() in {"PO", "FROM", "ORDER", "NUMBER", "THE", "PURCHASE"}:
            return False
        return any(ch.isdigit() for ch in token) and len(token) >= 4

    def _overlay_header(self, target: PreprocessedHeader, source: PreprocessedHeader) -> None:
        """Sovrascrive i campi testata con quelli trovati nel testo del documento."""
        if self._looks_like_po(source.po_number) and (
            not self._looks_like_po(target.po_number)
            or len(source.po_number or "") >= len(target.po_number or "")
        ):
            target.po_number = source.po_number
        if source.po_date:
            target.po_date = source.po_date
        if source.currency:
            target.currency = source.currency
        if source.delivery_date:
            target.delivery_date = source.delivery_date
        if source.buyer_name and not target.buyer_name:
            target.buyer_name = source.buyer_name
        if source.ship_to_name:
            target.ship_to_name = source.ship_to_name
        if source.payment_terms and not target.payment_terms:
            target.payment_terms = source.payment_terms
        if source.total_amount is not None:
            target.total_amount = source.total_amount

    def _extract_lines_from_email_text(self, text: str) -> list[PreprocessedLine]:
        """Estrae righe da liste d'ordine in testo email (pattern '1. [SKU] desc')."""
        lines: list[PreprocessedLine] = []
        items = list(EMAIL_ITEM_RE.finditer(text))
        for idx, match in enumerate(items):
            start = match.end()
            end = items[idx + 1].start() if idx + 1 < len(items) else len(text)
            block = text[start:end]
            qty_match = EMAIL_QTY_RE.search(block)

            code = match.group(2).strip()
            description = match.group(3).strip()
            quantity = None
            uom_raw = "EA"
            unit_price = None
            needs_llm = False

            if qty_match:
                quantity = parse_quantity_token(qty_match.group(1))
                if quantity is None:
                    needs_llm = True
                uom_raw = qty_match.group(2).upper()
                if qty_match.group(3):
                    try:
                        unit_price = float(qty_match.group(3).replace(",", ""))
                    except ValueError:
                        unit_price = None
            else:
                needs_llm = True

            if not description:
                continue

            lines.append(PreprocessedLine(
                row_index=idx + 1,
                raw_cells=[code, description],
                seller_item_code=code,
                description=description,
                quantity=quantity,
                uom_raw=uom_raw,
                unit_price=unit_price,
                line_amount=(
                    quantity * unit_price
                    if quantity is not None and unit_price is not None
                    else None
                ),
                confidence=0.9 if not needs_llm else 0.5,
                source="email_text",
                needs_llm=needs_llm,
            ))
        return lines

    def _extract_header_from_email(self, email_meta: dict) -> PreprocessedHeader:
        """Estrae testata da metadati email. Non usa Date: come po_date."""
        header = PreprocessedHeader(source="email_metadata")

        subject = email_meta.get("subject", "")
        if subject:
            for pattern in COMMON_HEADER_PATTERNS["po_number"]:
                match = re.search(pattern, subject, re.IGNORECASE)
                if match and self._looks_like_po(match.group(1)):
                    header.po_number = match.group(1)
                    break

        from_name = email_meta.get("from_name", "")
        if from_name:
            header.buyer_name = from_name

        return header

    def _extract_header_from_text(self, text: str) -> PreprocessedHeader:
        """Estrae testata da testo libero usando pattern."""
        header = PreprocessedHeader(source="text_pattern")

        for field_name, patterns in COMMON_HEADER_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1)
                    if field_name == "po_number" and not self._looks_like_po(value):
                        continue
                    setattr(header, field_name, value.strip())
                    break

        company = re.search(
            r"(?:Company|Customer|From)[ \t:]+(.+)",
            text,
            re.IGNORECASE,
        )
        if company and not header.buyer_name:
            header.buyer_name = company.group(1).strip()

        ship = re.search(r"Ship To[ \t:]+(.+)", text, re.IGNORECASE)
        if ship:
            header.ship_to_name = ship.group(1).strip()

        return header

    def _extract_header_from_table_kv(self, table: dict) -> PreprocessedHeader:
        """Legge coppie etichetta/valore nelle righe sopra la testata colonne."""
        header = PreprocessedHeader(source="table_kv")
        rows = table.get("rows") or []
        header_idx = table.get("header_row_index")
        if header_idx is None:
            header_idx = self._detect_header_row(rows)
        limit = header_idx if header_idx is not None else min(len(rows), 12)

        for row in rows[:limit]:
            cells = [self._get_cell_value(c) for c in row]
            nonempty = [c for c in cells if c is not None and str(c).strip()]
            if not nonempty:
                continue
            label = str(nonempty[0]).strip().rstrip(":").lower()
            value = str(nonempty[1]).strip() if len(nonempty) > 1 else ""
            if not value and ":" in str(nonempty[0]):
                left, _, right = str(nonempty[0]).partition(":")
                label, value = left.strip().lower(), right.strip()
            field = self._match_kv_label(label)
            if not field or not value:
                continue
            if field == "po_number" and not self._looks_like_po(value):
                continue
            setattr(header, field, value)
        return header

    @staticmethod
    def _match_kv_label(label: str) -> str | None:
        compact = label.strip().rstrip(":").lower()
        best: str | None = None
        best_len = 0
        for field_name, phrases in KV_LABELS.items():
            for phrase in phrases:
                if compact == phrase or compact.startswith(phrase):
                    if len(phrase) > best_len:
                        best, best_len = field_name, len(phrase)
        return best

    def _extract_lines_from_table(
        self,
        table: dict,
    ) -> tuple[list[PreprocessedLine], list[dict], float | None]:
        """Estrae righe ordine da una tabella strutturata."""
        rows = table.get("rows", [])
        if not rows:
            return [], [], None

        header_idx = table.get("header_row_index")
        if header_idx is None:
            header_idx = self._detect_header_row(rows)

        if header_idx is None or header_idx >= len(rows):
            return [], [{"table_id": table.get("table_id"), "reason": "no_header"}], None

        header_row = rows[header_idx]
        column_map = self._map_columns(header_row)

        has_id = "description" in column_map or "item_code" in column_map
        has_qty = "quantity" in column_map or "price" in column_map
        if not (has_id and has_qty):
            return [], [{"table_id": table.get("table_id"), "reason": "missing_key_columns"}], None

        lines: list[PreprocessedLine] = []
        ambiguous: list[dict] = []
        total_amount: float | None = None

        for row_idx, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
            cells = [self._get_cell_value(c) for c in row]

            if self._is_empty_or_total_row(cells):
                if "amount" in column_map:
                    maybe = self._safe_float(cells, column_map["amount"])
                    first = str(next((c for c in cells if c is not None and str(c).strip()), "")).lower()
                    if maybe is not None and any(kw in first for kw in ("total", "totale", "grand")):
                        total_amount = maybe
                continue

            line = PreprocessedLine(row_index=row_idx, raw_cells=cells)

            if "item_code" in column_map:
                line.seller_item_code = self._safe_str(cells, column_map["item_code"])

            if "customer_code" in column_map:
                line.buyer_item_code = self._safe_str(cells, column_map["customer_code"])

            if "description" in column_map:
                line.description = self._safe_str(cells, column_map["description"])

            if "quantity" in column_map:
                raw_qty = self._safe_str(cells, column_map["quantity"])
                line.quantity = parse_quantity_token(raw_qty) if raw_qty else self._safe_float(
                    cells, column_map["quantity"]
                )

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

            line.seller_item_code, line.description = _repair_split_sku(
                line.seller_item_code, line.description
            )

            lines.append(line)

        return lines, ambiguous, total_amount

    def _detect_header_row(self, rows: list) -> int | None:
        """Rileva automaticamente la riga di intestazione (prime 20 righe)."""
        for idx, row in enumerate(rows[:20]):
            cells = [self._get_cell_value(c) for c in row]
            text_cells = [str(c).lower() for c in cells if c]
            matches = sum(1 for text in text_cells if self._match_column(text))
            if matches >= 2:
                return idx
        return 0 if rows else None

    def _map_columns(self, header_row: list) -> dict[str, int]:
        """Mappa i nomi delle colonne agli indici (frase più lunga vince)."""
        column_map: dict[str, int] = {}
        for idx, cell in enumerate(header_row):
            value = self._get_cell_value(cell)
            if not value:
                continue
            field = self._match_column(str(value))
            if field and field not in column_map:
                column_map[field] = idx
        return column_map

    @staticmethod
    def _match_column(text: str) -> str | None:
        compact = text.lower().strip().rstrip(":#")
        if compact in {"unit", "units"}:
            return "uom"
        best: str | None = None
        best_len = 0
        for field_name, phrases in COLUMN_PHRASES:
            for phrase in phrases:
                if phrase == compact or phrase in compact:
                    if len(phrase) > best_len:
                        best, best_len = field_name, len(phrase)
        return best

    def _get_cell_value(self, cell: Any) -> Any:
        if isinstance(cell, dict):
            return cell.get("value")
        return cell

    def _safe_str(self, cells: list, idx: int) -> str | None:
        if idx < len(cells):
            val = cells[idx]
            if val is not None:
                text = str(val).strip()
                return text or None
        return None

    def _safe_float(self, cells: list, idx: int) -> float | None:
        if idx < len(cells):
            val = cells[idx]
            if val is None:
                return None
            if isinstance(val, int | float):
                return float(val)
            return parse_quantity_token(str(val))
        return None

    def _is_empty_or_total_row(self, cells: list) -> bool:
        nonempty = [c for c in cells if c is not None and str(c).strip()]
        if not nonempty:
            return True
        first_text = str(nonempty[0]).lower()
        total_keywords = ("total", "subtotal", "totale", "sub-total", "grand total", "shipping", "tax")
        return any(kw in first_text for kw in total_keywords)

    def _renumber_lines(self, lines: list[PreprocessedLine]) -> list[PreprocessedLine]:
        for idx, line in enumerate(lines, start=1):
            line.row_index = idx
        return lines

    @staticmethod
    def _lines_disagree(
        left: list[PreprocessedLine],
        right: list[PreprocessedLine],
    ) -> bool:
        def keyset(lines: list[PreprocessedLine]) -> set[tuple[str, float | None]]:
            keys: set[tuple[str, float | None]] = set()
            for line in lines:
                code = (line.seller_item_code or line.buyer_item_code or "").strip().upper()
                if code:
                    keys.add((code, line.quantity))
            return keys

        a, b = keyset(left), keyset(right)
        if not a or not b:
            return False
        return a != b


def _repair_split_sku(code: str | None, description: str | None) -> tuple[str | None, str | None]:
    """Ricompone SKU spezzati da pdfplumber (``FST-FWS-34-10`` + ``-1Flat Washer``)."""
    if not code or not description:
        return code, description
    lead = re.match(r"^(-\d+)(.*)$", description)
    if not lead:
        return code, description
    rest = lead.group(2).lstrip(" -")
    return code + lead.group(1), rest or description


def parse_quantity_token(raw: str | None) -> float | None:
    """Parsa una quantità numerica o in lettere (``twenty-four``)."""
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)
    text = str(raw).replace(",", "").replace("$", "").replace("€", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    token = text.lower().replace("_", "-")
    if token in _WORD_ONES:
        return float(_WORD_ONES[token])
    if token in _WORD_TENS:
        return float(_WORD_TENS[token])
    if "-" in token:
        tens, _, ones = token.partition("-")
        if tens in _WORD_TENS and ones in _WORD_ONES:
            return float(_WORD_TENS[tens] + _WORD_ONES[ones])
    return None
