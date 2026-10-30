"""Accessori puri sul VOF e utilità condivise dalle regole."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ventureorder.rules.models import Issue, RuleContext, Severity

# Alias UoM frequenti sui PO MRO rispetto ai codici UN/ECE Rec. 20.
UOM_ALIASES: dict[str, str] = {
    "DZ": "DZN",
    "DOZ": "DZN",
    "DOZEN": "DZN",
    "CA": "CS",
    "CASE": "CS",
    "RL": "RO",
    "ROLL": "RO",
    "GAL": "GLL",
    "GA": "GLL",
    "LT": "LTR",
    "L": "LTR",
    "KG": "KGM",
    "LB": "LBR",
    "PCE": "EA",
    "PC": "EA",
    "PCS": "EA",
    "UN": "EA",
    "C62": "EA",
    "H87": "EA",
    "EACH": "EA",
}

INDIVISIBLE_UOMS = frozenset(
    {"EA", "BX", "CS", "PK", "DZN", "PR", "CT", "BG", "DR", "RO"}
)

# Unità usate da datagen/master/products.json, in aggiunta a Rec. 20 / alias MRO.
DATAGEN_VALID_UOMS = frozenset({"CS", "BX", "RO", "PK", "BG", "RL", "GLL", "DZN"})

DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".pif",
        ".vbs",
        ".js",
        ".jar",
        ".ps1",
        ".sh",
        ".dll",
        ".sys",
        ".xlsm",
        ".xlsb",
    }
)

ALLOWED_DOCUMENT_KINDS = frozenset(
    {"PDF_TEXT", "PDF_SCAN", "XLSX", "XLS", "CSV", "EMAIL_BODY", "IMAGE"}
)


def resolved(party: dict[str, Any] | None) -> dict[str, Any]:
    """Restituisce ``party.resolved`` o un dict vuoto."""
    if not isinstance(party, dict):
        return {}
    value = party.get("resolved")
    return value if isinstance(value, dict) else {}


def line_resolution(line: dict[str, Any] | None) -> dict[str, Any]:
    """Restituisce ``line.resolution`` o un dict vuoto."""
    if not isinstance(line, dict):
        return {}
    value = line.get("resolution")
    return value if isinstance(value, dict) else {}


def parse_date(value: Any) -> date | None:
    """Parsa una data ISO (``YYYY-MM-DD`` o datetime). ``None`` se assente/invalida."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def normalize_uom(raw: str | None) -> str | None:
    """Normalizza un codice UoM (maiuscolo, alias MRO → Rec. 20)."""
    if not raw:
        return None
    token = str(raw).strip().upper()
    if not token:
        return None
    token = re.split(r"[^A-Z0-9]+", token, maxsplit=1)[0]
    if not token:
        return None
    return UOM_ALIASES.get(token, token)


def normalize_terms(text: str | None) -> str:
    """Normalizza termini di pagamento per il confronto (``NET30``)."""
    if not text:
        return ""
    compact = re.sub(r"[^A-Z0-9]", "", str(text).upper())
    compact = compact.replace("DAYS", "").replace("GG", "")
    return compact


def normalize_party_name(name: str | None) -> str:
    """Normalizza un nome di sede/cliente per il confronto."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def normalize_address(addr: dict[str, Any] | None) -> str:
    """Chiave di confronto indirizzo: line1 + city + CAP, minuscolo."""
    if not isinstance(addr, dict):
        return ""
    parts = [
        str(addr.get("line1") or addr.get("street") or ""),
        str(addr.get("city") or ""),
        str(addr.get("postal_code") or ""),
    ]
    return " ".join(p.lower().strip() for p in parts if p).strip()


def email_domain(address: str | None) -> str | None:
    """Estrae il dominio da un indirizzo email."""
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[-1].strip().lower() or None


def gtin_is_valid(gtin: str | None) -> bool:
    """Verifica la cifra di controllo GS1 (GTIN-8/12/13/14)."""
    if not gtin:
        return False
    digits = "".join(c for c in str(gtin) if c.isdigit())
    if len(digits) not in (8, 12, 13, 14):
        return False
    padded = digits.zfill(14)
    body, check = padded[:-1], padded[-1]
    total = 0
    for i, digit in enumerate(body):
        # Pesi GS1: dal fondo del GTIN-14 (posizioni dispari da destra × 3).
        weight = 3 if (len(body) - i) % 2 == 1 else 1
        total += int(digit) * weight
    expected = (10 - (total % 10)) % 10
    return expected == int(check)


def as_float(value: Any) -> float | None:
    """Converte in float; ``None`` se mancante o non numerico."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def issue(
    rule_id: str,
    severity: Severity,
    message: str,
    pointer: str,
    suggestion: str | None = None,
    **details: Any,
) -> Issue:
    """Factory compatta per una ``Issue``."""
    return Issue(
        rule_id=rule_id,
        severity=severity,
        message=message,
        json_pointer=pointer,
        suggestion=suggestion,
        details=details or None,
    )


def threshold(ctx: RuleContext, key: str, default: Any) -> Any:
    """Legge una soglia dal contesto, con default."""
    return ctx.thresholds.get(key, default)


def line_pointer(index: int, field: str | None = None) -> str:
    """JSON Pointer di una riga (indice 0-based) o di un suo campo."""
    base = f"/lines/{index}"
    return f"{base}/{field}" if field else base
