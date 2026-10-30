"""Riconoscimento clienti e articoli (§6 architettura v0.2)."""

from __future__ import annotations

from ventureorder.match.customer import CustomerMatcher
from ventureorder.match.eval import MatchEvalReport, evaluate_synthetic_dataset
from ventureorder.match.items import ItemMatcher
from ventureorder.match.models import CustomerMatch, ItemMatch
from ventureorder.match.pipeline import apply_matches

__all__ = [
    "CustomerMatch",
    "CustomerMatcher",
    "ItemMatch",
    "ItemMatcher",
    "MatchEvalReport",
    "apply_matches",
    "evaluate_synthetic_dataset",
]
