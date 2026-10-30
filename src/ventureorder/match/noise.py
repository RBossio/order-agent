"""Varianti rumorose deterministiche per l'evaluation (seed fisso)."""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

NOISY_EVAL_SEED = 42
NOISY_CALIBRATION_SEED = 7
NOISY_CALIBRATION_SEEDS: tuple[int, ...] = (7, 13, 99)

GENERIC_EMAIL_DOMAINS: tuple[str, ...] = (
    "gmail.example",
    "outlook.example",
    "hotmail.example",
    "yahoo.example",
)

CUSTOMER_VARIANT_KINDS: tuple[str, ...] = ("no_tax_id", "generic_email", "name_noise")
ITEM_VARIANT_KINDS: tuple[str, ...] = (
    "unknown_codes",
    "spaced_codes",
    "paraphrase",
    "alt_uom",
)
ALL_VARIANT_KINDS: tuple[str, ...] = CUSTOMER_VARIANT_KINDS + ITEM_VARIANT_KINDS

_NAME_ABBREV = (
    (re.compile(r"\bCompany\b", re.I), "Co"),
    (re.compile(r"\bHoldings\b", re.I), "Hldgs"),
    (re.compile(r"\bManufacturing\b", re.I), "Mfg"),
    (re.compile(r"\bGroup\b", re.I), "Grp"),
    (re.compile(r"\bCorporation\b|\bCorp\.?\b", re.I), "Co"),
    (re.compile(r"\bIncorporated\b|\bInc\.?\b", re.I), "Inc"),
)

_PARA_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\s*\(SYNTHETIC\)", re.I), ""),
    (re.compile(r"\bhex cap screw\b", re.I), "HCS"),
    (re.compile(r"\bnitrile gloves\b", re.I), "nitrile glove"),
    (re.compile(r"\blatex gloves\b", re.I), "latex glove"),
    (re.compile(r"\bpowder[- ]?free\b|\bPF\b", re.I), "PF"),
    (re.compile(r"\b(\d+)\s*in\b", re.I), r"\1 inch"),
    (re.compile(r"\bcan liner\b", re.I), "trash liner"),
    (re.compile(r"\bsafety glasses\b", re.I), "protective eyewear"),
    (re.compile(r"\bfloor cleaner\b", re.I), "floor cleaning compound"),
    (re.compile(r"\bcut-?off wheel\b", re.I), "cutoff disc"),
    (re.compile(r"\btoilet tissue\b", re.I), "bath tissue"),
    (re.compile(r"\bpaper towel\b", re.I), "hand towel"),
)

_UOM_ALIAS_FLIP: dict[str, str] = {
    "CS": "CASE",
    "BX": "BOX",
    "EA": "PCS",
    "DZN": "DZ",
    "RO": "ROLL",
    "PK": "PACK",
    "GLL": "GAL",
}


def is_hard_case(vof: dict[str, Any]) -> bool:
    """True se il ground truth è marcato caso difficile."""
    meta_raw = vof.get("_synthetic_metadata")
    meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
    return bool(meta.get("is_hard_case"))


def variant_rng(seed: int, *parts: object) -> random.Random:
    """RNG deterministico derivato da seed e chiavi (ordine-stabile)."""
    material = f"{seed}:" + ":".join(str(p) for p in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def apply_variants(
    extracted: dict[str, Any],
    kinds: list[str],
    rng: random.Random,
) -> dict[str, Any]:
    """Applica le varianti rumorose in-place e restituisce lo stesso dict."""
    for kind in kinds:
        if kind == "no_tax_id":
            _drop_tax_id(extracted)
        elif kind == "generic_email":
            _generic_email(extracted, rng)
        elif kind == "name_noise":
            _name_noise(extracted, rng)
        elif kind == "unknown_codes":
            _unknown_codes(extracted)
        elif kind == "spaced_codes":
            _spaced_codes(extracted)
        elif kind == "paraphrase":
            _paraphrase_lines(extracted, rng)
        elif kind == "alt_uom":
            _alt_uom(extracted)
        elif kind == "drop_address":
            _drop_address(extracted)
    return extracted


def select_kinds_for_order(index: int, hard: bool, rng: random.Random) -> list[str]:
    """Sceglie le varianti: una ruotata, tre impilate sui casi difficili."""
    if hard:
        item_kind = ITEM_VARIANT_KINDS[index % len(ITEM_VARIANT_KINDS)]
        # Sui casi difficili si toglie anche l'indirizzo: restano nome rumoroso
        # e i rumori di riga, altrimenti ADDRESS risolverebbe sempre.
        kinds = list(CUSTOMER_VARIANT_KINDS) + ["drop_address", item_kind]
        rng.shuffle(kinds)
        return kinds
    return [ALL_VARIANT_KINDS[index % len(ALL_VARIANT_KINDS)]]


def _drop_address(extracted: dict[str, Any]) -> None:
    buyer = extracted.get("buyer")
    if isinstance(buyer, dict):
        buyer["address"] = None
    bill_to = extracted.get("bill_to")
    if isinstance(bill_to, dict):
        bill_to["address"] = None


def _drop_tax_id(extracted: dict[str, Any]) -> None:
    buyer = extracted.setdefault("buyer", {})
    if isinstance(buyer, dict):
        buyer["tax_id"] = None


def _generic_email(extracted: dict[str, Any], rng: random.Random) -> None:
    domain = rng.choice(GENERIC_EMAIL_DOMAINS)
    source = extracted.setdefault("source", {})
    if isinstance(source, dict):
        source["from_address"] = f"purchasing@{domain}"
    buyer = extracted.setdefault("buyer", {})
    if isinstance(buyer, dict):
        contact = buyer.setdefault("contact", {})
        if isinstance(contact, dict):
            contact["email"] = f"orders@{domain}"


def _name_noise(extracted: dict[str, Any], rng: random.Random) -> None:
    buyer = extracted.setdefault("buyer", {})
    if not isinstance(buyer, dict):
        return
    name = str(buyer.get("name") or "")
    if not name:
        return
    if rng.random() < 0.5:
        buyer["name"] = _abbreviate_name(name)
    else:
        buyer["name"] = _typo_name(name, rng)


def _abbreviate_name(name: str) -> str:
    out = name
    for pattern, repl in _NAME_ABBREV:
        out = pattern.sub(repl, out)
    return out


def _typo_name(name: str, rng: random.Random) -> str:
    letters = list(name)
    idxs = [
        i
        for i, ch in enumerate(letters)
        if ch.isalpha() and i + 1 < len(letters) and letters[i + 1].isalpha()
    ]
    if not idxs:
        return name + "x"
    i = rng.choice(idxs)
    letters[i], letters[i + 1] = letters[i + 1], letters[i]
    return "".join(letters)


def _unknown_codes(extracted: dict[str, Any]) -> None:
    for line in extracted.get("lines") or []:
        if not isinstance(line, dict):
            continue
        line_no = line.get("line_no") or 0
        line["buyer_item_code"] = f"ZZ-UNK-{int(line_no):04d}"
        line["seller_item_code"] = None
        line["gtin"] = None
        line["manufacturer_part_number"] = None


def _spaced_codes(extracted: dict[str, Any]) -> None:
    for line in extracted.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for field in ("buyer_item_code", "seller_item_code"):
            raw = line.get(field)
            if raw:
                line[field] = _insert_separators(str(raw))


def _insert_separators(code: str) -> str:
    if "-" in code:
        return code.replace("-", " - ")
    if len(code) > 4:
        return f"{code[:2]} {code[2:4]} {code[4:]}"
    return f"{code} "


def _paraphrase_lines(extracted: dict[str, Any], rng: random.Random) -> None:
    for line in extracted.get("lines") or []:
        if not isinstance(line, dict):
            continue
        desc = str(line.get("description") or "")
        if not desc:
            continue
        line["description"] = _paraphrase(desc, rng)
        line["buyer_item_code"] = None
        line["seller_item_code"] = None
        line["gtin"] = None
        line["manufacturer_part_number"] = None
        line["manufacturer_name"] = None


def _paraphrase(desc: str, rng: random.Random) -> str:
    out = desc
    applicable = [(pat, repl) for pat, repl in _PARA_RULES if pat.search(out)]
    if not applicable:
        return re.sub(r"\s+", " ", out + " item").strip()
    rng.shuffle(applicable)
    for pat, repl in applicable[:2]:
        out = pat.sub(repl, out)
    return re.sub(r"\s+", " ", out).strip()


def _alt_uom(extracted: dict[str, Any]) -> None:
    for line in extracted.get("lines") or []:
        if not isinstance(line, dict):
            continue
        current = str(line.get("uom") or line.get("uom_raw") or "").upper()
        pack = line.get("pack") if isinstance(line.get("pack"), dict) else {}
        inner = str(pack.get("inner_uom") or "").upper() if pack else ""
        if inner and inner != current:
            line["uom"] = inner
            line["uom_raw"] = inner
            continue
        flipped = _UOM_ALIAS_FLIP.get(current)
        if flipped:
            line["uom"] = flipped
            line["uom_raw"] = flipped
