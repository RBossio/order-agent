"""Riconoscimento clienti e articoli (§6 architettura v0.2).

Input ammessi e campi vietati (ID attesi): ``ventureorder.match.fields``.
"""

from __future__ import annotations

from ventureorder.match.customer import CustomerMatcher
from ventureorder.match.eval import (
    MatchEvalReport,
    evaluate_noisy_dataset,
    evaluate_synthetic_dataset,
)
from ventureorder.match.fields import (
    CUSTOMER_INPUT_FIELDS,
    FORBIDDEN_ID_FIELDS,
    ITEM_INPUT_FIELDS,
    sanitize_extracted_order,
)
from ventureorder.match.items import ItemMatcher
from ventureorder.match.models import CustomerMatch, ItemMatch
from ventureorder.match.pipeline import apply_matches

__all__ = [
    "CUSTOMER_INPUT_FIELDS",
    "FORBIDDEN_ID_FIELDS",
    "ITEM_INPUT_FIELDS",
    "CustomerMatch",
    "CustomerMatcher",
    "ItemMatch",
    "ItemMatcher",
    "MatchEvalReport",
    "apply_matches",
    "evaluate_noisy_dataset",
    "evaluate_synthetic_dataset",
    "sanitize_extracted_order",
]
