"""Registro delle regole di validazione.

Fornisce il decoratore @rule per registrare le regole e funzioni
per accedere al registro.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from rules.models import Issue, RuleContext, Severity

RuleFunc = Callable[[dict[str, Any], RuleContext], list[Issue]]
F = TypeVar("F", bound=RuleFunc)

_RULES_REGISTRY: dict[str, tuple[RuleFunc, str, Severity]] = {}


def rule(code: str, default_severity: Severity) -> Callable[[F], F]:
    """Decoratore per registrare una regola di validazione.
    
    Args:
        code: Codice della regola nel formato AAA-00 (es. HDR-01)
        default_severity: Severità predefinita della regola
    
    Example:
        @rule("HDR-01", Severity.BLOCK)
        def rule_hdr_01(vof: dict, ctx: RuleContext) -> list[Issue]:
            ...
    """
    def decorator(func: F) -> F:
        if code in _RULES_REGISTRY:
            raise ValueError(f"Regola {code} già registrata")
        _RULES_REGISTRY[code] = (func, code, default_severity)
        func.rule_code = code  # type: ignore
        func.default_severity = default_severity  # type: ignore
        return func
    return decorator


def get_rule(code: str) -> tuple[RuleFunc, str, Severity] | None:
    """Recupera una regola dal registro per codice."""
    return _RULES_REGISTRY.get(code)


def get_all_rules() -> dict[str, tuple[RuleFunc, str, Severity]]:
    """Restituisce tutte le regole registrate."""
    return _RULES_REGISTRY.copy()


def get_rules_by_area(area: str) -> dict[str, tuple[RuleFunc, str, Severity]]:
    """Restituisce le regole di un'area specifica (es. HDR, CUS, ITM).
    
    Args:
        area: Prefisso dell'area (es. "HDR", "CUS", "ITM")
    """
    return {
        code: rule_tuple
        for code, rule_tuple in _RULES_REGISTRY.items()
        if code.startswith(f"{area}-")
    }


def clear_registry() -> None:
    """Svuota il registro (solo per test)."""
    _RULES_REGISTRY.clear()
