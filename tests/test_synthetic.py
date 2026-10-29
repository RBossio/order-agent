"""
Test per validare i dati sintetici generati per VentureOrder.

Esegui con:
    pytest tests/ -v
"""

import json
from pathlib import Path

import jsonschema
import pytest

SYNTHETIC_DIR = Path(__file__).parent.parent / "synthetic"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"
DATA_DIR = SYNTHETIC_DIR / "data"
GT_DIR = SYNTHETIC_DIR / "ground_truth"

EXPECTED_CATALOG_SIZE = 300
EXPECTED_CUSTOMERS = 10
EXPECTED_ORDERS = 150
EXPECTED_HARD_CASE_PCT = 0.15
HARD_CASE_TOLERANCE = 0.02


@pytest.fixture(scope="module")
def schema():
    """Carica lo schema JSON VOF v1."""
    schema_path = SCHEMA_DIR / "venture-order.v1.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def catalog():
    """Carica il catalogo generato."""
    catalog_path = DATA_DIR / "catalog.json"
    if not catalog_path.exists():
        pytest.skip("Catalogo non generato, esegui prima il generatore")
    with open(catalog_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def customers():
    """Carica i clienti generati."""
    customers_path = DATA_DIR / "customers.json"
    if not customers_path.exists():
        pytest.skip("Clienti non generati, esegui prima il generatore")
    with open(customers_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest():
    """Carica il manifest degli ordini."""
    manifest_path = DATA_DIR / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("Manifest non generato, esegui prima il generatore")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ground_truths():
    """Carica tutti i ground truth JSON."""
    if not GT_DIR.exists():
        pytest.skip("Ground truth non generati, esegui prima il generatore")

    gts = []
    for gt_file in sorted(GT_DIR.glob("*.json")):
        with open(gt_file, encoding="utf-8") as f:
            gt = json.load(f)
            gt["_filename"] = gt_file.name
            gts.append(gt)
    return gts


class TestCatalog:
    """Test per il catalogo articoli."""

    def test_catalog_size(self, catalog):
        """Verifica che il catalogo abbia esattamente 300 articoli."""
        assert len(catalog) == EXPECTED_CATALOG_SIZE, \
            f"Catalogo deve avere {EXPECTED_CATALOG_SIZE} articoli, trovati {len(catalog)}"

    def test_catalog_required_fields(self, catalog):
        """Verifica che ogni articolo abbia i campi obbligatori."""
        required_fields = ["sku", "description", "uom", "price", "erp_product_id"]

        for i, item in enumerate(catalog):
            for field in required_fields:
                assert field in item, f"Articolo {i}: campo '{field}' mancante"

    def test_catalog_unique_skus(self, catalog):
        """Verifica che gli SKU siano univoci."""
        skus = [item["sku"] for item in catalog]
        assert len(skus) == len(set(skus)), "SKU duplicati nel catalogo"

    def test_catalog_unique_erp_ids(self, catalog):
        """Verifica che gli ERP ID siano univoci."""
        erp_ids = [item["erp_product_id"] for item in catalog]
        assert len(erp_ids) == len(set(erp_ids)), "ERP ID duplicati nel catalogo"

    def test_catalog_prices_valid(self, catalog):
        """Verifica che i prezzi siano validi."""
        for item in catalog:
            assert item["price"] > 0, f"Prezzo non valido per {item['sku']}"

    def test_catalog_categories(self, catalog):
        """Verifica la distribuzione delle categorie."""
        categories = {}
        for item in catalog:
            cat = item.get("category", "UNKNOWN")
            categories[cat] = categories.get(cat, 0) + 1

        expected_cats = ["FASTENERS", "PPE", "JANSAN_LINERS", "JANSAN_CHEMICALS"]
        for cat in expected_cats:
            assert cat in categories, f"Categoria {cat} non presente nel catalogo"

    def test_catalog_pack_structure(self, catalog):
        """Verifica la struttura dei pack."""
        items_with_pack = [item for item in catalog if item.get("pack")]
        assert len(items_with_pack) > 50, "Troppo pochi articoli con pack"

        for item in items_with_pack:
            pack = item["pack"]
            assert "raw" in pack, f"Pack senza 'raw' per {item['sku']}"
            assert "inner_count" in pack, f"Pack senza 'inner_count' per {item['sku']}"


class TestCustomers:
    """Test per i clienti."""

    def test_customers_count(self, customers):
        """Verifica che ci siano esattamente 10 clienti."""
        assert len(customers) == EXPECTED_CUSTOMERS, \
            f"Devono esserci {EXPECTED_CUSTOMERS} clienti, trovati {len(customers)}"

    def test_customers_required_fields(self, customers):
        """Verifica i campi obbligatori dei clienti."""
        required_fields = ["customer_id", "name", "erp_partner_id", "order_style"]

        for customer in customers:
            for field in required_fields:
                assert field in customer, f"Cliente {customer.get('customer_id')}: campo '{field}' mancante"

    def test_customers_unique_ids(self, customers):
        """Verifica che gli ID cliente siano univoci."""
        ids = [c["customer_id"] for c in customers]
        assert len(ids) == len(set(ids)), "ID cliente duplicati"

    def test_customers_synthetic_names(self, customers):
        """Verifica che i nomi contengano 'SYNTHETIC' per identificarli come fittizi."""
        for customer in customers:
            assert "SYNTHETIC" in customer["name"], \
                f"Nome cliente {customer['customer_id']} non contiene 'SYNTHETIC'"

    def test_customers_order_styles(self, customers):
        """Verifica che ogni cliente abbia uno stile d'ordine."""
        for customer in customers:
            style = customer["order_style"]
            assert "format_preference" in style
            assert "po_prefix" in style
            assert "date_format" in style
            assert len(style["format_preference"]) > 0

    def test_customers_with_xref(self, customers):
        """Verifica che alcuni clienti abbiano cross-reference."""
        customers_with_xref = [c for c in customers if len(c.get("xref", [])) > 0]
        assert len(customers_with_xref) >= 5, \
            "Almeno 5 clienti devono avere codici articolo propri (xref)"

    def test_customers_ship_to(self, customers):
        """Verifica che ogni cliente abbia almeno un indirizzo di spedizione."""
        for customer in customers:
            assert "ship_to" in customer
            assert len(customer["ship_to"]) >= 1, \
                f"Cliente {customer['customer_id']} senza indirizzi di spedizione"


class TestManifest:
    """Test per il manifest degli ordini."""

    def test_manifest_structure(self, manifest):
        """Verifica la struttura del manifest."""
        required_fields = [
            "generated_at", "seed", "total_orders", "hard_cases",
            "hard_case_percentage", "format_distribution", "orders"
        ]
        for field in required_fields:
            assert field in manifest, f"Campo '{field}' mancante nel manifest"

    def test_manifest_order_count(self, manifest):
        """Verifica il conteggio ordini nel manifest."""
        assert manifest["total_orders"] == EXPECTED_ORDERS, \
            f"Manifest indica {manifest['total_orders']} ordini, attesi {EXPECTED_ORDERS}"
        assert len(manifest["orders"]) == EXPECTED_ORDERS

    def test_manifest_hard_case_percentage(self, manifest):
        """Verifica la percentuale di casi difficili."""
        pct = manifest["hard_cases"] / manifest["total_orders"]
        assert abs(pct - EXPECTED_HARD_CASE_PCT) <= HARD_CASE_TOLERANCE, \
            f"Percentuale casi difficili {pct:.2%}, attesa {EXPECTED_HARD_CASE_PCT:.0%} ± {HARD_CASE_TOLERANCE:.0%}"

    def test_manifest_format_distribution(self, manifest):
        """Verifica la distribuzione dei formati."""
        dist = manifest["format_distribution"]
        total = sum(dist.values())
        assert total == EXPECTED_ORDERS, \
            f"Somma formati {total} diversa da ordini totali {EXPECTED_ORDERS}"

        for fmt in ["PDF", "XLSX", "EML"]:
            assert fmt in dist, f"Formato {fmt} mancante nella distribuzione"
            assert dist[fmt] >= 30, f"Troppo pochi ordini in formato {fmt}"


class TestGroundTruth:
    """Test per i ground truth JSON."""

    def test_ground_truth_count(self, ground_truths):
        """Verifica il numero di ground truth."""
        assert len(ground_truths) == EXPECTED_ORDERS, \
            f"Ground truth: {len(ground_truths)}, attesi {EXPECTED_ORDERS}"

    def test_ground_truth_schema_validation(self, ground_truths, schema):
        """Valida tutti i ground truth contro lo schema VOF v1."""
        validator = jsonschema.Draft202012Validator(schema)

        errors = []
        for gt in ground_truths:
            gt_clean = {k: v for k, v in gt.items() if not k.startswith("_")}

            validation_errors = list(validator.iter_errors(gt_clean))
            if validation_errors:
                errors.append({
                    "file": gt.get("_filename", "unknown"),
                    "errors": [str(e.message)[:100] for e in validation_errors[:3]]
                })

        if errors:
            error_summary = "\n".join(
                f"  - {e['file']}: {e['errors'][0]}"
                for e in errors[:10]
            )
            pytest.fail(f"Validazione schema fallita per {len(errors)} file:\n{error_summary}")

    def test_ground_truth_required_fields(self, ground_truths):
        """Verifica i campi obbligatori nei ground truth."""
        required_fields = [
            "schema_version", "order_id", "tenant_id", "document_type",
            "status", "source", "buyer", "header", "lines"
        ]

        for gt in ground_truths:
            for field in required_fields:
                assert field in gt, f"Campo '{field}' mancante in {gt.get('_filename')}"

    def test_ground_truth_schema_version(self, ground_truths):
        """Verifica la versione dello schema."""
        for gt in ground_truths:
            assert gt["schema_version"] == "1.0", \
                f"Versione schema non valida in {gt.get('_filename')}"

    def test_ground_truth_unique_order_ids(self, ground_truths):
        """Verifica che gli order_id siano univoci (UUID)."""
        order_ids = [gt["order_id"] for gt in ground_truths]
        assert len(order_ids) == len(set(order_ids)), "Order ID duplicati"

    def test_ground_truth_lines_not_empty(self, ground_truths):
        """Verifica che ogni ordine abbia almeno una riga."""
        for gt in ground_truths:
            assert len(gt["lines"]) >= 1, \
                f"Ordine senza righe in {gt.get('_filename')}"

    def test_ground_truth_line_structure(self, ground_truths):
        """Verifica la struttura delle righe d'ordine."""
        required_line_fields = ["line_no", "description", "quantity", "uom_raw"]

        for gt in ground_truths:
            for line in gt["lines"]:
                for field in required_line_fields:
                    assert field in line, \
                        f"Campo '{field}' mancante in riga {line.get('line_no')} di {gt.get('_filename')}"


class TestHardCases:
    """Test per i casi difficili."""

    def test_hard_cases_count(self, ground_truths):
        """Verifica il numero di casi difficili."""
        hard_cases = [
            gt for gt in ground_truths
            if gt.get("_synthetic_metadata", {}).get("is_hard_case")
        ]

        pct = len(hard_cases) / len(ground_truths)
        assert abs(pct - EXPECTED_HARD_CASE_PCT) <= HARD_CASE_TOLERANCE, \
            f"Percentuale casi difficili {pct:.2%}, attesa {EXPECTED_HARD_CASE_PCT:.0%}"

    def test_hard_cases_have_types(self, ground_truths):
        """Verifica che i casi difficili abbiano tipi specificati."""
        hard_cases = [
            gt for gt in ground_truths
            if gt.get("_synthetic_metadata", {}).get("is_hard_case")
        ]

        for gt in hard_cases:
            types = gt.get("_synthetic_metadata", {}).get("hard_case_types", [])
            assert len(types) > 0, \
                f"Caso difficile senza tipi in {gt.get('_filename')}"

    def test_hard_case_types_variety(self, ground_truths):
        """Verifica che ci siano diversi tipi di casi difficili."""
        all_types = set()
        for gt in ground_truths:
            types = gt.get("_synthetic_metadata", {}).get("hard_case_types", [])
            all_types.update(types)

        assert len(all_types) >= 8, \
            f"Troppo pochi tipi di casi difficili ({len(all_types)}), attesi almeno 8"

    def test_validation_issues_for_blocking_cases(self, ground_truths):
        """Verifica che i casi con campi mancanti abbiano issue di validazione."""
        blocking_types = {"MISSING_PO_NUMBER", "MISSING_QTY"}

        for gt in ground_truths:
            types = set(gt.get("_synthetic_metadata", {}).get("hard_case_types", []))
            if types & blocking_types:
                validation = gt.get("validation", {})
                issues = validation.get("issues", [])
                blocking_issues = [i for i in issues if i.get("severity") == "BLOCK"]
                assert len(blocking_issues) > 0, \
                    f"Caso con campi mancanti senza issue BLOCK in {gt.get('_filename')}"


class TestDocuments:
    """Test per i documenti generati."""

    def test_pdf_files_exist(self, manifest):
        """Verifica che i file PDF esistano."""
        pdf_count = manifest["format_distribution"]["PDF"]
        pdf_dir = SYNTHETIC_DIR / "documents" / "pdf"

        if pdf_dir.exists():
            actual_pdfs = list(pdf_dir.glob("*.pdf"))
            assert len(actual_pdfs) == pdf_count, \
                f"File PDF: {len(actual_pdfs)}, attesi {pdf_count}"

    def test_xlsx_files_exist(self, manifest):
        """Verifica che i file XLSX esistano."""
        xlsx_count = manifest["format_distribution"]["XLSX"]
        xlsx_dir = SYNTHETIC_DIR / "documents" / "xlsx"

        if xlsx_dir.exists():
            actual_xlsx = list(xlsx_dir.glob("*.xlsx"))
            assert len(actual_xlsx) >= xlsx_count - 5, \
                f"File XLSX: {len(actual_xlsx)}, attesi circa {xlsx_count}"

    def test_eml_files_exist(self, manifest):
        """Verifica che i file EML esistano."""
        eml_count = manifest["format_distribution"]["EML"]
        eml_dir = SYNTHETIC_DIR / "documents" / "eml"

        if eml_dir.exists():
            actual_eml = list(eml_dir.glob("*.eml"))
            assert len(actual_eml) == eml_count, \
                f"File EML: {len(actual_eml)}, attesi {eml_count}"


class TestReproducibility:
    """Test per la riproducibilità con seed fisso."""

    def test_seed_is_set(self):
        """Verifica che il seed sia definito."""
        from synthetic import SEED
        assert SEED is not None
        assert isinstance(SEED, int)

    def test_catalog_deterministic(self, catalog):
        """Verifica che il catalogo sia deterministico."""
        from synthetic.catalog import generate_catalog

        catalog2 = generate_catalog()

        assert len(catalog) == len(catalog2)
        assert catalog[0]["sku"] == catalog2[0]["sku"]
        assert catalog[-1]["sku"] == catalog2[-1]["sku"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
