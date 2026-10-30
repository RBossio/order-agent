"""Confidenza tarata: fonte, accordo tra metodi e controlli — non l'auto-score LLM."""

from __future__ import annotations

from .models import FieldConfidence

# Sotto 0,80 un campo sbagliato non è errore silenzioso a livello di campo (eval).
# Sotto 0,90 EXT-01 manda l'ordine in REVIEW.
# DETERMINISTIC 0,98 e AGREED 0,99 superano auto_post_min_score 0,97 (§7.1,
# invariata): un ordine pulito, deterministico e con i controlli ok può AUTO_POST.
DETERMINISTIC = 0.98
LLM_ONLY = 0.70
AGREED = 0.99
DISAGREE = 0.45
CHECK_FAIL = 0.39
MISSING = 0.0
REVIEW_THRESHOLD = 0.90
SILENT_THRESHOLD = 0.80


def calibrate(
    source: str,
    *,
    agreed: bool | None = None,
    checks_ok: bool = True,
    present: bool = True,
) -> float:
    """Calcola la confidenza di un campo.

    Args:
        source: ``preprocessor``, ``llm`` o ``agreed``.
        agreed: True se i due metodi coincidono, False se discordano, None se uno solo.
        checks_ok: False se un controllo incrociato è fallito su questo campo.
        present: False se il valore manca.
    """
    if not present:
        return MISSING
    if not checks_ok:
        return CHECK_FAIL
    if agreed is True:
        return AGREED
    if agreed is False:
        return DISAGREE
    if source == "llm":
        return LLM_ONLY
    if source == "agreed":
        return AGREED
    return DETERMINISTIC


def set_confidence(fields: list[FieldConfidence], path: str, value: float) -> None:
    """Imposta (o crea) la confidenza di ``path``, senza alzarla."""
    for field in fields:
        if field.path == path:
            field.confidence = min(field.confidence, value)
            return
    fields.append(FieldConfidence(path=path, confidence=value, source="check"))


def drop_below_review(fields: list[FieldConfidence], path: str) -> None:
    """Porta la confidenza sotto la soglia EXT-01 / silenziosa."""
    set_confidence(fields, path, CHECK_FAIL)
