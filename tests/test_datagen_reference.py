"""Provider Datagen, UoM da products.json e casi difficili ITM/UOM/PRC/DUP."""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

import pytest

from synthetic.orders import HARD_CASE_TYPES, assign_hard_cases, carton_conversion
from tests.test_rules import assert_hit, make_vof
from ventureorder.rules import (
    DatagenReferenceDataProvider,
    DecisionRoute,
    HistoricalOrder,
    Severity,
    ValidationEngine,
)

REPO = Path(__file__).resolve().parent.parent
AS_OF = date(2026, 11, 3)
CONFIG = REPO / "config"
PRODUCTS_PATH = REPO / "datagen" / "master" / "products.json"
DATAGEN_UOMS = ("CS", "BX", "RO", "PK", "BG", "RL", "GLL", "DZN")


@pytest.fixture(scope="module")
def products() -> list[dict]:
    with PRODUCTS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def provider() -> DatagenReferenceDataProvider:
    return DatagenReferenceDataProvider.from_datagen()


@pytest.fixture(scope="module")
def engine(provider: DatagenReferenceDataProvider) -> ValidationEngine:
    return ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)


def _product_by_sku(products: list[dict], sku: str) -> dict:
    return next(item for item in products if item["default_code"] == sku)


def _vof_for_sku(
    provider: DatagenReferenceDataProvider,
    sku: str,
    *,
    buyer_item_code: str | None = None,
    gtin: str | None = None,
    mpn: str | None = None,
    uom: str | None = None,
    quantity: float = 2,
    unit_price: float | None = None,
    conversion_factor: float | None = 1,
    erp_uom: str | None = None,
    erp_quantity: float | None = None,
    method: str = "SELLER_CODE",
    score: float = 0.98,
    unresolved: bool = False,
) -> dict:
    product = provider.get_product_by_sku(sku)
    assert product is not None
    customer = provider.get_customer_by_ref("C-ACME")
    assert customer is not None
    price = product.list_price if unit_price is None else unit_price
    line_uom = uom or product.sale_uom
    resolved_uom = erp_uom or product.sale_uom
    qty_erp = erp_quantity if erp_quantity is not None else quantity
    order = make_vof()
    order["buyer"]["resolved"] = {
        "erp_partner_id": customer.erp_partner_id,
        "erp_partner_ref": customer.erp_partner_ref,
        "method": "EMAIL_DOMAIN",
        "score": 0.99,
    }
    order["lines"][0] = {
        "line_no": 1,
        "buyer_item_code": buyer_item_code,
        "seller_item_code": None if unresolved else sku,
        "manufacturer_name": None,
        "manufacturer_part_number": mpn,
        "gtin": gtin,
        "description": product.name,
        "quantity": quantity,
        "uom_raw": line_uom,
        "uom": line_uom,
        "pack": product.pack,
        "unit_price": price,
        "price_uom": line_uom,
        "price_basis_qty": 1,
        "discount_pct": None,
        "line_amount": round(quantity * price, 2),
        "requested_delivery_date": None,
        "notes": None,
        "resolution": {
            "sku": None if unresolved else sku,
            "erp_product_id": None if unresolved else product.erp_product_id,
            "erp_uom": resolved_uom,
            "erp_uom_id": 31,
            "erp_quantity": qty_erp,
            "conversion_factor": conversion_factor,
            "method": "UNRESOLVED" if unresolved else method,
            "score": 0.0 if unresolved else score,
            "candidates": [],
            "erp_list_price": product.list_price,
        },
    }
    amount = order["lines"][0]["line_amount"]
    order["totals"] = {
        "lines_amount_declared": amount,
        "total_amount_declared": amount,
        "lines_amount_computed": amount,
    }
    return order


class TestDatagenReferenceDataProvider:
    def test_loads_master_files(self, provider: DatagenReferenceDataProvider) -> None:
        assert provider.get_customer_by_ref("C-ACME") is not None
        assert provider.get_product_by_sku("PPE-GLV-LAT-6-L-WHI") is not None
        xref = provider.get_xref("C-ACME", "ACME-ABR-3086")
        assert xref is not None
        assert xref.sku == "ABR-COW-6IN-1"

    def test_is_valid_uom_accepts_datagen_units(
        self, provider: DatagenReferenceDataProvider
    ) -> None:
        for code in DATAGEN_UOMS:
            assert provider.is_valid_uom(code), f"{code} deve essere un'UoM valida"
        assert provider.is_valid_uom("ca")
        assert provider.is_valid_uom("DZ")
        assert not provider.is_valid_uom("BANANAS")

    def test_set_valid_uoms_does_not_force_datagen_units(self) -> None:
        from ventureorder.rules import MockReferenceDataProvider

        mock = MockReferenceDataProvider()
        mock.set_valid_uoms({"EA"})
        assert mock.is_valid_uom("EA")
        assert mock.is_valid_uom("PC")
        assert not mock.is_valid_uom("CS")
        assert not mock.is_valid_uom("RL")

    def test_carton_conversions_match_products_json(
        self, provider: DatagenReferenceDataProvider, products: list[dict]
    ) -> None:
        gloves = _product_by_sku(products, "PPE-GLV-LAT-6-L-WHI")
        expected = {(c["from_uom"], c["to_uom"]): float(c["factor"]) for c in gloves["conversions"]}
        assert (
            provider.get_uom_conversion("CS", "BX", "PPE-GLV-LAT-6-L-WHI") == expected[("CS", "BX")]
        )
        assert (
            provider.get_uom_conversion("CS", "EA", "PPE-GLV-LAT-6-L-WHI") == expected[("CS", "EA")]
        )
        wrap = _product_by_sku(products, "PKG-STW-002")
        factor_rl = float(wrap["conversions"][0]["factor"])
        assert wrap["conversions"][0]["to_uom"] == "RL"
        assert provider.get_uom_conversion("CS", "RL", "PKG-STW-002") == factor_rl
        assert provider.get_uom_conversion("CS", "RO", "PKG-STW-002") == factor_rl

    def test_catalog_exposes_product_conversions(self) -> None:
        from synthetic.loaders.datagen import DatagenLoader

        loader = DatagenLoader(REPO / "datagen" / "master")
        catalog = loader.load_catalog()
        gloves = next(item for item in catalog if item["sku"] == "PPE-GLV-LAT-6-L-WHI")
        pairs = {(c["from_uom"], c["to_uom"]): c["factor"] for c in gloves["conversions"]}
        assert pairs[("CS", "BX")] == 10.0
        assert pairs[("CS", "EA")] == 1000.0


class TestHardCaseAssignments:
    def test_new_types_are_in_the_existing_set(self) -> None:
        for code in (
            "UNKNOWN_CUSTOMER_CODE",
            "AMBIGUOUS_CUSTOMER_CODE",
            "UOM_CARTON",
            "PRICE_OUT_OF_TOLERANCE",
            "DUP_PO",
        ):
            assert code in HARD_CASE_TYPES

    def test_assign_hard_cases_covers_all_types(self) -> None:
        rng = random.Random(42)
        configs = assign_hard_cases(150, 0.15, rng=rng)
        assert len(configs) == 150
        present = {code for assigned in configs for code in assigned}
        assert set(HARD_CASE_TYPES) <= present

    def test_carton_conversion_prefers_box(self, products: list[dict]) -> None:
        gloves = {
            "uom": "CS",
            "conversions": _product_by_sku(products, "PPE-GLV-LAT-6-L-WHI")["conversions"],
            "pack": {"inner_count": 10, "inner_uom": "BX"},
        }
        conv = carton_conversion(gloves)
        assert conv == {"from_uom": "CS", "to_uom": "BX", "factor": 10.0}


class TestHardCasesWithDatagenProvider:
    def test_itm_unknown_customer_code(
        self, engine: ValidationEngine, provider: DatagenReferenceDataProvider
    ) -> None:
        order = _vof_for_sku(
            provider,
            "PPE-GLV-LAT-6-L-WHI",
            buyer_item_code="ACME-UNKNOWN-9999",
            unresolved=True,
        )
        result = engine.validate(order)
        assert_hit(result, "ITM-01", Severity.BLOCK)
        assert provider.get_xref("C-ACME", "ACME-UNKNOWN-9999") is None
        assert result.decision == DecisionRoute.REVIEW
        assert result.decision != DecisionRoute.AUTO_POST
        assert result.decision != DecisionRoute.REJECT

    def test_itm_ambiguous_customer_code(
        self, engine: ValidationEngine, provider: DatagenReferenceDataProvider
    ) -> None:
        gloves = provider.get_product_by_sku("PPE-GLV-LAT-6-L-WHI")
        wrap = provider.get_product_by_sku("PKG-STW-002")
        assert gloves is not None and wrap is not None and wrap.gtin
        xref = next(
            record
            for record in (
                provider.get_xref("C-ACME", code)
                for code in ("ACME-ABR-3086", "ACME-JAN-1133", "ACME-SAF-7598")
            )
            if record is not None
        )
        order = _vof_for_sku(
            provider,
            gloves.sku,
            buyer_item_code=xref.customer_item_code,
            gtin=wrap.gtin,
            method="XREF",
            score=1.0,
        )
        result = engine.validate(order)
        assert_hit(result, "ITM-04", Severity.REVIEW)
        assert result.decision == DecisionRoute.REVIEW
        assert result.decision != DecisionRoute.AUTO_POST
        assert result.decision != DecisionRoute.REJECT

    def test_uom_carton_conversion(self, products: list[dict]) -> None:
        provider = DatagenReferenceDataProvider.from_datagen(allowlisted_refs={"C-ACME"})
        engine = ValidationEngine(config_dir=CONFIG, reference_data=provider, as_of=AS_OF)
        customer = provider.get_customer_by_ref("C-ACME")
        assert customer is not None
        assert customer.allowlisted
        factor = provider.get_uom_conversion("CS", "BX", "PPE-GLV-LAT-6-L-WHI")
        assert factor == 10.0
        gloves = _product_by_sku(products, "PPE-GLV-LAT-6-L-WHI")
        expected = {(c["from_uom"], c["to_uom"]): c["factor"] for c in gloves["conversions"]}
        assert factor == expected[("CS", "BX")]
        order = _vof_for_sku(
            provider,
            "PPE-GLV-LAT-6-L-WHI",
            uom="CS",
            quantity=2,
            conversion_factor=factor,
            erp_uom="BX",
            erp_quantity=20,
        )
        order["source"]["from_address"] = f"purchasing@{customer.email_domain}"
        order["buyer"]["contact"]["email"] = f"purchasing@{customer.email_domain}"
        if customer.delivery_partner_ids:
            order["ship_to"]["resolved"]["erp_partner_id"] = customer.delivery_partner_ids[0]
        # Pack documento ≠ catalogo (es. 250/CS vs 100/BX 10BX/CS) → UOM-04 REVIEW.
        order["lines"][0]["pack"] = {"raw": "250/CS", "inner_count": 250, "inner_uom": "EA"}
        result = engine.validate(order)
        assert_hit(result, "UOM-03", Severity.INFO)
        assert_hit(result, "UOM-04", Severity.REVIEW)
        assert not [item for item in result.issues if item.rule_id == "UOM-02"]
        assert result.decision == DecisionRoute.REVIEW
        assert "UOM-04" in result.reasons
        assert "ALLOWLIST" not in result.reasons
        assert "CUS-04" not in result.reasons
        assert result.decision != DecisionRoute.AUTO_POST
        assert result.decision != DecisionRoute.REJECT

    def test_prc_price_out_of_tolerance(
        self, engine: ValidationEngine, provider: DatagenReferenceDataProvider
    ) -> None:
        product = provider.get_product_by_sku("PPE-GLV-LAT-6-L-WHI")
        assert product is not None
        order = _vof_for_sku(
            provider,
            product.sku,
            unit_price=round(product.list_price * 1.15, 2),
        )
        result = engine.validate(order)
        assert_hit(result, "PRC-01", Severity.REVIEW)
        assert result.decision == DecisionRoute.REVIEW
        assert result.decision != DecisionRoute.AUTO_POST
        assert result.decision != DecisionRoute.REJECT

    def test_dup_existing_po(self) -> None:
        seeded = DatagenReferenceDataProvider.from_datagen()
        seeded.add_order(
            HistoricalOrder(
                order_id="ORD-HIST-SYN",
                customer_ref="C-ACME",
                po_number="4500012345",
                po_revision=0,
                status="POSTED",
                sha256="aa" * 32,
                message_id="<dup-po@acme-mfg.example>",
            )
        )
        engine = ValidationEngine(config_dir=CONFIG, reference_data=seeded, as_of=AS_OF)
        result = engine.validate(make_vof())
        assert_hit(result, "DUP-01", Severity.BLOCK)
        assert result.decision == DecisionRoute.REJECT
