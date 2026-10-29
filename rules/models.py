"""Core data models for the validation rules engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(Enum):
    """Severity level for validation issues."""

    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class Issue:
    """A validation issue found by a rule."""

    rule_id: str
    severity: Severity
    message: str
    json_pointer: str
    suggestion: str | None = None
    details: dict[str, Any] | None = None


class ReferenceDataProvider(Protocol):
    """Protocol for pluggable reference data sources."""

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Get customer by ID."""
        ...

    def get_customer_by_name(self, name: str) -> list[dict[str, Any]]:
        """Search customers by name (fuzzy)."""
        ...

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Get item/product by ID."""
        ...

    def get_item_by_code(self, code: str) -> list[dict[str, Any]]:
        """Search items by customer code, GTIN, or MPN."""
        ...

    def get_customer_item_xref(
        self, customer_id: str, customer_item_code: str
    ) -> dict[str, Any] | None:
        """Get customer-specific item cross-reference."""
        ...

    def get_existing_orders(
        self, customer_id: str, po_number: str
    ) -> list[dict[str, Any]]:
        """Check for existing orders with same PO number."""
        ...

    def get_similar_orders(
        self, customer_id: str, order_date: str, total: float
    ) -> list[dict[str, Any]]:
        """Find similar orders for duplicate detection."""
        ...

    def get_order_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Find order by content hash (SHA-256 or Message-ID)."""
        ...

    def get_uom_conversion(
        self, from_uom: str, to_uom: str, item_id: str | None = None
    ) -> float | None:
        """Get UoM conversion factor."""
        ...

    def is_valid_uom(self, uom: str) -> bool:
        """Check if UoM is recognized."""
        ...

    def get_item_price(
        self, item_id: str, customer_id: str | None = None
    ) -> float | None:
        """Get expected price for item."""
        ...

    def is_valid_currency(self, currency: str) -> bool:
        """Check if currency code is valid."""
        ...

    def is_dangerous_extension(self, extension: str) -> bool:
        """Check if file extension is dangerous."""
        ...

    def get_peppol_endpoint(self, customer_id: str) -> str | None:
        """Get Peppol endpoint for customer."""
        ...

    def get_peppol_uom_codes(self) -> set[str]:
        """Get valid Peppol UoM codes."""
        ...


@dataclass
class RuleContext:
    """Context for rule execution."""

    order: dict[str, Any]
    confidence_map: dict[str, float] = field(default_factory=dict)
    reference_data: ReferenceDataProvider | None = None
    config: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)


class DecisionRoute(Enum):
    """Final decision route for an order."""

    AUTO_POST = "AUTO_POST"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass
class ValidationResult:
    """Result of validating an order."""

    issues: list[Issue] = field(default_factory=list)
    decision: DecisionRoute = DecisionRoute.AUTO_POST
    score: float = 100.0
    summary: dict[str, int] = field(default_factory=dict)

    def add_issue(self, issue: Issue) -> None:
        """Add an issue and update decision."""
        self.issues.append(issue)
        severity = issue.severity.value
        self.summary[severity] = self.summary.get(severity, 0) + 1
        if issue.severity == Severity.BLOCK:
            self.decision = DecisionRoute.REJECT
        elif issue.severity == Severity.REVIEW and self.decision != DecisionRoute.REJECT:
            self.decision = DecisionRoute.REVIEW
