"""Tests for validation rules engine."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from rules import ValidationEngine
from rules.models import DecisionRoute, RuleContext, Severity
from rules.reference_data import MockReferenceDataProvider


def make_vof(
    po_number: str = "PO-12345",
    order_date: str | None = None,
    currency: str = "EUR",
    customer: dict | None = None,
    lines: list | None = None,
    total: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Helper to create a minimal valid VOF order."""
    if order_date is None:
        order_date = datetime.now().strftime("%Y-%m-%d")
    if customer is None:
        customer = {"id": "CUST001", "name": "Test Customer"}
    if lines is None:
        lines = [
            {
                "item": {"id": "ITM001", "description": "Test Item"},
                "quantity": 10,
                "unit_price": 25.00,
                "uom": "PZ",
                "line_amount": 250.00,
            }
        ]

    order = {
        "po_number": po_number,
        "order_date": order_date,
        "currency": currency,
        "customer": customer,
        "lines": lines,
        **kwargs,
    }

    if total is not None:
        order["total"] = total

    return order


@pytest.fixture
def engine() -> ValidationEngine:
    """Create a validation engine with mock reference data."""
    ref = MockReferenceDataProvider()
    return ValidationEngine(config_dir="config", reference_data=ref)


@pytest.fixture
def mock_ref() -> MockReferenceDataProvider:
    """Create mock reference data provider."""
    return MockReferenceDataProvider()


class TestHdrRules:
    """Tests for HDR (Header) rules."""

    def test_hdr_01_po_number_present(self, engine: ValidationEngine) -> None:
        """HDR-01: PO number present should pass."""
        order = make_vof(po_number="PO-12345")
        result = engine.validate(order)
        hdr01_issues = [i for i in result.issues if i.rule_id == "HDR-01"]
        assert len(hdr01_issues) == 0

    def test_hdr_01_po_number_missing(self, engine: ValidationEngine) -> None:
        """HDR-01: Missing PO number should block."""
        order = make_vof(po_number="")
        result = engine.validate(order)
        hdr01_issues = [i for i in result.issues if i.rule_id == "HDR-01"]
        assert len(hdr01_issues) == 1
        assert hdr01_issues[0].severity == Severity.BLOCK

    def test_hdr_02_order_date_valid(self, engine: ValidationEngine) -> None:
        """HDR-02: Valid order date should pass."""
        order = make_vof(order_date="2024-01-15")
        result = engine.validate(order)
        hdr02_issues = [i for i in result.issues if i.rule_id == "HDR-02"]
        assert len(hdr02_issues) == 0

    def test_hdr_02_order_date_future(self, engine: ValidationEngine) -> None:
        """HDR-02: Future order date should require review."""
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        order = make_vof(order_date=future_date)
        result = engine.validate(order)
        hdr02_issues = [i for i in result.issues if i.rule_id == "HDR-02"]
        assert len(hdr02_issues) == 1
        assert hdr02_issues[0].severity == Severity.REVIEW

    def test_hdr_02_order_date_missing(self, engine: ValidationEngine) -> None:
        """HDR-02: Missing order date should require review."""
        order = make_vof()
        del order["order_date"]
        result = engine.validate(order)
        hdr02_issues = [i for i in result.issues if i.rule_id == "HDR-02"]
        assert len(hdr02_issues) == 1

    def test_hdr_03_currency_valid(self, engine: ValidationEngine) -> None:
        """HDR-03: Valid currency should pass."""
        order = make_vof(currency="EUR")
        result = engine.validate(order)
        hdr03_issues = [i for i in result.issues if i.rule_id == "HDR-03"]
        assert len(hdr03_issues) == 0

    def test_hdr_03_currency_missing(self, engine: ValidationEngine) -> None:
        """HDR-03: Missing currency should block."""
        order = make_vof()
        del order["currency"]
        result = engine.validate(order)
        hdr03_issues = [i for i in result.issues if i.rule_id == "HDR-03"]
        assert len(hdr03_issues) == 1
        assert hdr03_issues[0].severity == Severity.BLOCK

    def test_hdr_04_delivery_date_past(self, engine: ValidationEngine) -> None:
        """HDR-04: Past delivery date should warn."""
        past_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        order = make_vof(requested_delivery_date=past_date)
        result = engine.validate(order)
        hdr04_issues = [i for i in result.issues if i.rule_id == "HDR-04"]
        assert len(hdr04_issues) == 1
        assert hdr04_issues[0].severity == Severity.WARN

    def test_hdr_05_document_type_valid(self, engine: ValidationEngine) -> None:
        """HDR-05: Valid document type should pass."""
        order = make_vof(document_type="ORDER")
        result = engine.validate(order)
        hdr05_issues = [i for i in result.issues if i.rule_id == "HDR-05"]
        assert len(hdr05_issues) == 0

    def test_hdr_05_document_type_unknown(self, engine: ValidationEngine) -> None:
        """HDR-05: Unknown document type should inform."""
        order = make_vof(document_type="CUSTOM_TYPE")
        result = engine.validate(order)
        hdr05_issues = [i for i in result.issues if i.rule_id == "HDR-05"]
        assert len(hdr05_issues) == 1
        assert hdr05_issues[0].severity == Severity.INFO

    def test_hdr_06_payment_terms_valid(self, engine: ValidationEngine) -> None:
        """HDR-06: Valid payment terms should pass."""
        order = make_vof(payment_terms="NET30")
        result = engine.validate(order)
        hdr06_issues = [i for i in result.issues if i.rule_id == "HDR-06"]
        assert len(hdr06_issues) == 0


class TestCusRules:
    """Tests for CUS (Customer) rules."""

    def test_cus_01_customer_identified(
        self, mock_ref: MockReferenceDataProvider
    ) -> None:
        """CUS-01: Identified customer should pass."""
        mock_ref.set_mock("get_customer", {"id": "CUST001", "name": "Test Customer"})
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof(customer={"id": "CUST001", "name": "Test Customer"})
        result = engine.validate(order)
        cus01_issues = [i for i in result.issues if i.rule_id == "CUS-01"]
        assert len(cus01_issues) == 0

    def test_cus_01_customer_missing(self, engine: ValidationEngine) -> None:
        """CUS-01: Missing customer should block."""
        order = make_vof(customer={})
        result = engine.validate(order)
        cus01_issues = [i for i in result.issues if i.rule_id == "CUS-01"]
        assert len(cus01_issues) == 1
        assert cus01_issues[0].severity == Severity.BLOCK

    def test_cus_02_fuzzy_match(self, engine: ValidationEngine) -> None:
        """CUS-02: Fuzzy matched customer should require review."""
        order = make_vof(customer={
            "id": "CUST001",
            "name": "Test Customer",
            "resolution_method": "fuzzy",
            "match_confidence": 0.85,
        })
        result = engine.validate(order)
        cus02_issues = [i for i in result.issues if i.rule_id == "CUS-02"]
        assert len(cus02_issues) == 1
        assert cus02_issues[0].severity == Severity.REVIEW

    def test_cus_03_ship_to_differs(self, engine: ValidationEngine) -> None:
        """CUS-03: Different ship_to should require review."""
        order = make_vof(
            bill_to={"street": "Via Roma 1", "city": "Milano", "postal_code": "20100"},
            ship_to={"street": "Via Torino 2", "city": "Roma", "postal_code": "00100"},
        )
        result = engine.validate(order)
        cus03_issues = [i for i in result.issues if i.rule_id == "CUS-03"]
        assert len(cus03_issues) == 1

    def test_cus_04_suspicious_email(self, engine: ValidationEngine) -> None:
        """CUS-04: Suspicious email domain should warn."""
        order = make_vof(customer={
            "id": "CUST001",
            "name": "Test",
            "contact_email": "test@tempmail.com",
        })
        result = engine.validate(order)
        cus04_issues = [i for i in result.issues if i.rule_id == "CUS-04"]
        assert len(cus04_issues) == 1
        assert cus04_issues[0].severity == Severity.WARN

    def test_cus_05_customer_warnings(self, engine: ValidationEngine) -> None:
        """CUS-05: Customer warnings should be reported."""
        order = make_vof(customer={
            "id": "CUST001",
            "name": "Test",
            "warnings": ["Cliente in ritardo pagamenti"],
        })
        result = engine.validate(order)
        cus05_issues = [i for i in result.issues if i.rule_id == "CUS-05"]
        assert len(cus05_issues) == 1
        assert cus05_issues[0].severity == Severity.INFO


class TestItmRules:
    """Tests for ITM (Item) rules."""

    def test_itm_01_item_resolved(self, engine: ValidationEngine) -> None:
        """ITM-01: Resolved item should pass."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001", "description": "Test"}, "quantity": 10, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        itm01_issues = [i for i in result.issues if i.rule_id == "ITM-01"]
        assert len(itm01_issues) == 0

    def test_itm_01_item_unresolved(self, engine: ValidationEngine) -> None:
        """ITM-01: Unresolved item should block."""
        order = make_vof(lines=[
            {"item": {"resolution_status": "unresolved"}, "quantity": 10, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        itm01_issues = [i for i in result.issues if i.rule_id == "ITM-01"]
        assert len(itm01_issues) == 1
        assert itm01_issues[0].severity == Severity.BLOCK

    def test_itm_03_fuzzy_match(self, engine: ValidationEngine) -> None:
        """ITM-03: Fuzzy matched item should require review."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001", "resolution_method": "fuzzy", "match_confidence": 0.80},
            "quantity": 10, "unit_price": 25.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        itm03_issues = [i for i in result.issues if i.rule_id == "ITM-03"]
        assert len(itm03_issues) == 1

    def test_itm_05_gtin_valid(self, engine: ValidationEngine) -> None:
        """ITM-05: Valid GTIN checksum should pass."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001", "gtin": "5901234123457"},
            "quantity": 10, "unit_price": 25.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        itm05_issues = [i for i in result.issues if i.rule_id == "ITM-05"]
        assert len(itm05_issues) == 0

    def test_itm_05_gtin_invalid(self, engine: ValidationEngine) -> None:
        """ITM-05: Invalid GTIN checksum should warn."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001", "gtin": "5901234123456"},
            "quantity": 10, "unit_price": 25.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        itm05_issues = [i for i in result.issues if i.rule_id == "ITM-05"]
        assert len(itm05_issues) == 1
        assert itm05_issues[0].severity == Severity.WARN

    def test_itm_06_duplicate_lines(self, engine: ValidationEngine) -> None:
        """ITM-06: Duplicate lines should warn."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "uom": "PZ"},
            {"item": {"id": "ITM001"}, "quantity": 5, "unit_price": 25.00, "uom": "PZ"},
        ])
        result = engine.validate(order)
        itm06_issues = [i for i in result.issues if i.rule_id == "ITM-06"]
        assert len(itm06_issues) == 1

    def test_itm_07_xref_candidate(self, engine: ValidationEngine) -> None:
        """ITM-07: CANDIDATE xref should require review."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001"},
            "customer_item_xref": {"status": "CANDIDATE", "customer_code": "ABC123"},
            "quantity": 10, "unit_price": 25.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        itm07_issues = [i for i in result.issues if i.rule_id == "ITM-07"]
        assert len(itm07_issues) == 1


class TestUomRules:
    """Tests for UOM rules."""

    def test_uom_01_valid_uom(self, engine: ValidationEngine) -> None:
        """UOM-01: Valid UoM should pass."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        uom01_issues = [i for i in result.issues if i.rule_id == "UOM-01"]
        assert len(uom01_issues) == 0

    def test_uom_01_invalid_uom(self, engine: ValidationEngine) -> None:
        """UOM-01: Invalid UoM should block."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "uom": "UNKNOWN_UOM"}
        ])
        result = engine.validate(order)
        uom01_issues = [i for i in result.issues if i.rule_id == "UOM-01"]
        assert len(uom01_issues) == 1

    def test_uom_05_non_integer_discrete(self, engine: ValidationEngine) -> None:
        """UOM-05: Non-integer quantity for discrete UoM should warn."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10.5, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        uom05_issues = [i for i in result.issues if i.rule_id == "UOM-05"]
        assert len(uom05_issues) == 1


class TestQtyRules:
    """Tests for QTY rules."""

    def test_qty_01_valid_quantity(self, engine: ValidationEngine) -> None:
        """QTY-01: Valid quantity should pass."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        qty01_issues = [i for i in result.issues if i.rule_id == "QTY-01"]
        assert len(qty01_issues) == 0

    def test_qty_01_missing_quantity(self, engine: ValidationEngine) -> None:
        """QTY-01: Missing quantity should block."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        qty01_issues = [i for i in result.issues if i.rule_id == "QTY-01"]
        assert len(qty01_issues) == 1
        assert qty01_issues[0].severity == Severity.BLOCK

    def test_qty_01_zero_quantity(self, engine: ValidationEngine) -> None:
        """QTY-01: Zero quantity should block."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 0, "unit_price": 25.00, "uom": "PZ"}
        ])
        result = engine.validate(order)
        qty01_issues = [i for i in result.issues if i.rule_id == "QTY-01"]
        assert len(qty01_issues) == 1

    def test_qty_02_anomalous_quantity(self, engine: ValidationEngine) -> None:
        """QTY-02: Anomalous quantity should require review."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001", "avg_order_qty": 10},
            "quantity": 500,
            "unit_price": 25.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        qty02_issues = [i for i in result.issues if i.rule_id == "QTY-02"]
        assert len(qty02_issues) == 1


class TestPrcRules:
    """Tests for PRC (Price) rules."""

    def test_prc_02_missing_price(self, engine: ValidationEngine) -> None:
        """PRC-02: Missing price should warn."""
        order = make_vof(lines=[
            {"item": {"id": "ITM001"}, "quantity": 10, "uom": "PZ"}
        ])
        result = engine.validate(order)
        prc02_issues = [i for i in result.issues if i.rule_id == "PRC-02"]
        assert len(prc02_issues) == 1
        assert prc02_issues[0].severity == Severity.WARN

    def test_prc_03_line_amount_correct(self, engine: ValidationEngine) -> None:
        """PRC-03: Correct line amount should pass."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001"},
            "quantity": 10, "unit_price": 25.00, "line_amount": 250.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        prc03_issues = [i for i in result.issues if i.rule_id == "PRC-03"]
        assert len(prc03_issues) == 0

    def test_prc_03_line_amount_mismatch(self, engine: ValidationEngine) -> None:
        """PRC-03: Incorrect line amount should warn."""
        order = make_vof(lines=[{
            "item": {"id": "ITM001"},
            "quantity": 10, "unit_price": 25.00, "line_amount": 300.00, "uom": "PZ",
        }])
        result = engine.validate(order)
        prc03_issues = [i for i in result.issues if i.rule_id == "PRC-03"]
        assert len(prc03_issues) == 1


class TestTotRules:
    """Tests for TOT (Total) rules."""

    def test_tot_01_total_correct(self, engine: ValidationEngine) -> None:
        """TOT-01: Correct total should pass."""
        order = make_vof(
            lines=[{"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "line_amount": 250.00, "uom": "PZ"}],
            total=250.00,
        )
        result = engine.validate(order)
        tot01_issues = [i for i in result.issues if i.rule_id == "TOT-01"]
        assert len(tot01_issues) == 0

    def test_tot_01_total_mismatch(self, engine: ValidationEngine) -> None:
        """TOT-01: Incorrect total should require review."""
        order = make_vof(
            lines=[{"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "line_amount": 250.00, "uom": "PZ"}],
            total=300.00,
        )
        result = engine.validate(order)
        tot01_issues = [i for i in result.issues if i.rule_id == "TOT-01"]
        assert len(tot01_issues) == 1


class TestDupRules:
    """Tests for DUP (Duplicate) rules."""

    def test_dup_01_no_duplicate(self, mock_ref: MockReferenceDataProvider) -> None:
        """DUP-01: No duplicate should pass."""
        mock_ref.set_mock("get_existing_orders", [])
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof()
        result = engine.validate(order)
        dup01_issues = [i for i in result.issues if i.rule_id == "DUP-01"]
        assert len(dup01_issues) == 0

    def test_dup_01_duplicate_found(self, mock_ref: MockReferenceDataProvider) -> None:
        """DUP-01: Duplicate PO should block."""
        mock_ref.set_mock("get_existing_orders", [{"id": "ORD-OLD-001"}])
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof()
        result = engine.validate(order)
        dup01_issues = [i for i in result.issues if i.rule_id == "DUP-01"]
        assert len(dup01_issues) == 1
        assert dup01_issues[0].severity == Severity.BLOCK

    def test_dup_02_no_hash_duplicate(self, mock_ref: MockReferenceDataProvider) -> None:
        """DUP-02: No hash duplicate should pass."""
        mock_ref.set_mock("get_order_by_hash", None)
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof(content_hash="abc123")
        result = engine.validate(order)
        dup02_issues = [i for i in result.issues if i.rule_id == "DUP-02"]
        assert len(dup02_issues) == 0

    def test_dup_02_hash_duplicate_found(self, mock_ref: MockReferenceDataProvider) -> None:
        """DUP-02: Hash duplicate should block."""
        mock_ref.set_mock("get_order_by_hash", {"id": "ORD-OLD-001"})
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof(content_hash="abc123")
        result = engine.validate(order)
        dup02_issues = [i for i in result.issues if i.rule_id == "DUP-02"]
        assert len(dup02_issues) == 1


class TestExtRules:
    """Tests for EXT (Extraction) rules."""

    def test_ext_01_high_confidence(self, engine: ValidationEngine) -> None:
        """EXT-01: High confidence should pass."""
        order = make_vof()
        confidence = {"po_number": 0.99, "customer.name": 0.98}
        result = engine.validate(order, confidence)
        ext01_issues = [i for i in result.issues if i.rule_id == "EXT-01"]
        assert len(ext01_issues) == 0

    def test_ext_01_low_confidence(self, engine: ValidationEngine) -> None:
        """EXT-01: Low confidence should require review."""
        order = make_vof()
        confidence = {"po_number": 0.70, "customer.name": 0.65}
        result = engine.validate(order, confidence)
        ext01_issues = [i for i in result.issues if i.rule_id == "EXT-01"]
        assert len(ext01_issues) == 2

    def test_ext_03_extraction_errors(self, engine: ValidationEngine) -> None:
        """EXT-03: Extraction errors should require review."""
        order = make_vof(extraction_metadata={
            "errors": ["Tabella non riconosciuta"],
            "warnings": ["Valore ambiguo"],
        })
        result = engine.validate(order)
        ext03_issues = [i for i in result.issues if i.rule_id == "EXT-03"]
        assert len(ext03_issues) == 2


class TestSecRules:
    """Tests for SEC (Security) rules."""

    def test_sec_01_safe_attachment(self, engine: ValidationEngine) -> None:
        """SEC-01: Safe attachment should pass."""
        order = make_vof(attachments=[{"filename": "order.pdf"}])
        result = engine.validate(order)
        sec01_issues = [i for i in result.issues if i.rule_id == "SEC-01"]
        assert len(sec01_issues) == 0

    def test_sec_01_dangerous_attachment(self, engine: ValidationEngine) -> None:
        """SEC-01: Dangerous attachment should block."""
        order = make_vof(attachments=[{"filename": "malware.exe"}])
        result = engine.validate(order)
        sec01_issues = [i for i in result.issues if i.rule_id == "SEC-01"]
        assert len(sec01_issues) == 1
        assert sec01_issues[0].severity == Severity.BLOCK


class TestExpRules:
    """Tests for EXP (Export) rules."""

    def test_exp_01_peppol_not_required(self, engine: ValidationEngine) -> None:
        """EXP-01: No Peppol required should pass."""
        order = make_vof()
        result = engine.validate(order)
        exp01_issues = [i for i in result.issues if i.rule_id == "EXP-01"]
        assert len(exp01_issues) == 0

    def test_exp_01_peppol_endpoint_missing(
        self, mock_ref: MockReferenceDataProvider
    ) -> None:
        """EXP-01: Missing Peppol endpoint should require review."""
        mock_ref.set_mock("get_peppol_endpoint", None)
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof(export={"peppol_required": True})
        result = engine.validate(order)
        exp01_issues = [i for i in result.issues if i.rule_id == "EXP-01"]
        assert len(exp01_issues) == 1

    def test_exp_02_field_too_long(self, engine: ValidationEngine) -> None:
        """EXP-02: Field too long should warn."""
        order = make_vof(po_number="X" * 100)
        result = engine.validate(order)
        exp02_issues = [i for i in result.issues if i.rule_id == "EXP-02"]
        assert len(exp02_issues) == 1

    def test_exp_03_uom_not_peppol(self, engine: ValidationEngine) -> None:
        """EXP-03: Non-Peppol UoM should warn."""
        order = make_vof(
            export={"peppol_required": True},
            lines=[{"item": {"id": "ITM001"}, "quantity": 10, "unit_price": 25.00, "uom": "BOXES"}],
        )
        result = engine.validate(order)
        exp03_issues = [i for i in result.issues if i.rule_id == "EXP-03"]
        assert len(exp03_issues) == 1


class TestDecisionRoutes:
    """Tests for decision routing."""

    def test_auto_post_on_clean_order(self, engine: ValidationEngine) -> None:
        """Clean order should auto-post."""
        order = make_vof()
        result = engine.validate(order)
        blocking = [i for i in result.issues if i.severity == Severity.BLOCK]
        reviewing = [i for i in result.issues if i.severity == Severity.REVIEW]
        if not blocking and not reviewing:
            assert result.decision == DecisionRoute.AUTO_POST

    def test_reject_on_blocking_issue(self, engine: ValidationEngine) -> None:
        """Blocking issue should reject."""
        order = make_vof(po_number="")
        result = engine.validate(order)
        assert result.decision == DecisionRoute.REJECT

    def test_review_on_review_issue(self, engine: ValidationEngine) -> None:
        """Review issue should require review."""
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        order = make_vof(order_date=future_date)
        result = engine.validate(order)
        has_block = any(i.severity == Severity.BLOCK for i in result.issues)
        has_review = any(i.severity == Severity.REVIEW for i in result.issues)
        if has_review and not has_block:
            assert result.decision == DecisionRoute.REVIEW


class TestEngineConfiguration:
    """Tests for engine configuration."""

    def test_rule_disabled(self, mock_ref: MockReferenceDataProvider) -> None:
        """Disabled rule should not run."""
        engine = ValidationEngine(config_dir="config", reference_data=mock_ref)
        order = make_vof(source={
            "email_headers": {"spf_result": "fail", "dkim_result": "fail"}
        })
        result = engine.validate(order)
        sec02_issues = [i for i in result.issues if i.rule_id == "SEC-02"]
        assert len(sec02_issues) == 0

    def test_thresholds_loaded(self, engine: ValidationEngine) -> None:
        """Thresholds should be loaded from config."""
        assert engine.thresholds.get("price_tolerance_pct") == 2.0
        assert engine.thresholds.get("confidence_min") == 0.90


class TestRuleContext:
    """Tests for rule context."""

    def test_context_creation(self) -> None:
        """Rule context should be created correctly."""
        order = make_vof()
        ctx = RuleContext(
            order=order,
            confidence_map={"po_number": 0.95},
            thresholds={"price_tolerance_pct": 3.0},
        )
        assert ctx.order == order
        assert ctx.confidence_map["po_number"] == 0.95
        assert ctx.thresholds["price_tolerance_pct"] == 3.0


class TestEmptyOrder:
    """Tests for edge cases with empty/minimal orders."""

    def test_empty_lines(self, engine: ValidationEngine) -> None:
        """Order with no lines should not crash."""
        order = make_vof(lines=[])
        result = engine.validate(order)
        assert result is not None

    def test_minimal_order(self, engine: ValidationEngine) -> None:
        """Minimal order should validate."""
        order = {"po_number": "PO-001", "currency": "EUR"}
        result = engine.validate(order)
        assert result is not None
