"""Motore dichiarativo delle regole di validazione VentureOrder (§7)."""

from __future__ import annotations

from ventureorder.rules import cus as cus
from ventureorder.rules import dup as dup
from ventureorder.rules import exp as exp
from ventureorder.rules import ext as ext
from ventureorder.rules import hdr as hdr
from ventureorder.rules import itm as itm
from ventureorder.rules import prc as prc
from ventureorder.rules import qty as qty
from ventureorder.rules import sec as sec
from ventureorder.rules import tot as tot
from ventureorder.rules import uom as uom
from ventureorder.rules.engine import (
    NON_DISABLEABLE_RULES,
    REJECT_RULES,
    RulesConfigError,
    ValidationEngine,
    validate_rules_config,
)
from ventureorder.rules.models import (
    DecisionRoute,
    Issue,
    RuleContext,
    SecurityHints,
    Severity,
    ValidationResult,
)
from ventureorder.rules.reference import (
    CustomerRecord,
    HistoricalOrder,
    MockReferenceDataProvider,
    ProductRecord,
    SyntheticReferenceDataProvider,
    XrefRecord,
)
from ventureorder.rules.registry import get_all_rules, get_rule, get_rules_by_area, rule

# L'import dei moduli di area registra le regole tramite @rule.
RULE_MODULES = (hdr, cus, itm, uom, qty, prc, tot, dup, ext, sec, exp)

__all__ = [
    "CustomerRecord",
    "DecisionRoute",
    "HistoricalOrder",
    "Issue",
    "MockReferenceDataProvider",
    "NON_DISABLEABLE_RULES",
    "ProductRecord",
    "REJECT_RULES",
    "RuleContext",
    "RulesConfigError",
    "SecurityHints",
    "Severity",
    "SyntheticReferenceDataProvider",
    "ValidationEngine",
    "ValidationResult",
    "XrefRecord",
    "RULE_MODULES",
    "get_all_rules",
    "get_rule",
    "get_rules_by_area",
    "rule",
    "validate_rules_config",
]
