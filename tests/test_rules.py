"""Test del motore di regole: un caso positivo e uno negativo per ogni regola."""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from ventureorder.rules import (
    CustomerRecord,
    DecisionRoute,
    HistoricalOrder,
    MockReferenceDataProvider,
    ProductRecord,
    SecurityHints,
    Severity,
    SyntheticReferenceDataProvider,
    ValidationEngine,
    XrefRecord,
    get_all_rules,
)

REPO = Path(__file__).resolve().parent.parent
AS_OF = date(2026, 11, 3)
CONFIG = REPO / "config"

CATALOG_RULES = [
    "HDR-01",
    "HDR-02",
    "HDR-03",
    "HDR-04",
    "HDR-05",
    "HDR-06",
    "CUS-01",
    "CUS-02",
    "CUS-03",
    "CUS-04",
    "CUS-05",
    "ITM-01",
    "ITM-02",
    "ITM-03",
    "ITM-04",
    "ITM-05",
    "ITM-06",
    "ITM-07",
    "UOM-01",
    "UOM-02",
    "UOM-03",
    "UOM-04",
    "UOM-05",
    "QTY-01",
    "QTY-02",
    "QTY-03",
    "PRC-01",
    "PRC-02",
    "PRC-03",
    "PRC-04",
    "TOT-01",
    "TOT-02",
    "TOT-03",
    "DUP-01",
    "DUP-02",
    "DUP-03",
    "EXT-01",
    "EXT-02",
    "EXT-03",
    "SEC-01",
    "SEC-02",
    "EXP-01",
    "EXP-02",
    "EXP-03",
]

SHIP_ADDRESS = {
    "line1": "4400 Maumee Ave",
    "line2": "Dock B",
    "city": "Toledo",
    "region": "OH",
    "postal_code": "43609",
    "country": "US",
}


def _base_line() -> dict:
    return {
        "line_no": 1,
        "buyer_item_code": "ACM-HW-00412",
        "seller_item_code": None,
        "manufacturer_name": None,
        "manufacturer_part_number": None,
        "gtin": None,
        "description": "HEX CAP SCREW 1/2-13 X 2 GR5 ZINC",
        "quantity": 4,
        "uom_raw": "BX",
        "uom": "BX",
        "pack": {"raw": "BX/50", "inner_count": 50, "inner_size": 1, "inner_uom": "EA"},
        "unit_price": 18.75,
        "price_uom": "BX",
        "price_basis_qty": 1,
        "discount_pct": None,
        "line_amount": 75.0,
        "requested_delivery_date": None,
        "notes": None,
        "resolution": {
            "sku": "FST-HCS-12-13X2-G5Z-B50",
            "erp_product_id": 1012,
            "erp_uom": "BX",
            "erp_uom_id": 31,
            "erp_quantity": 4,
            "conversion_factor": 1,
            "method": "XREF",
            "score": 1.0,
            "candidates": [],
            "erp_list_price": 18.75,
        },
    }


def make_vof(**overrides) -> dict:
    """VOF sintetico pulito, allineato a schema/example-mro.json."""
    order = {
        "schema_version": "1.0",
        "order_id": "7b1e6c2a-3f4d-4e8a-9c51-2d0f6a9b1e77",
        "tenant_id": "delta-industrial-supply",
        "document_type": "ORIGINAL",
        "status": "EXTRACTED",
        "source": {
            "channel": "EMAIL_IMAP",
            "message_id": "<po-4500012345@acme-mfg.example>",
            "from_address": "purchasing@acme-mfg.example",
            "subject": "PO 4500012345",
            "received_at": "2026-11-03T14:22:05Z",
            "documents": [
                {
                    "document_id": "doc-01",
                    "kind": "PDF_TEXT",
                    "filename": "PO_4500012345.pdf",
                    "mime_type": "application/pdf",
                    "sha256": "3f5a0c9e1b7d4a2f8e6c0b9a7d5e3f1a2c4b6d8e0f1a3c5e7b9d1f3a5c7e9b1d",
                    "page_count": 1,
                }
            ],
        },
        "buyer": {
            "name": "Acme Manufacturing Inc. (SYNTHETIC)",
            "contact": {"email": "purchasing@acme-mfg.example"},
            "resolved": {
                "erp_partner_id": 42,
                "erp_partner_ref": "C-ACME",
                "method": "EMAIL_DOMAIN",
                "score": 0.99,
            },
        },
        "seller": {
            "name": "Delta Industrial Supply LLC (SYNTHETIC)",
            "peppol_endpoint": "0088:1234567890128",
        },
        "ship_to": {
            "name": "Acme Plant 2",
            "code_on_document": "PLANT-02",
            "address": copy.deepcopy(SHIP_ADDRESS),
            "resolved": {
                "erp_partner_id": 44,
                "erp_partner_ref": None,
                "method": "CODE",
                "score": 1.0,
            },
        },
        "header": {
            "po_number": "4500012345",
            "po_revision": 0,
            "po_date": "2026-11-03",
            "requested_delivery_date": "2026-11-10",
            "currency": "USD",
            "payment_terms_text": "Net 30",
        },
        "lines": [_base_line()],
        "charges": [],
        "totals": {
            "lines_amount_declared": 75.0,
            "total_amount_declared": 75.0,
            "lines_amount_computed": 75.0,
        },
        "evidence": {
            "/header/po_number": {
                "confidence": 0.99,
                "snippet": "PO Number: 4500012345",
            }
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(order.get(key), dict):
            merged = copy.deepcopy(order[key])
            merged.update(value)
            order[key] = merged
        else:
            order[key] = value
    return order


def seed_ref() -> MockReferenceDataProvider:
    ref = MockReferenceDataProvider()
    ref.add_customer(
        CustomerRecord(
            erp_partner_id=42,
            erp_partner_ref="C-ACME",
            name="Acme Manufacturing Inc. (SYNTHETIC)",
            email_domain="acme-mfg.example",
            currency="USD",
            payment_terms="Net 30",
            sale_warn="no-message",
            ship_to=[{"code": "PLANT-02", "address": copy.deepcopy(SHIP_ADDRESS)}],
            delivery_partner_ids=[44],
            allowlisted=True,
            approved_orders_without_corrections=25,
            peppol_endpoint="0088:1234567890128",
            gln="1234567890128",
        )
    )
    ref.add_product(
        ProductRecord(
            sku="FST-HCS-12-13X2-G5Z-B50",
            erp_product_id=1012,
            name="HEX CAP SCREW 1/2-13 X 2 GR5 ZINC",
            sale_uom="BX",
            list_price=18.75,
            gtin="9999900000009",
            manufacturer_part_number="HCS-12-13X2",
            pack={"raw": "BX/50", "inner_count": 50, "inner_uom": "EA"},
            conversions=[{"from_uom": "BX", "to_uom": "EA", "factor": 50.0}],
            active=True,
            sale_ok=True,
            sale_multiple=1,
            min_order_qty=1,
        )
    )
    ref.add_product(
        ProductRecord(
            sku="JAN-LNR-4046-15-BK",
            erp_product_id=3110,
            name="Can Liner 40x46",
            sale_uom="CS",
            list_price=41.20,
            gtin="9999900000016",
            manufacturer_part_number="JS-0457-ALT",
            pack={"raw": "100/CS", "inner_count": 100, "inner_uom": "EA"},
            conversions=[{"from_uom": "CS", "to_uom": "EA", "factor": 100.0}],
            active=True,
            sale_ok=True,
        )
    )
    ref.add_xref(
        XrefRecord(
            customer_ref="C-ACME",
            customer_item_code="ACM-HW-00412",
            sku="FST-HCS-12-13X2-G5Z-B50",
            erp_product_id=1012,
            status="TRUSTED",
        )
    )
    return ref


@pytest.fixture
def ref() -> MockReferenceDataProvider:
    return seed_ref()


@pytest.fixture
def engine(ref: MockReferenceDataProvider) -> ValidationEngine:
    return ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)


def fired(result, code: str) -> list:
    return [item for item in result.issues if item.rule_id == code]


def assert_clean(result, code: str) -> None:
    assert fired(result, code) == [], f"{code} non doveva scattare: {fired(result, code)}"


def assert_hit(result, code: str, severity: Severity | None = None):
    hits = fired(result, code)
    assert hits, f"{code} doveva scattare"
    if severity is not None:
        assert hits[0].severity == severity
    return hits


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_all_architecture_rules_registered(self) -> None:
        registered = set(get_all_rules())
        assert registered == set(CATALOG_RULES)

    def test_each_rule_has_positive_and_negative_test(self) -> None:
        """Meta-check: questo file definisce test_xx_pass e test_xx_fail per ogni regola."""
        import ast

        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        missing = []
        for code in CATALOG_RULES:
            slug = code.lower().replace("-", "_")
            if f"test_{slug}_pass" not in names or f"test_{slug}_fail" not in names:
                missing.append(code)
        assert missing == [], f"Mancano pass/fail per: {missing}"


# ---------------------------------------------------------------------------
# HDR
# ---------------------------------------------------------------------------


class TestHdr:
    def test_hdr_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-01")

    def test_hdr_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof(header={"po_number": "", "po_date": "2026-11-03", "currency": "USD"})
        assert_hit(engine.validate(order), "HDR-01", Severity.BLOCK)

    def test_hdr_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-02")

    def test_hdr_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["header"]["po_date"] = "2026-12-01"
        assert_hit(engine.validate(order), "HDR-02", Severity.REVIEW)

    def test_hdr_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-03")

    def test_hdr_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["header"]["currency"] = "EUR"
        assert_hit(engine.validate(order), "HDR-03", Severity.REVIEW)

    def test_hdr_04_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-04")

    def test_hdr_04_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["header"]["requested_delivery_date"] = "2026-10-01"
        assert_hit(engine.validate(order), "HDR-04", Severity.REVIEW)

    def test_hdr_05_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-05")

    def test_hdr_05_fail(self, engine: ValidationEngine) -> None:
        assert_hit(engine.validate(make_vof(document_type="CANCEL")), "HDR-05", Severity.REVIEW)

    def test_hdr_06_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "HDR-06")

    def test_hdr_06_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["header"]["payment_terms_text"] = "Net 45"
        assert_hit(engine.validate(order), "HDR-06", Severity.WARN)


# ---------------------------------------------------------------------------
# CUS
# ---------------------------------------------------------------------------


class TestCus:
    def test_cus_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "CUS-01")

    def test_cus_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof(buyer={"name": "Unknown", "resolved": None})
        assert_hit(engine.validate(order), "CUS-01", Severity.BLOCK)

    def test_cus_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "CUS-02")

    def test_cus_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["buyer"]["resolved"] = {
            "erp_partner_id": 42,
            "erp_partner_ref": "C-ACME",
            "method": "FUZZY_NAME",
            "score": 0.80,
        }
        assert_hit(engine.validate(order), "CUS-02", Severity.REVIEW)

    def test_cus_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "CUS-03")

    def test_cus_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["ship_to"] = {
            "name": "Altro magazzino",
            "address": {
                "line1": "1 Unknown Rd",
                "city": "Detroit",
                "postal_code": "48201",
                "country": "US",
            },
            "resolved": {"erp_partner_id": 99, "method": "ADDRESS", "score": 0.7},
        }
        assert_hit(engine.validate(order), "CUS-03", Severity.REVIEW)

    def test_cus_04_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "CUS-04")

    def test_cus_04_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["source"]["from_address"] = "buyer@other-corp.example"
        assert_hit(engine.validate(order), "CUS-04", Severity.REVIEW)

    def test_cus_05_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "CUS-05")

    def test_cus_05_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.get_customer_by_ref("C-ACME").sale_warn = "block"
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "CUS-05", Severity.REVIEW)


# ---------------------------------------------------------------------------
# ITM
# ---------------------------------------------------------------------------


class TestItm:
    def test_itm_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "ITM-01")

    def test_itm_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["resolution"] = {
            "sku": None,
            "erp_product_id": None,
            "method": "UNRESOLVED",
            "score": 0.2,
            "candidates": [],
        }
        assert_hit(engine.validate(order), "ITM-01", Severity.BLOCK)

    def test_itm_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "ITM-02")

    def test_itm_02_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.get_product_by_sku("FST-HCS-12-13X2-G5Z-B50").active = False
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "ITM-02", Severity.BLOCK)

    def test_itm_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "ITM-03")

    def test_itm_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["resolution"]["method"] = "FUZZY"
        order["lines"][0]["resolution"]["score"] = 0.88
        assert_hit(engine.validate(order), "ITM-03", Severity.REVIEW)

    def test_itm_04_pass(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["gtin"] = "9999900000009"
        order["lines"][0]["manufacturer_part_number"] = "HCS-12-13X2"
        assert_clean(engine.validate(order), "ITM-04")

    def test_itm_04_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["gtin"] = "9999900000016"
        assert_hit(engine.validate(order), "ITM-04", Severity.REVIEW)

    def test_itm_05_pass(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["gtin"] = "9999900000009"
        assert_clean(engine.validate(order), "ITM-05")

    def test_itm_05_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["gtin"] = "9999900000000"
        assert_hit(engine.validate(order), "ITM-05", Severity.WARN)

    def test_itm_06_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "ITM-06")

    def test_itm_06_fail(self, engine: ValidationEngine) -> None:
        line2 = _base_line()
        line2["line_no"] = 2
        line2["line_amount"] = 75.0
        order = make_vof(lines=[_base_line(), line2], totals={"total_amount_declared": 150.0})
        assert_hit(engine.validate(order), "ITM-06", Severity.WARN)

    def test_itm_07_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "ITM-07")

    def test_itm_07_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.get_xref("C-ACME", "ACM-HW-00412").status = "CANDIDATE"
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "ITM-07", Severity.REVIEW)


# ---------------------------------------------------------------------------
# UOM
# ---------------------------------------------------------------------------


class TestUom:
    def test_uom_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "UOM-01")

    def test_uom_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["uom"] = "Bananas"
        order["lines"][0]["uom_raw"] = "Bananas"
        assert_hit(engine.validate(order), "UOM-01", Severity.REVIEW)

    def test_uom_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "UOM-02")

    def test_uom_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["uom"] = "KGM"
        order["lines"][0]["uom_raw"] = "KG"
        order["lines"][0]["resolution"]["conversion_factor"] = None
        order["lines"][0]["resolution"]["erp_uom"] = "BX"
        assert_hit(engine.validate(order), "UOM-02", Severity.BLOCK)

    def test_uom_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "UOM-03")

    def test_uom_03_fail(self, engine: ValidationEngine) -> None:
        """'Fail' = la INFO scatta perché è stata applicata una conversione."""
        order = make_vof()
        order["lines"][0]["uom"] = "DZN"
        order["lines"][0]["uom_raw"] = "DZ"
        order["lines"][0]["quantity"] = 2
        order["lines"][0]["resolution"]["erp_uom"] = "EA"
        order["lines"][0]["resolution"]["erp_quantity"] = 24
        order["lines"][0]["resolution"]["conversion_factor"] = 12
        assert_hit(engine.validate(order), "UOM-03", Severity.INFO)

    def test_uom_04_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "UOM-04")

    def test_uom_04_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["pack"] = {"raw": "BX/100", "inner_count": 100, "inner_uom": "EA"}
        assert_hit(engine.validate(order), "UOM-04", Severity.REVIEW)

    def test_uom_05_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "UOM-05")

    def test_uom_05_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["resolution"]["erp_quantity"] = 4.5
        order["lines"][0]["resolution"]["erp_uom"] = "EA"
        assert_hit(engine.validate(order), "UOM-05", Severity.REVIEW)


# ---------------------------------------------------------------------------
# QTY / PRC / TOT
# ---------------------------------------------------------------------------


class TestQtyPrcTot:
    def test_qty_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "QTY-01")

    def test_qty_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["quantity"] = 0
        assert_hit(engine.validate(order), "QTY-01", Severity.BLOCK)

    def test_qty_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "QTY-02")

    def test_qty_02_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.set_qty_p99("C-ACME", "FST-HCS-12-13X2-G5Z-B50", 1.0)
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "QTY-02", Severity.REVIEW)

    def test_qty_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "QTY-03")

    def test_qty_03_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.get_product_by_sku("FST-HCS-12-13X2-G5Z-B50").min_order_qty = 10
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "QTY-03", Severity.WARN)

    def test_prc_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "PRC-01")

    def test_prc_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["unit_price"] = 30.0
        order["lines"][0]["line_amount"] = 120.0
        order["totals"] = {"total_amount_declared": 120.0}
        assert_hit(engine.validate(order), "PRC-01", Severity.REVIEW)

    def test_prc_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "PRC-02")

    def test_prc_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["unit_price"] = None
        assert_hit(engine.validate(order), "PRC-02", Severity.INFO)

    def test_prc_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "PRC-03")

    def test_prc_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["line_amount"] = 10.0
        assert_hit(engine.validate(order), "PRC-03", Severity.REVIEW)

    def test_prc_04_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "PRC-04")

    def test_prc_04_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["notes"] = "price per C"
        order["lines"][0]["price_basis_qty"] = 1
        assert_hit(engine.validate(order), "PRC-04", Severity.REVIEW)

    def test_tot_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "TOT-01")

    def test_tot_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof(totals={"total_amount_declared": 999.0})
        assert_hit(engine.validate(order), "TOT-01", Severity.REVIEW)

    def test_tot_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "TOT-02")

    def test_tot_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["line_no"] = 3
        assert_hit(engine.validate(order), "TOT-02", Severity.BLOCK)

    def test_tot_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "TOT-03")

    def test_tot_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof(
            charges=[{"type": "FREIGHT", "amount": 12.0}],
            totals={"total_amount_declared": 87.0},
        )
        assert_hit(engine.validate(order), "TOT-03", Severity.WARN)


# ---------------------------------------------------------------------------
# DUP / EXT / SEC / EXP
# ---------------------------------------------------------------------------


class TestDupExtSecExp:
    def test_dup_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "DUP-01")

    def test_dup_01_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.add_order(
            HistoricalOrder(
                order_id="ORD-OLD",
                customer_ref="C-ACME",
                po_number="4500012345",
                po_revision=0,
                status="POSTED",
            )
        )
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        result = engine.validate(make_vof())
        assert_hit(result, "DUP-01", Severity.BLOCK)
        assert result.decision == DecisionRoute.REJECT

    def test_dup_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "DUP-02")

    def test_dup_02_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.add_order(
            HistoricalOrder(
                order_id="ORD-HASH",
                customer_ref="C-ACME",
                po_number="OTHER",
                message_id="<po-4500012345@acme-mfg.example>",
                status="POSTED",
            )
        )
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        result = engine.validate(make_vof())
        assert_hit(result, "DUP-02", Severity.BLOCK)
        assert result.decision == DecisionRoute.REJECT

    def test_dup_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "DUP-03")

    def test_dup_03_fail(self, ref: MockReferenceDataProvider) -> None:
        ref.add_order(
            HistoricalOrder(
                order_id="ORD-SIM",
                customer_ref="C-ACME",
                po_number="4500099999",
                po_date="2026-11-04",
                status="POSTED",
                lines=[{"sku": "FST-HCS-12-13X2-G5Z-B50", "quantity": 4}],
            )
        )
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        assert_hit(engine.validate(make_vof()), "DUP-03", Severity.REVIEW)

    def test_ext_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "EXT-01")

    def test_ext_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["evidence"]["/header/po_number"] = {"confidence": 0.5, "snippet": "PO"}
        assert_hit(engine.validate(order), "EXT-01", Severity.REVIEW)

    def test_ext_02_pass(self, engine: ValidationEngine) -> None:
        result = engine.validate(
            make_vof(),
            document_text="PO Number: 4500012345 HEX CAP SCREW",
        )
        assert_clean(result, "EXT-02")

    def test_ext_02_fail(self, engine: ValidationEngine) -> None:
        result = engine.validate(make_vof(), document_text="nessuno snippet qui")
        assert_hit(result, "EXT-02", Severity.REVIEW)

    def test_ext_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "EXT-03")

    def test_ext_03_fail(self, engine: ValidationEngine) -> None:
        result = engine.validate(
            make_vof(),
            llm_schema_attempts=2,
            llm_schema_valid=False,
        )
        assert_hit(result, "EXT-03", Severity.REVIEW)

    def test_sec_01_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof()), "SEC-01")

    def test_sec_01_fail(self, engine: ValidationEngine) -> None:
        result = engine.validate(
            make_vof(),
            security=SecurityHints(filename="payload.exe", has_macros=False),
        )
        assert_hit(result, "SEC-01", Severity.BLOCK)
        assert result.decision == DecisionRoute.REJECT

    def test_sec_02_pass(self, engine: ValidationEngine) -> None:
        """SEC-02 è disabilitata di default: non deve scattare nemmeno con SPF fail."""
        result = engine.validate(make_vof(), security=SecurityHints(spf_pass=False))
        assert_clean(result, "SEC-02")

    def test_sec_02_fail(self, ref: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        engine.rules_config["disabled_rules"] = []
        result = engine.validate(make_vof(), security=SecurityHints(spf_pass=False))
        assert_hit(result, "SEC-02", Severity.REVIEW)

    def test_exp_01_pass(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["buyer"]["peppol_endpoint"] = "0088:1234567890128"
        assert_clean(engine.validate(order, export_target="PEPPOL"), "EXP-01")

    def test_exp_01_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["buyer"]["peppol_endpoint"] = None
        order["buyer"]["gln"] = None
        order["seller"]["peppol_endpoint"] = None
        assert_hit(engine.validate(order, export_target="PEPPOL"), "EXP-01", Severity.BLOCK)

    def test_exp_02_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof(), export_target="X12"), "EXP-02")

    def test_exp_02_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["description"] = "X" * 80
        assert_hit(engine.validate(order, export_target="X12"), "EXP-02", Severity.WARN)

    def test_exp_03_pass(self, engine: ValidationEngine) -> None:
        assert_clean(engine.validate(make_vof(), export_target="PEPPOL"), "EXP-03")

    def test_exp_03_fail(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["lines"][0]["uom"] = "ZZZ"
        order["lines"][0]["uom_raw"] = "ZZZ"
        result = engine.validate(order, export_target="PEPPOL")
        assert_hit(result, "EXP-03", Severity.BLOCK)


# ---------------------------------------------------------------------------
# Motore, routing, DatagenLoader, esempio VOF
# ---------------------------------------------------------------------------


class TestEngineAndDatagen:
    def test_clean_order_auto_post(self, engine: ValidationEngine) -> None:
        result = engine.validate(make_vof())
        blocking = [i for i in result.issues if i.severity in {Severity.BLOCK, Severity.REVIEW}]
        assert blocking == []
        assert result.decision == DecisionRoute.AUTO_POST
        assert result.score >= 0.97

    def test_review_without_reject(self, engine: ValidationEngine) -> None:
        order = make_vof()
        order["header"]["po_date"] = "2026-12-01"
        result = engine.validate(order)
        assert result.decision == DecisionRoute.REVIEW
        assert "HDR-02" in result.reasons

    def test_severity_override(self, ref: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        engine.rules_config["severity_overrides"] = {"HDR-06": "BLOCK"}
        order = make_vof()
        order["header"]["payment_terms_text"] = "CIA"
        hits = assert_hit(engine.validate(order), "HDR-06", Severity.BLOCK)
        assert hits[0].json_pointer == "/header/payment_terms_text"

    def test_issue_schema_shape(self, engine: ValidationEngine) -> None:
        order = make_vof(header={"po_number": "", "po_date": "2026-11-03", "currency": "USD"})
        result = engine.validate(order)
        payload = result.to_vof_fields()
        issue = payload["validation"]["issues"][0]
        assert set(issue) >= {"code", "severity", "path", "message"}
        assert payload["decision"]["route"] in {"AUTO_POST", "REVIEW", "REJECT"}

    def test_synthetic_provider_from_datagen(self) -> None:
        provider = SyntheticReferenceDataProvider.from_datagen()
        customer = provider.get_customer_by_ref("C-ACME")
        assert customer is not None
        assert "SYNTHETIC" in customer.name
        product = provider.get_product_by_sku("ADH-EPX-000")
        assert product is not None
        assert product.gtin
        assert provider.is_valid_uom("EA")
        assert provider.is_valid_uom("CS")

    def test_example_mro_runs(self, ref: MockReferenceDataProvider) -> None:
        example = json.loads((REPO / "schema" / "example-mro.json").read_text(encoding="utf-8"))
        engine = ValidationEngine(config_dir=CONFIG, reference_data=ref, as_of=AS_OF)
        result = engine.validate(example)
        assert result is not None
        assert result.decision in {DecisionRoute.REVIEW, DecisionRoute.REJECT, DecisionRoute.AUTO_POST}
