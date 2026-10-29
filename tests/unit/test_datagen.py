"""Test unitari per datagen/generate_master_data.py."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import random

from datagen.generate_master_data import (
    generate_customers,
    generate_products,
    generate_xref,
    gtin13_check_digit,
    parse_pack_description,
)


class TestGtin:
    """Test per il calcolo del check digit GTIN."""

    def test_gtin13_check_digit_valid(self):
        """Verifica che il check digit sia calcolato correttamente."""
        assert gtin13_check_digit("978030640615") == "9780306406157"
        assert gtin13_check_digit("400638133393") == "4006381333931"

    def test_gtin13_all_zeros(self):
        """Verifica check digit per numeri tutti zero."""
        result = gtin13_check_digit("000000000000")
        assert len(result) == 13
        assert result[-1] == "0"


class TestPackDescriptionParser:
    """Test per parse_pack_description."""

    def test_gallon_pack(self):
        """Test formato '4/1GAL' - 4 galloni per case."""
        convs = parse_pack_description("4/1GAL", "CS")
        assert len(convs) == 1
        assert convs[0].from_uom == "CS"
        assert convs[0].to_uom == "GLL"
        assert convs[0].factor == 4.0

    def test_multi_level_pack(self):
        """Test formato '100/BX 10BX/CS' - multi-livello."""
        convs = parse_pack_description("100/BX 10BX/CS", "CS")
        conv_map = {(c.from_uom, c.to_uom): c.factor for c in convs}

        assert ("BX", "EA") in conv_map
        assert conv_map[("BX", "EA")] == 100.0

        assert ("CS", "BX") in conv_map
        assert conv_map[("CS", "BX")] == 10.0

        assert ("CS", "EA") in conv_map
        assert conv_map[("CS", "EA")] == 1000.0

    def test_simple_box(self):
        """Test formato 'BX/50' - 50 EA per box."""
        convs = parse_pack_description("BX/50", "BX")
        assert len(convs) == 1
        assert convs[0].from_uom == "BX"
        assert convs[0].to_uom == "EA"
        assert convs[0].factor == 50.0

    def test_simple_count(self):
        """Test formato '100/CS' - 100 EA per case."""
        convs = parse_pack_description("100/CS", "CS")
        assert len(convs) == 1
        assert convs[0].from_uom == "CS"
        assert convs[0].to_uom == "EA"
        assert convs[0].factor == 100.0

    def test_roll_pack(self):
        """Test formato '12RL/CS' - 12 rotoli per case."""
        convs = parse_pack_description("12RL/CS", "CS")
        conv_map = {(c.from_uom, c.to_uom): c.factor for c in convs}
        assert ("CS", "RL") in conv_map
        assert conv_map[("CS", "RL")] == 12.0

    def test_pair_pack(self):
        """Test formato '200PR/BX' - 200 paia per box."""
        convs = parse_pack_description("200PR/BX", "BX")
        conv_map = {(c.from_uom, c.to_uom): c.factor for c in convs}
        assert ("BX", "PR") in conv_map
        assert conv_map[("BX", "PR")] == 200.0

    def test_none_pack(self):
        """Test con pack_description None."""
        convs = parse_pack_description(None, "EA")
        assert convs == []


class TestProductConversions:
    """Test per la coerenza delle conversioni prodotto."""

    def test_all_products_have_coherent_conversions(self):
        """Verifica che ogni prodotto abbia conversioni coerenti con pack_description."""
        rng = random.Random(42)
        products = generate_products(rng)

        errors = []
        for prod in products:
            if prod.pack_description:
                expected_convs = parse_pack_description(
                    prod.pack_description, prod.sale_uom
                )
                expected_map = {
                    (c.from_uom, c.to_uom): c.factor for c in expected_convs
                }
                actual_map = {
                    (c.from_uom, c.to_uom): c.factor for c in prod.conversions
                }

                for key, expected_factor in expected_map.items():
                    if key not in actual_map:
                        errors.append(
                            f"{prod.default_code}: manca conversione {key}"
                        )
                    elif actual_map[key] != expected_factor:
                        errors.append(
                            f"{prod.default_code}: conversione {key} "
                            f"attesa {expected_factor}, trovata {actual_map[key]}"
                        )

        assert not errors, "Prodotti con conversioni incoerenti:\n" + "\n".join(errors)


class TestCustomerXref:
    """Test per l'univocità dei codici cliente."""

    def test_no_duplicate_customer_codes(self):
        """Verifica che ogni cliente non abbia codici articolo duplicati."""
        rng = random.Random(42)
        products = generate_products(rng)
        customers = generate_customers(rng)
        xrefs = generate_xref(rng, products, customers)

        duplicates = []
        customer_codes: dict[str, set[str]] = {}

        for xref in xrefs:
            if xref.customer_ref not in customer_codes:
                customer_codes[xref.customer_ref] = set()

            if xref.customer_item_code in customer_codes[xref.customer_ref]:
                duplicates.append(
                    f"{xref.customer_ref}/{xref.customer_item_code} -> {xref.product_sku}"
                )
            customer_codes[xref.customer_ref].add(xref.customer_item_code)

        assert not duplicates, (
            f"Trovati {len(duplicates)} codici cliente duplicati:\n"
            + "\n".join(duplicates[:10])
        )


class TestGeneratedData:
    """Test per i dati generati."""

    def test_generates_300_products(self):
        """Verifica che vengano generati 300 prodotti."""
        rng = random.Random(42)
        products = generate_products(rng)
        assert len(products) == 300

    def test_generates_10_customers(self):
        """Verifica che vengano generati 10 clienti."""
        rng = random.Random(42)
        customers = generate_customers(rng)
        assert len(customers) == 10

    def test_all_products_have_valid_gtin(self):
        """Verifica che tutti i GTIN siano validi."""
        rng = random.Random(42)
        products = generate_products(rng)

        for prod in products:
            gtin = prod.gtin
            assert len(gtin) == 13, f"{prod.default_code}: GTIN non è 13 cifre"

            digits_12 = gtin[:12]
            expected = gtin13_check_digit(digits_12)
            assert gtin == expected, (
                f"{prod.default_code}: check digit GTIN invalido "
                f"({gtin} != {expected})"
            )

    def test_deterministic_generation(self):
        """Verifica che la generazione sia deterministica."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)

        products1 = generate_products(rng1)
        products2 = generate_products(rng2)

        assert len(products1) == len(products2)
        for p1, p2 in zip(products1, products2, strict=False):
            assert p1.default_code == p2.default_code
            assert p1.name == p2.name
            assert p1.list_price == p2.list_price


class TestMasterDataFiles:
    """Test per i file generati in datagen/master/."""

    @pytest.fixture
    def master_dir(self):
        """Path della directory master."""
        return Path(__file__).parent.parent.parent / "datagen" / "master"

    def test_products_json_exists(self, master_dir):
        """Verifica che products.json esista."""
        if not master_dir.exists():
            pytest.skip("datagen/master non esiste, eseguire generate_master_data.py")
        assert (master_dir / "products.json").exists()

    def test_products_json_valid(self, master_dir):
        """Verifica che products.json sia JSON valido con 300 prodotti."""
        products_file = master_dir / "products.json"
        if not products_file.exists():
            pytest.skip("products.json non esiste")

        with open(products_file) as f:
            products = json.load(f)

        assert isinstance(products, list)
        assert len(products) == 300

    def test_customers_json_valid(self, master_dir):
        """Verifica che customers.json sia JSON valido con 10 clienti."""
        customers_file = master_dir / "customers.json"
        if not customers_file.exists():
            pytest.skip("customers.json non esiste")

        with open(customers_file) as f:
            customers = json.load(f)

        assert isinstance(customers, list)
        assert len(customers) == 10

    def test_xref_no_duplicates(self, master_dir):
        """Verifica che customer_xref.json non abbia duplicati."""
        xref_file = master_dir / "customer_xref.json"
        if not xref_file.exists():
            pytest.skip("customer_xref.json non esiste")

        with open(xref_file) as f:
            xrefs = json.load(f)

        seen: dict[str, set[str]] = {}
        duplicates = []

        for xref in xrefs:
            cust = xref["customer_ref"]
            code = xref["customer_item_code"]

            if cust not in seen:
                seen[cust] = set()

            if code in seen[cust]:
                duplicates.append(f"{cust}/{code}")
            seen[cust].add(code)

        assert not duplicates, f"Duplicati trovati: {duplicates[:10]}"
