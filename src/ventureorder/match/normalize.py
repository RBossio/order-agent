"""Normalizzazione di identificativi per il matching (§6)."""

from __future__ import annotations

import re
from typing import Any

from ventureorder.rules.access import email_domain, gtin_is_valid, normalize_address, normalize_uom

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_ITEM_SEP = re.compile(r"[\s\-\./]+")
_SYNTHETIC = re.compile(r"\(synthetic\)|\(fictitious\)", re.IGNORECASE)
_NON_NAME = re.compile(r"[^a-z0-9\s]")
LEGAL_SUFFIXES = frozenset(
    {"inc", "llc", "ltd", "corp", "co", "spa", "srl", "gmbh", "plc", "sa", "sas", "snc"}
)
NAME_STOPWORDS = frozenset({"the", "and", "of", "di", "e"})

try:
    from rapidfuzz import fuzz as _fuzz

    def token_set_ratio(left: str, right: str) -> float:
        """Similarità 0–100 tipo ``rapidfuzz.fuzz.token_set_ratio``."""
        if not left or not right:
            return 0.0
        return float(_fuzz.token_set_ratio(left, right))

except ImportError:  # pragma: no cover — fallback senza dipendenza
    from difflib import SequenceMatcher

    def token_set_ratio(left: str, right: str) -> float:
        """Approssimazione di token_set_ratio con ``difflib``."""
        if not left or not right:
            return 0.0
        a = set(left.split())
        b = set(right.split())
        if not a or not b:
            return 0.0
        inter = a & b
        rest_a = " ".join(sorted(a - inter))
        rest_b = " ".join(sorted(b - inter))
        core = " ".join(sorted(inter))
        if not rest_a and not rest_b:
            return 100.0
        left_cmp = f"{core} {rest_a}".strip()
        right_cmp = f"{core} {rest_b}".strip()
        return 100.0 * SequenceMatcher(None, left_cmp, right_cmp).ratio()


def normalize_tax_id(value: str | None) -> str:
    """P.IVA / CF / EIN: alfanumerico, senza prefisso paese US/IT."""
    if not value:
        return ""
    compact = _NON_ALNUM.sub("", str(value).upper())
    if compact.startswith("IT") and len(compact) > 2 and not compact[2:].isalpha():
        compact = compact[2:]
    if compact.startswith("US") and compact[2:].isdigit():
        compact = compact[2:]
    return compact


def normalize_item_code(value: str | None) -> str:
    """Codice articolo: maiuscole, senza spazi ``-``.``/`` e zeri iniziali (§6.2)."""
    if not value:
        return ""
    compact = _ITEM_SEP.sub("", str(value).upper())
    return compact.lstrip("0")


def normalize_sku(value: str | None) -> str:
    """SKU interno: maiuscole, senza spazi interni (i trattini restano)."""
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value).strip().upper())


def normalize_gtin(value: str | None) -> str | None:
    """GTIN a 14 cifre se la cifra di controllo è valida, altrimenti ``None``."""
    if not value:
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    if not digits:
        return None
    if not gtin_is_valid(digits):
        return None
    return digits.zfill(14)


def normalize_name(value: str | None) -> str:
    """Nome anagrafica: minuscolo, senza forma giuridica né marcatore SYNTHETIC."""
    if not value:
        return ""
    text = _SYNTHETIC.sub(" ", str(value).lower())
    text = _NON_NAME.sub(" ", text)
    tokens = [
        token
        for token in text.split()
        if token and token not in LEGAL_SUFFIXES and token not in NAME_STOPWORDS
    ]
    return " ".join(tokens)


def normalize_description(value: str | None) -> str:
    """Descrizione riga/prodotto: minuscolo, punteggiatura → spazio."""
    if not value:
        return ""
    text = _SYNTHETIC.sub(" ", str(value).lower())
    text = re.sub(r"[^a-z0-9./x×\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


GENERIC_EMAIL_LABELS: frozenset[str] = frozenset(
    {
        "gmail",
        "googlemail",
        "outlook",
        "hotmail",
        "live",
        "msn",
        "yahoo",
        "ymail",
        "libero",
        "icloud",
        "me",
        "mac",
        "aol",
        "proton",
        "protonmail",
        "gmx",
        "zoho",
    }
)


def is_generic_email_domain(domain: str | None) -> bool:
    """True per webmail (gmail, outlook, yahoo, libero, icloud, …)."""
    if not domain:
        return False
    labels = str(domain).strip().lower().replace("www.", "").split(".")
    return any(label in GENERIC_EMAIL_LABELS for label in labels if label)


def sender_domain(vof: dict[str, Any]) -> str | None:
    """Dominio del mittente, poi email di contatto buyer."""
    source = vof.get("source") if isinstance(vof.get("source"), dict) else {}
    from_address = source.get("from_address") if isinstance(source, dict) else None
    domain = email_domain(from_address if isinstance(from_address, str) else None)
    if domain:
        return domain
    buyer = vof.get("buyer") if isinstance(vof.get("buyer"), dict) else {}
    contact = buyer.get("contact") if isinstance(buyer, dict) else None
    email = contact.get("email") if isinstance(contact, dict) else None
    return email_domain(email if isinstance(email, str) else None)


__all__ = [
    "email_domain",
    "is_generic_email_domain",
    "normalize_address",
    "normalize_description",
    "normalize_gtin",
    "normalize_item_code",
    "normalize_name",
    "normalize_sku",
    "normalize_tax_id",
    "normalize_uom",
    "sender_domain",
    "token_set_ratio",
]
