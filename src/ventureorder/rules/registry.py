"""Registro dichiarativo delle regole: ``@rule(codice, severità)``."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ventureorder.rules.models import Issue, RuleContext, Severity

RuleFunc = Callable[[RuleContext], list[Issue]]
F = TypeVar("F", bound=RuleFunc)

_RULES_REGISTRY: dict[str, tuple[RuleFunc, Severity]] = {}


def rule(code: str, default_severity: Severity) -> Callable[[F], F]:
    """Registra una funzione ``rule(ctx) -> list[Issue]`` con codice e severità."""

    def decorator(func: F) -> F:
        _RULES_REGISTRY[code] = (func, default_severity)
        func.rule_id = code  # type: ignore[attr-defined]
        func.default_severity = default_severity  # type: ignore[attr-defined]
        return func

    return decorator


def get_rule(code: str) -> tuple[RuleFunc, Severity] | None:
    """Restituisce ``(funzione, severità)`` per codice, o ``None``."""
    return _RULES_REGISTRY.get(code)


def get_all_rules() -> dict[str, tuple[RuleFunc, Severity]]:
    """Copia del registro (codice → funzione e severità predefinita)."""
    return _RULES_REGISTRY.copy()


def get_rules_by_area(area: str) -> dict[str, tuple[RuleFunc, Severity]]:
    """Filtra le regole per prefisso di area (es. ``HDR``, ``CUS``)."""
    prefix = area if area.endswith("-") else f"{area}-"
    return {code: value for code, value in _RULES_REGISTRY.items() if code.startswith(prefix)}
