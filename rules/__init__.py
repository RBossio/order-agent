"""Motore di regole di validazione per VentureOrder.

Implementa le circa 45 regole definite nel §7 dell'architettura v0.2,
organizzate per area: HDR, CUS, ITM, UOM, QTY, PRC, TOT, DUP, EXT, SEC, EXP.
"""

from rules import cus as cus
from rules import dup as dup
from rules import exp as exp
from rules import ext as ext
from rules import hdr as hdr
from rules import itm as itm
from rules import prc as prc
from rules import qty as qty
from rules import sec as sec
from rules import tot as tot
from rules import uom as uom
from rules.engine import ValidationEngine
from rules.models import DecisionRoute, Issue, RuleContext, Severity, ValidationResult
from rules.registry import get_all_rules, get_rule, get_rules_by_area, rule

__all__ = [
    "DecisionRoute",
    "Issue",
    "RuleContext",
    "Severity",
    "ValidationEngine",
    "ValidationResult",
    "cus",
    "dup",
    "exp",
    "ext",
    "get_all_rules",
    "get_rule",
    "get_rules_by_area",
    "hdr",
    "itm",
    "prc",
    "qty",
    "rule",
    "sec",
    "tot",
    "uom",
]
