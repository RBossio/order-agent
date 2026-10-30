"""Test del riconoscimento clienti e articoli: due casi per strategia, ambigui, sconosciuti."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ventureorder.match import (
    CUSTOMER_INPUT_FIELDS,
    FORBIDDEN_ID_FIELDS,
    ITEM_INPUT_FIELDS,
    CustomerMatcher,
    ItemMatcher,
    apply_matches,
    sanitize_extracted_order,
)
from ventureorder.match.noise import (
    GENERIC_EMAIL_DOMAINS,
    NOISY_EVAL_SEED,
    apply_variants,
    select_kinds_for_order,
    variant_rng,
)
from ventureorder.match.normalize import (
    normalize_gtin,
    normalize_item_code,
    normalize_sku,
    normalize_tax_id,
)
from ventureorder.rules import (
    CustomerRecord,
    DecisionRoute,
    MockReferenceDataProvider,
    ProductRecord,
    Severity,
    ValidationEngine,
    XrefRecord,
)

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config"
AS_OF = date(2026, 11, 3)

ACME_ADDRESS = {
    "line1": "1375 Business Park Rd",
    "city": "Toledo",
    "region": "OH",
    "postal_code": "43601",
    "country": "US",
}
ACME_SHIP = {
    "line1": "9494 Corporate Dr",
    "city": "Grand Rapids",
    "region": "MI",
    "postal_code": "49503",
    "country": "US",
}
DELTA_ADDRESS = {
    "line1": "1543 Corporate Dr",
    "city": "Dayton",
    "region": "OH",
    "postal_code": "45402",
    "country": "US",
}


def _customer(**kwargs) -> CustomerRecord:
    defaults = {
        "erp_partner_id": 42,
        "erp_partner_ref": "C-ACME",
        "name": "Acme Company (SYNTHETIC)",
        "email_domain": "acme.example",
        "tax_id": "12-8713396",
        "address": dict(ACME_ADDRESS),
        "email": "purchasing@acme.example",
        "ship_to": [{"code": "SHIP-01", "address": dict(ACME_SHIP)}],
    }
    defaults.update(kwargs)
    return CustomerRecord(**defaults)


def seed_provider() -> MockReferenceDataProvider:
    ref = MockReferenceDataProvider()
    ref.add_customer(_customer())
    ref.add_customer(
        _customer(
            erp_partner_id=45,
            erp_partner_ref="C-DELTA",
            name="Delta Holdings (SYNTHETIC)",
            email_domain="delta.example",
            tax_id="68-7070880",
            address=dict(DELTA_ADDRESS),
            email="purchasing@delta.example",
            ship_to=[],
        )
    )
    ref.add_product(
        ProductRecord(
            sku="FST-HCS-12-13X2-G5Z-B50",
            erp_product_id=1012,
            name="Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc (SYNTHETIC)",
            sale_uom="BX",
            list_price=18.75,
            gtin="9999900000009",
            manufacturer_part_number="HCS-12-13X2",
            pack={"raw": "BX/50", "inner_count": 50, "inner_uom": "EA"},
            conversions=[
                {"from_uom": "BX", "to_uom": "EA", "factor": 50.0},
                {"from_uom": "CS", "to_uom": "BX", "factor": 10.0},
            ],
        )
    )
    ref.add_product(
        ProductRecord(
            sku="PPE-GLV-NIT-8-XL-BLU",
            erp_product_id=1144,
            name="Nitrile Gloves XL Blue 8mil PF (SYNTHETIC)",
            sale_uom="CS",
            list_price=96.34,
            gtin="9999900000344",
            conversions=[
                {"from_uom": "CS", "to_uom": "BX", "factor": 10.0},
                {"from_uom": "BX", "to_uom": "EA", "factor": 100.0},
            ],
        )
    )
    ref.add_product(
        ProductRecord(
            sku="PPE-GLV-NIT-5-XL-BLU",
            erp_product_id=1145,
            name="Nitrile Gloves XL Blue 5mil PF (SYNTHETIC)",
            sale_uom="CS",
            list_price=72.06,
            gtin="9999900000337",
            conversions=[{"from_uom": "CS", "to_uom": "BX", "factor": 10.0}],
        )
    )
    ref.add_product(
        ProductRecord(
            sku="TOOL-WRN-10IN",
            erp_product_id=1200,
            name="Adjustable Wrench 10in (SYNTHETIC)",
            sale_uom="EA",
            list_price=18.82,
            gtin="9999900001839",
        )
    )
    ref.add_product(
        ProductRecord(
            sku="ABR-COW-6IN-A",
            erp_product_id=1301,
            name="Cut-Off Wheel 6in (SYNTHETIC)",
            sale_uom="BX",
            list_price=20.0,
            gtin="9999900001846",
        )
    )
    ref.add_product(
        ProductRecord(
            sku="ABR-COW-6IN-B",
            erp_product_id=1302,
            name="Cut-Off Wheel 6in (SYNTHETIC)",
            sale_uom="BX",
            list_price=21.0,
            gtin="9999900000016",
        )
    )
    ref.add_xref(
        XrefRecord(
            customer_ref="C-ACME",
            customer_item_code="ACME-HW-00412",
            sku="FST-HCS-12-13X2-G5Z-B50",
            erp_product_id=1012,
            status="TRUSTED",
        )
    )
    ref.add_xref(
        XrefRecord(
            customer_ref="C-ACME",
            customer_item_code="ACME-GLV-8XL",
            sku="PPE-GLV-NIT-8-XL-BLU",
            erp_product_id=1144,
            status="CANDIDATE",
        )
    )
    return ref


@pytest.fixture
def provider() -> MockReferenceDataProvider:
    return seed_provider()


@pytest.fixture
def customers(provider: MockReferenceDataProvider) -> CustomerMatcher:
    return CustomerMatcher(provider)


@pytest.fixture
def items(provider: MockReferenceDataProvider) -> ItemMatcher:
    return ItemMatcher(provider)


def _vof(**overrides) -> dict:
    order = {
        "source": {"from_address": "purchasing@acme.example"},
        "buyer": {
            "name": "Acme Company (SYNTHETIC)",
            "tax_id": "12-8713396",
            "address": dict(ACME_ADDRESS),
            "contact": {"email": "purchasing@acme.example"},
        },
        "lines": [],
    }
    order.update(overrides)
    return order


def _line(**overrides) -> dict:
    line = {
        "line_no": 1,
        "buyer_item_code": None,
        "seller_item_code": None,
        "gtin": None,
        "description": "Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc",
        "quantity": 4,
        "uom": "BX",
        "uom_raw": "BX",
    }
    line.update(overrides)
    return line


# ---------------------------------------------------------------------------
# Normalizzazione
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_tax_id_strips_us_prefix_and_dashes(self) -> None:
        assert normalize_tax_id("US12-8713396") == normalize_tax_id("12-8713396")
        assert normalize_tax_id("12-8713396") == "128713396"

    def test_item_code_drops_separators_and_leading_zeros(self) -> None:
        assert normalize_item_code("ACME-HW-00412") == normalize_item_code("acme.hw.00412")
        assert normalize_item_code("ACME-HW-00412") == "ACMEHW00412"
        assert normalize_item_code("00-412") == "412"

    def test_gtin_pads_valid_checksum(self) -> None:
        assert normalize_gtin("9999900000009") == "09999900000009"
        assert normalize_gtin("9999900000008") is None


# ---------------------------------------------------------------------------
# Cliente — TAX_ID
# ---------------------------------------------------------------------------


class TestCustomerTaxId:
    def test_tax_id_exact(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(_vof(buyer={"tax_id": "12-8713396"}))
        assert match.resolved
        assert match.method == "TAX_ID"
        assert match.score == 1.0
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"

    def test_tax_id_with_prefix_and_punctuation(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(_vof(buyer={"tax_id": "US 12-8713396"}))
        assert match.method == "TAX_ID"
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"


# ---------------------------------------------------------------------------
# Cliente — EMAIL_DOMAIN
# ---------------------------------------------------------------------------


class TestCustomerEmail:
    def test_email_domain_from_sender(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={"from_address": "buyer@delta.example"},
                buyer={"name": None, "tax_id": None, "contact": {}},
            )
        )
        assert match.method == "EMAIL_DOMAIN"
        assert match.score == pytest.approx(0.99)
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-DELTA"

    def test_email_domain_from_contact(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={"from_address": None},
                buyer={
                    "name": None,
                    "tax_id": None,
                    "contact": {"email": "purchasing@acme.example"},
                },
            )
        )
        assert match.method == "EMAIL_DOMAIN"
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"


# ---------------------------------------------------------------------------
# Cliente — FUZZY_NAME
# ---------------------------------------------------------------------------


class TestCustomerName:
    def test_name_normalized_exact(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={},
                buyer={"name": "Acme Company Inc.", "tax_id": None, "contact": {}},
            )
        )
        assert match.method == "FUZZY_NAME"
        assert match.score >= 0.95
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"

    def test_name_fuzzy_typo(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={},
                buyer={"name": "Acme Companyy", "tax_id": None, "contact": {}},
            )
        )
        assert match.method == "FUZZY_NAME"
        assert match.resolved
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"
        assert 0 < match.score <= 0.95


# ---------------------------------------------------------------------------
# Cliente — ADDRESS
# ---------------------------------------------------------------------------


class TestCustomerAddress:
    def test_address_billing(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={},
                buyer={"name": None, "tax_id": None, "address": dict(DELTA_ADDRESS)},
            )
        )
        assert match.method == "ADDRESS"
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-DELTA"

    def test_address_shipping(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={},
                buyer={"name": None, "tax_id": None, "address": dict(ACME_SHIP)},
            )
        )
        assert match.method == "ADDRESS"
        assert match.customer is not None
        assert match.customer.erp_partner_ref == "C-ACME"


# ---------------------------------------------------------------------------
# Cliente — ambiguo / sconosciuto
# ---------------------------------------------------------------------------


class TestCustomerEdge:
    def test_ambiguous_similar_names(self, provider: MockReferenceDataProvider) -> None:
        provider.add_customer(
            _customer(
                erp_partner_id=99,
                erp_partner_ref="C-ACME-WEST",
                name="Acme Company (SYNTHETIC)",
                email_domain="acme-west.example",
                tax_id="11-1111111",
                address={"line1": "1 West Rd", "city": "Akron", "postal_code": "44301"},
            )
        )
        matcher = CustomerMatcher(provider)
        match = matcher.resolve(
            _vof(source={}, buyer={"name": "Acme Company", "tax_id": None, "contact": {}})
        )
        assert match.ambiguous
        assert match.customer is None
        assert match.to_vof() is not None
        assert match.to_vof()["erp_partner_id"] is None
        assert len(match.candidates) >= 2

    def test_unknown_customer(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            _vof(
                source={"from_address": "nobody@void.example"},
                buyer={
                    "name": "Zeta Unknown GmbH",
                    "tax_id": "00-0000099",
                    "address": {
                        "line1": "1 Nowhere Ln",
                        "city": "Mars",
                        "postal_code": "00000",
                    },
                    "contact": {"email": "nobody@void.example"},
                },
            )
        )
        assert not match.resolved
        assert match.method == "UNRESOLVED"
        assert match.to_vof() is None


# ---------------------------------------------------------------------------
# Articoli — XREF
# ---------------------------------------------------------------------------


class TestItemXref:
    def test_xref_trusted(self, items: ItemMatcher) -> None:
        match = items.resolve(_line(buyer_item_code="ACME-HW-00412"), "C-ACME")
        assert match.method == "XREF"
        assert match.score == pytest.approx(1.0)
        assert match.product is not None
        assert match.product.sku == "FST-HCS-12-13X2-G5Z-B50"

    def test_xref_normalized_separators(self, items: ItemMatcher) -> None:
        match = items.resolve(_line(buyer_item_code="acme.hw.00412"), "C-ACME")
        assert match.method == "XREF"
        assert match.product is not None
        assert match.product.sku == "FST-HCS-12-13X2-G5Z-B50"


# ---------------------------------------------------------------------------
# Articoli — SKU interno
# ---------------------------------------------------------------------------


class TestItemSku:
    def test_seller_sku_exact(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(buyer_item_code=None, seller_item_code="TOOL-WRN-10IN"),
            "C-ACME",
        )
        assert match.method == "SELLER_CODE"
        assert match.score == pytest.approx(0.98)
        assert match.product is not None
        assert match.product.sku == "TOOL-WRN-10IN"

    def test_buyer_code_as_internal_sku(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(buyer_item_code="ppe-glv-nit-8-xl-blu", seller_item_code=None),
            "C-DELTA",
        )
        assert match.method == "SELLER_CODE"
        assert match.product is not None
        assert match.product.sku == "PPE-GLV-NIT-8-XL-BLU"


# ---------------------------------------------------------------------------
# Articoli — GTIN
# ---------------------------------------------------------------------------


class TestItemGtin:
    def test_gtin_13(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(buyer_item_code=None, gtin="9999900000009"),
            None,
        )
        assert match.method == "GTIN"
        assert match.score == pytest.approx(0.99)
        assert match.product is not None
        assert match.product.sku == "FST-HCS-12-13X2-G5Z-B50"

    def test_gtin_with_spaces_and_padding(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(buyer_item_code=None, gtin=" 9999900000344 "),
            None,
        )
        assert match.method == "GTIN"
        assert match.product is not None
        assert match.product.sku == "PPE-GLV-NIT-8-XL-BLU"


# ---------------------------------------------------------------------------
# Articoli — descrizione fuzzy (misura e colore)
# ---------------------------------------------------------------------------


class TestItemFuzzy:
    def test_fuzzy_unique_description(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(
                buyer_item_code=None,
                seller_item_code=None,
                gtin=None,
                description="Adjustable Wrench 10 inch",
                uom="EA",
            ),
            None,
        )
        assert match.method == "FUZZY"
        assert match.product is not None
        assert match.product.sku == "TOOL-WRN-10IN"
        assert match.score >= 0.75
        assert not match.ambiguous

    def test_fuzzy_color_and_measure_tokens(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(
                buyer_item_code=None,
                gtin=None,
                description="NIT gloves XL BLU 8 mil PF",
                uom="CS",
            ),
            None,
        )
        assert match.method == "FUZZY"
        assert match.product is not None
        assert match.product.sku == "PPE-GLV-NIT-8-XL-BLU"
        assert match.score >= 0.75


# ---------------------------------------------------------------------------
# Articoli — ambiguo / sconosciuto + UoM
# ---------------------------------------------------------------------------


class TestItemEdge:
    def test_ambiguous_same_description(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(
                buyer_item_code=None,
                gtin=None,
                description="Cut-Off Wheel 6in (SYNTHETIC)",
                uom="BX",
            ),
            None,
        )
        assert match.ambiguous
        assert match.method == "FUZZY"
        assert len(match.candidates) >= 2
        skus = {c.sku for c in match.candidates}
        assert "ABR-COW-6IN-A" in skus
        assert "ABR-COW-6IN-B" in skus
        payload = match.to_vof()
        assert payload["method"] == "FUZZY"
        assert len(payload["candidates"]) <= 3

    def test_unknown_item(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(
                buyer_item_code="ZZ-UNKNOWN-999",
                seller_item_code=None,
                gtin=None,
                description="Quantum Flux Capacitor Mk.IX",
            ),
            "C-ACME",
        )
        assert match.method == "UNRESOLVED"
        assert match.product is None
        assert match.to_vof()["sku"] is None

    def test_uom_conversion_uses_product_factors(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(seller_item_code="FST-HCS-12-13X2-G5Z-B50", quantity=3, uom="CS"),
            "C-ACME",
        )
        assert match.product is not None
        assert match.conversion_factor == pytest.approx(10.0)
        assert match.erp_uom == "BX"
        assert match.erp_quantity == pytest.approx(30.0)

    def test_uom_same_unit_factor_one(self, items: ItemMatcher) -> None:
        match = items.resolve(
            _line(seller_item_code="TOOL-WRN-10IN", quantity=2, uom="EA"),
            None,
        )
        assert match.conversion_factor == pytest.approx(1.0)
        assert match.erp_quantity == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Pipeline + regole CUS/ITM e score minimo
# ---------------------------------------------------------------------------


class TestMatchRulesIntegration:
    def test_apply_matches_writes_resolved_fields(
        self, provider: MockReferenceDataProvider
    ) -> None:
        vof = _vof(lines=[_line(buyer_item_code="ACME-HW-00412")])
        apply_matches(vof, provider, overwrite=True)
        assert vof["buyer"]["resolved"]["method"] == "TAX_ID"
        assert vof["buyer"]["resolved"]["erp_partner_ref"] == "C-ACME"
        assert vof["lines"][0]["resolution"]["method"] == "XREF"
        assert vof["lines"][0]["resolution"]["sku"] == "FST-HCS-12-13X2-G5Z-B50"

    def test_cus_01_on_unknown(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-unknown",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"from_address": "x@void.example", "channel": "EMAIL_IMAP"},
            "buyer": {
                "name": "Zeta Unknown GmbH",
                "tax_id": "00-0000099",
                "address": {"line1": "1 None", "city": "Mars", "postal_code": "00000"},
            },
            "header": {"po_number": "PO-1", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [_line(seller_item_code="TOOL-WRN-10IN", uom="EA")],
            "evidence": {},
        }
        result = engine.match_and_validate(vof)
        codes = {item.rule_id for item in result.issues}
        assert "CUS-01" in codes
        assert result.decision == DecisionRoute.REVIEW

    def test_cus_02_uses_fuzzy_confidence(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-fuzzy-cus",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"channel": "EMAIL_IMAP"},
            "buyer": {"name": "Acme Compan"},
            "header": {"po_number": "PO-2", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [_line(seller_item_code="TOOL-WRN-10IN", uom="EA")],
            "evidence": {"/header/po_number": {"confidence": 0.99}},
        }
        result = engine.match_and_validate(vof)
        assert vof["buyer"]["resolved"]["method"] == "FUZZY_NAME"
        buyer_score = float(vof["buyer"]["resolved"]["score"])
        codes = {item.rule_id for item in result.issues}
        if buyer_score < 0.95:
            assert "CUS-02" in codes
        assert result.score <= buyer_score + 1e-9

    def test_itm_01_on_unresolved_line(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-itm-unknown",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"from_address": "purchasing@acme.example", "channel": "EMAIL_IMAP"},
            "buyer": {"tax_id": "12-8713396"},
            "header": {"po_number": "PO-3", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [
                _line(
                    buyer_item_code="NO-SUCH",
                    description="Quantum Flux Capacitor Mk.IX",
                )
            ],
            "evidence": {},
        }
        result = engine.match_and_validate(vof)
        hits = [i for i in result.issues if i.rule_id == "ITM-01"]
        assert hits
        assert hits[0].severity == Severity.BLOCK
        assert vof["lines"][0]["resolution"]["method"] == "UNRESOLVED"

    def test_itm_03_on_fuzzy_line(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-itm-fuzzy",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"from_address": "purchasing@acme.example", "channel": "EMAIL_IMAP"},
            "buyer": {"tax_id": "12-8713396"},
            "header": {"po_number": "PO-4", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [
                _line(
                    buyer_item_code=None,
                    description="Adjustable Wrench 10 inch",
                    uom="EA",
                )
            ],
            "evidence": {"/header/po_number": {"confidence": 0.99}},
        }
        result = engine.match_and_validate(vof)
        assert vof["lines"][0]["resolution"]["method"] == "FUZZY"
        codes = {item.rule_id for item in result.issues}
        assert "ITM-03" in codes
        line_score = float(vof["lines"][0]["resolution"]["score"])
        assert result.score <= line_score + 1e-9

    def test_min_score_uses_match_confidences(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-score",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"from_address": "purchasing@acme.example", "channel": "EMAIL_IMAP"},
            "buyer": {"tax_id": "12-8713396"},
            "header": {"po_number": "PO-5", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [_line(seller_item_code="TOOL-WRN-10IN", uom="EA")],
            "evidence": {"/header/po_number": {"confidence": 0.99}},
        }
        result = engine.match_and_validate(vof)
        buyer_score = float(vof["buyer"]["resolved"]["score"])
        line_score = float(vof["lines"][0]["resolution"]["score"])
        assert result.score <= min(0.99, buyer_score, line_score) + 1e-9

    def test_itm_07_candidate_xref(self, provider: MockReferenceDataProvider) -> None:
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        vof = {
            "schema_version": "1.0",
            "order_id": "match-xref-cand",
            "tenant_id": "delta-industrial-supply",
            "document_type": "ORIGINAL",
            "status": "EXTRACTED",
            "source": {"from_address": "purchasing@acme.example", "channel": "EMAIL_IMAP"},
            "buyer": {"tax_id": "12-8713396"},
            "header": {"po_number": "PO-6", "po_date": "2026-11-03", "currency": "USD"},
            "lines": [_line(buyer_item_code="ACME-GLV-8XL")],
            "evidence": {},
        }
        result = engine.match_and_validate(vof)
        assert vof["lines"][0]["resolution"]["method"] == "XREF"
        assert vof["lines"][0]["resolution"]["score"] == pytest.approx(0.95)
        codes = {item.rule_id for item in result.issues}
        assert "ITM-07" in codes


# ---------------------------------------------------------------------------
# Nessuna lettura degli ID attesi (customer_id / product_id)
# ---------------------------------------------------------------------------


class TestNoIdLeakage:
    def test_input_fields_are_documented(self) -> None:
        assert "buyer.tax_id" in CUSTOMER_INPUT_FIELDS
        assert "buyer.name" in CUSTOMER_INPUT_FIELDS
        assert "source.from_address" in CUSTOMER_INPUT_FIELDS
        assert "lines[].buyer_item_code" in ITEM_INPUT_FIELDS
        assert "lines[].description" in ITEM_INPUT_FIELDS
        assert "buyer.resolved" in FORBIDDEN_ID_FIELDS
        assert "buyer.code_on_document" in FORBIDDEN_ID_FIELDS
        assert "lines[].resolution" in FORBIDDEN_ID_FIELDS
        assert "lines[].sku" in FORBIDDEN_ID_FIELDS

    def test_sanitize_drops_expected_ids(self) -> None:
        vof = {
            "buyer": {
                "name": "Acme Company (SYNTHETIC)",
                "code_on_document": "C-ACME",
                "customer_id": "C-ACME",
                "erp_partner_ref": "C-ACME",
                "tax_id": "12-8713396",
                "resolved": {"erp_partner_ref": "C-ACME", "erp_partner_id": 42},
            },
            "source": {"from_address": "purchasing@acme.example"},
            "lines": [
                {
                    "line_no": 1,
                    "description": "Wrench",
                    "sku": "TOOL-WRN-10IN",
                    "erp_product_id": 1200,
                    "resolution": {"sku": "TOOL-WRN-10IN", "score": 1.0},
                    "buyer_item_code": "ACME-HW-00412",
                }
            ],
            "_synthetic_metadata": {"is_hard_case": True},
        }
        clean = sanitize_extracted_order(vof)
        assert "code_on_document" not in clean["buyer"]
        assert "resolved" not in clean["buyer"]
        assert "customer_id" not in clean["buyer"]
        assert "erp_partner_ref" not in clean["buyer"]
        assert "_synthetic_metadata" not in clean
        assert "resolution" not in clean["lines"][0]
        assert "sku" not in clean["lines"][0]
        assert "erp_product_id" not in clean["lines"][0]
        assert clean["lines"][0]["buyer_item_code"] == "ACME-HW-00412"
        assert clean["buyer"]["tax_id"] == "12-8713396"

    def test_ignores_code_on_document_customer_id(self, customers: CustomerMatcher) -> None:
        match = customers.resolve(
            {
                "source": {},
                "buyer": {
                    "code_on_document": "C-ACME",
                    "customer_id": "C-ACME",
                    "erp_partner_ref": "C-ACME",
                    "resolved": {
                        "erp_partner_id": 42,
                        "erp_partner_ref": "C-ACME",
                        "method": "MANUAL",
                        "score": 1.0,
                    },
                    "name": "Zeta Unknown GmbH",
                    "tax_id": None,
                },
            }
        )
        assert not match.resolved
        assert match.method == "UNRESOLVED"

    def test_ignores_resolution_and_line_sku(self, items: ItemMatcher) -> None:
        match = items.resolve(
            {
                "line_no": 1,
                "description": "Quantum Flux Capacitor Mk.IX",
                "buyer_item_code": None,
                "seller_item_code": None,
                "gtin": None,
                "sku": "TOOL-WRN-10IN",
                "product_id": 1200,
                "erp_product_id": 1200,
                "resolution": {
                    "sku": "TOOL-WRN-10IN",
                    "erp_product_id": 1200,
                    "method": "MANUAL",
                    "score": 1.0,
                },
            },
            "C-ACME",
        )
        assert match.method == "UNRESOLVED"
        assert match.product is None

    def test_apply_matches_ignores_expected_ids(self, provider: MockReferenceDataProvider) -> None:
        vof = {
            "source": {},
            "buyer": {
                "name": "Zeta Unknown GmbH",
                "tax_id": None,
                "code_on_document": "C-ACME",
                "customer_id": "C-ACME",
                "resolved": {
                    "erp_partner_id": 42,
                    "erp_partner_ref": "C-ACME",
                    "score": 1.0,
                },
            },
            "lines": [
                {
                    "line_no": 1,
                    "description": "Quantum Flux Capacitor Mk.IX",
                    "sku": "TOOL-WRN-10IN",
                    "product_id": 1200,
                    "resolution": {"sku": "TOOL-WRN-10IN", "score": 1.0},
                }
            ],
        }
        apply_matches(vof, provider, overwrite=True)
        buyer_res = vof["buyer"].get("resolved") or {}
        assert not buyer_res.get("erp_partner_ref")
        line_res = vof["lines"][0].get("resolution") or {}
        assert line_res.get("sku") is None


# ---------------------------------------------------------------------------
# Varianti rumorose (seed fisso)
# ---------------------------------------------------------------------------


def _sample_extracted() -> dict:
    return {
        "source": {"from_address": "purchasing@acme.example"},
        "buyer": {
            "name": "Acme Company (SYNTHETIC)",
            "tax_id": "12-8713396",
            "address": dict(ACME_ADDRESS),
            "contact": {"email": "purchasing@acme.example"},
        },
        "lines": [
            {
                "line_no": 1,
                "buyer_item_code": "ACME-HW-00412",
                "seller_item_code": "TOOL-WRN-10IN",
                "gtin": "9999900000009",
                "description": "Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc",
                "uom": "BX",
                "uom_raw": "BX",
                "pack": {"inner_uom": "EA", "inner_qty": 100},
            }
        ],
    }


class TestNoisyVariants:
    def test_seed_is_fixed(self) -> None:
        assert NOISY_EVAL_SEED == 42

    def test_no_tax_id(self) -> None:
        out = apply_variants(_sample_extracted(), ["no_tax_id"], variant_rng(42, "t"))
        assert out["buyer"]["tax_id"] is None

    def test_generic_email(self) -> None:
        out = apply_variants(_sample_extracted(), ["generic_email"], variant_rng(42, "e"))
        domain = out["source"]["from_address"].split("@", 1)[-1]
        assert domain in GENERIC_EMAIL_DOMAINS
        assert domain != "acme.example"

    def test_name_typo_or_abbrev(self) -> None:
        out = apply_variants(_sample_extracted(), ["name_noise"], variant_rng(42, "n"))
        assert out["buyer"]["name"] != "Acme Company (SYNTHETIC)"

    def test_unknown_customer_codes(self) -> None:
        out = apply_variants(_sample_extracted(), ["unknown_codes"], variant_rng(42, "u"))
        assert str(out["lines"][0]["buyer_item_code"]).startswith("ZZ-UNK-")
        assert out["lines"][0]["seller_item_code"] is None
        assert out["lines"][0]["gtin"] is None

    def test_spaced_codes_keep_identity(self) -> None:
        out = apply_variants(_sample_extracted(), ["spaced_codes"], variant_rng(42, "s"))
        spaced = out["lines"][0]["buyer_item_code"]
        assert " " in spaced
        assert normalize_item_code(spaced) == normalize_item_code("ACME-HW-00412")
        assert normalize_sku(out["lines"][0]["seller_item_code"]) == normalize_sku("TOOL-WRN-10IN")

    def test_paraphrased_description_drops_codes(self) -> None:
        out = apply_variants(_sample_extracted(), ["paraphrase"], variant_rng(42, "p"))
        assert out["lines"][0]["description"] != "Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc"
        assert out["lines"][0]["buyer_item_code"] is None
        assert out["lines"][0]["seller_item_code"] is None

    def test_alt_uom(self) -> None:
        out = apply_variants(_sample_extracted(), ["alt_uom"], variant_rng(42, "a"))
        assert out["lines"][0]["uom"] in {"EA", "BOX", "CASE", "PCS"}
        assert out["lines"][0]["uom"] != "BX" or out["lines"][0]["uom_raw"] != "BX"

    def test_hard_case_stacks_customer_noise_and_drops_address(self) -> None:
        rng = variant_rng(42, "hard")
        kinds = select_kinds_for_order(0, hard=True, rng=rng)
        assert "no_tax_id" in kinds
        assert "generic_email" in kinds
        assert "name_noise" in kinds
        assert "drop_address" in kinds
        out = apply_variants(_sample_extracted(), kinds, rng)
        assert out["buyer"]["tax_id"] is None
        assert out["buyer"]["address"] is None

    def test_variants_are_deterministic(self) -> None:
        a = apply_variants(_sample_extracted(), ["name_noise", "paraphrase"], variant_rng(42, "d"))
        b = apply_variants(_sample_extracted(), ["name_noise", "paraphrase"], variant_rng(42, "d"))
        assert a["buyer"]["name"] == b["buyer"]["name"]
        assert a["lines"][0]["description"] == b["lines"][0]["description"]

    def test_spaced_codes_still_match(self, items: ItemMatcher) -> None:
        out = apply_variants(_sample_extracted(), ["spaced_codes"], variant_rng(42, "s"))
        match = items.resolve(out["lines"][0], "C-ACME")
        assert match.product is not None
        assert match.product.sku == "FST-HCS-12-13X2-G5Z-B50"

    def test_unknown_codes_do_not_use_expected_sku(self, items: ItemMatcher) -> None:
        extracted = _sample_extracted()
        extracted["lines"][0]["description"] = "Quantum Flux Capacitor Mk.IX"
        extracted["lines"][0]["sku"] = "TOOL-WRN-10IN"
        extracted["lines"][0]["resolution"] = {"sku": "TOOL-WRN-10IN"}
        out = apply_variants(extracted, ["unknown_codes"], variant_rng(42, "u"))
        match = items.resolve(out["lines"][0], "C-ACME")
        assert match.product is None
