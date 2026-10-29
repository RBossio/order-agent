"""Rule registry for declarative rule definitions."""

from collections.abc import Callable
from typing import TypeVar

from rules.models import Issue, RuleContext, Severity

F = TypeVar("F", bound=Callable[[RuleContext], list[Issue]])

_RULES_REGISTRY: dict[str, tuple[Callable[[RuleContext], list[Issue]], str, Severity]] = {}


def rule(code: str, default_severity: Severity) -> Callable[[F], F]:
    """Decorator to register a validation rule."""

    def decorator(func: F) -> F:
        _RULES_REGISTRY[code] = (func, code, default_severity)
        return func

    return decorator


def get_rule(code: str) -> tuple[Callable[[RuleContext], list[Issue]], str, Severity] | None:
    """Get a rule by code."""
    return _RULES_REGISTRY.get(code)


def get_all_rules() -> (
    dict[str, tuple[Callable[[RuleContext], list[Issue]], str, Severity]]
):
    """Get all registered rules."""
    return _RULES_REGISTRY.copy()


def get_rules_by_area(area: str) -> (
    dict[str, tuple[Callable[[RuleContext], list[Issue]], str, Severity]]
):
    """Get rules by area prefix (e.g., 'HDR', 'CUS')."""
    return {k: v for k, v in _RULES_REGISTRY.items() if k.startswith(area)}
