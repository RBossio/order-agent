"""Parsing e normalizzazione date per estrazione e controlli."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_NAMED_DMY = re.compile(
    r"(\d{1,2})[-/\s.]+([A-Za-z]{3,9})[-/\s.,]+(\d{2,4})",
)
_NAMED_MDY = re.compile(
    r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{2,4})",
)


def _year(value: int) -> int:
    if value < 100:
        return value + 2000
    return value


def parse_date_tuple(value: Any) -> tuple[int, int, int] | None:
    """Parsa una data in ``(year, month, day)`` da formati ISO, US, EU o testuali."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    named = _NAMED_DMY.match(text)
    if named:
        month = _MONTHS.get(named.group(2).lower())
        if month:
            return (_year(int(named.group(3))), month, int(named.group(1)))

    named_mdy = _NAMED_MDY.match(text)
    if named_mdy:
        month = _MONTHS.get(named_mdy.group(1).lower())
        if month:
            return (_year(int(named_mdy.group(3))), month, int(named_mdy.group(2)))

    token = text[:10]
    for sep in ("-", "/", "."):
        if sep not in token:
            continue
        parts = token.split(sep)
        if len(parts) != 3:
            continue
        try:
            first, second, third = (int(part) for part in parts)
        except ValueError:
            continue
        if first >= 1000:
            return (first, second, third)
        third = _year(third)
        if first > 12:
            return (third, second, first)
        return (third, first, second)
    return None


def to_iso_date(value: Any) -> str | None:
    """Normalizza una data a ``YYYY-MM-DD``, o ``None`` se non parsabile."""
    parsed = parse_date_tuple(value)
    if parsed is None:
        return None
    year, month, day = parsed
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_date_obj(value: Any) -> date | None:
    """Parsa una data in ``datetime.date``."""
    iso = to_iso_date(value)
    if iso is None:
        return None
    return date.fromisoformat(iso)
