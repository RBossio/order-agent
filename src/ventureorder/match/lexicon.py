"""Lessico MRO/JanSan e attributi (misura, colore) per il fuzzy match."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_ABBREVIATIONS: dict[str, str] = {
    "HCS": "hex cap screw",
    "SHCS": "socket head cap screw",
    "GR5": "grade 5",
    "GR8": "grade 8",
    "ZN": "zinc",
    "ZP": "zinc",
    "SS": "stainless",
    "NIT": "nitrile",
    "PF": "powder free",
    "AF": "anti fog",
    "CLR": "clear",
    "BLK": "black",
    "BLU": "blue",
    "WHT": "white",
    "LNR": "liner",
    "RTU": "ready to use",
    "CONC": "concentrate",
    "NEUT": "neutral",
    "MIC": "micron",
    "LG": "large",
    "MD": "medium",
    "SM": "small",
}

DEFAULT_COLORS: dict[str, str] = {
    "blk": "black",
    "black": "black",
    "blu": "blue",
    "blue": "blue",
    "clr": "clear",
    "clear": "clear",
    "wht": "white",
    "white": "white",
    "amber": "amber",
    "smoke": "smoke",
    "nat": "natural",
    "natural": "natural",
    "grn": "green",
    "green": "green",
    "red": "red",
    "ylw": "yellow",
    "yellow": "yellow",
    "zn": "zinc",
    "zinc": "zinc",
    "zp": "zinc",
}

_DIM = re.compile(r"\b(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\b")
_MIL = re.compile(r"\b(\d+(?:\.\d+)?)\s*mil\b", re.IGNORECASE)
_INCH = re.compile(r"\b(\d+(?:-\d+/\d+)?(?:/\d+)?)\s*(?:in|inch|inches)\b", re.IGNORECASE)
_THREAD = re.compile(r"\b(\d+/\d+)\s*-\s*(\d+)\b")
_METRIC = re.compile(r"\b[mM](\d+)\s*[xX×]\s*(\d+(?:-\d+/\d+)?)\b")
_SIZE = re.compile(r"\b(xxl|xl|lg|large|md|medium|sm|small|[sml])\b", re.IGNORECASE)
_SIZE_NORM = {
    "s": "s",
    "sm": "s",
    "small": "s",
    "m": "m",
    "md": "m",
    "medium": "m",
    "l": "l",
    "lg": "l",
    "large": "l",
    "xl": "xl",
    "xxl": "xxl",
}


@lru_cache(maxsize=4)
def load_lexicon(path: str | None = None) -> dict[str, Any]:
    """Carica ``config/mro_lexicon.yaml`` o i default incorporati."""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    candidates.extend(
        [
            Path.cwd() / "config" / "mro_lexicon.yaml",
            REPO_ROOT / "config" / "mro_lexicon.yaml",
        ]
    )
    payload: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                payload = loaded
            break
    abbreviations = dict(DEFAULT_ABBREVIATIONS)
    raw_abbr = payload.get("abbreviations") or {}
    if isinstance(raw_abbr, dict):
        abbreviations.update({str(k).upper(): str(v).lower() for k, v in raw_abbr.items()})
    colors = dict(DEFAULT_COLORS)
    raw_colors = payload.get("colors") or {}
    if isinstance(raw_colors, dict):
        colors.update({str(k).lower(): str(v).lower() for k, v in raw_colors.items()})
    return {"abbreviations": abbreviations, "colors": colors}


def expand_abbreviations(text: str, lexicon: dict[str, Any] | None = None) -> str:
    """Espande le abbreviazioni MRO/JanSan nel testo già normalizzato."""
    data = lexicon or load_lexicon()
    abbreviations: dict[str, str] = data.get("abbreviations") or {}
    tokens = text.split()
    expanded: list[str] = []
    for token in tokens:
        key = re.sub(r"[^A-Za-z0-9]", "", token).upper()
        replacement = abbreviations.get(key)
        if replacement:
            expanded.extend(replacement.split())
        else:
            expanded.append(token)
    return " ".join(expanded)


def extract_attributes(text: str, lexicon: dict[str, Any] | None = None) -> dict[str, str]:
    """Estrae misura, colore, taglia e filetto da una descrizione."""
    data = lexicon or load_lexicon()
    colors: dict[str, str] = data.get("colors") or DEFAULT_COLORS
    attrs: dict[str, str] = {}
    dim = _DIM.search(text)
    if dim:
        attrs["dim"] = f"{dim.group(1)}x{dim.group(2)}"
    mil = _MIL.search(text)
    if mil:
        attrs["mil"] = mil.group(1)
    inch = _INCH.search(text)
    if inch:
        attrs["inch"] = inch.group(1).lower()
    thread = _THREAD.search(text)
    if thread:
        attrs["thread"] = f"{thread.group(1)}-{thread.group(2)}"
    metric = _METRIC.search(text)
    if metric:
        attrs["metric"] = f"m{metric.group(1)}x{metric.group(2)}"
    size = _SIZE.search(text)
    if size:
        attrs["size"] = _SIZE_NORM.get(size.group(1).lower(), size.group(1).lower())
    for token in re.findall(r"[A-Za-z]+", text.lower()):
        color = colors.get(token)
        if color:
            attrs["color"] = color
            break
    return attrs


def attribute_score(query: dict[str, str], catalog: dict[str, str]) -> tuple[float, bool]:
    """Quota di attributi coincidenti e flag di attributo discordante.

    Un attributo presente in entrambi con valore diverso è discordante
    (penalità §6.3: −0,30 e cap 0,80 sullo score totale).
    """
    if not query:
        return 1.0, False
    matched = 0
    compared = 0
    discordant = False
    for key, value in query.items():
        other = catalog.get(key)
        if other is None:
            continue
        compared += 1
        if other == value:
            matched += 1
        else:
            discordant = True
    if compared == 0:
        return 0.5, False
    return matched / compared, discordant
