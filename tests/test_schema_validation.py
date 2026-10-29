"""Test per la validazione dello schema VOF v1."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "venture-order.v1.schema.json"
EXAMPLE_PATH = REPO_ROOT / "schema" / "example-mro.json"
SAMPLES_DIR = REPO_ROOT / "samples"


class TestSchemaValidation:
    """Test suite per la validazione dello schema JSON."""

    @pytest.fixture
    def schema(self) -> dict:
        """Load the VOF v1 schema."""
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def example(self) -> dict:
        """Load the example MRO order."""
        with open(EXAMPLE_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_schema_is_valid_json(self, schema: dict) -> None:
        """Lo schema JSON deve essere valido."""
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        assert schema.get("title") is not None

    def test_example_validates_against_schema(self, schema: dict, example: dict) -> None:
        """L'esempio MRO deve validare contro lo schema VOF v1."""
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = list(validator.iter_errors(example))

        if errors:
            error_messages = [f"{err.message} at {list(err.absolute_path)}" for err in errors]
            pytest.fail("Schema validation failed:\n" + "\n".join(error_messages))

    def test_example_has_required_fields(self, example: dict) -> None:
        """L'esempio deve avere tutti i campi obbligatori."""
        required_fields = [
            "schema_version",
            "order_id",
            "tenant_id",
            "document_type",
            "source",
            "buyer",
            "header",
            "lines",
            "status",
        ]
        for field in required_fields:
            assert field in example, f"Campo obbligatorio mancante: {field}"

    def test_example_schema_version_is_1_0(self, example: dict) -> None:
        """La versione dello schema deve essere 1.0."""
        assert example["schema_version"] == "1.0"

    def test_example_has_valid_lines(self, example: dict) -> None:
        """L'esempio deve avere almeno una riga valida."""
        assert len(example["lines"]) > 0
        for idx, line in enumerate(example["lines"]):
            assert "line_no" in line, f"Riga {idx}: manca line_no"
            assert "description" in line, f"Riga {idx}: manca description"
            assert "quantity" in line, f"Riga {idx}: manca quantity"
            assert line["quantity"] > 0, f"Riga {idx}: quantity deve essere > 0"


class TestSampleGenerators:
    """Test suite per i generatori di sample."""

    def test_gen_samples_runs_successfully(self) -> None:
        """gen_samples.py deve eseguire senza errori."""
        result = subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_samples.py")],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
        )
        assert result.returncode == 0, f"gen_samples.py failed: {result.stderr}"
        assert "ok" in result.stdout

    def test_gen_peppol_runs_successfully(self) -> None:
        """gen_peppol.py deve eseguire senza errori."""
        result = subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_peppol.py")],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
        )
        assert result.returncode == 0, f"gen_peppol.py failed: {result.stderr}"
        assert "ok total" in result.stdout

    def test_gen_samples_creates_x12_file(self) -> None:
        """gen_samples.py deve creare il file X12 850."""
        subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_samples.py")],
            capture_output=True,
            cwd=SAMPLES_DIR,
        )
        x12_file = SAMPLES_DIR / "sample.x12.850.txt"
        assert x12_file.exists(), "File X12 850 non creato"
        content = x12_file.read_text()
        assert "ISA*" in content
        assert "ST*850*" in content

    def test_gen_samples_creates_edifact_file(self) -> None:
        """gen_samples.py deve creare il file EDIFACT ORDERS."""
        subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_samples.py")],
            capture_output=True,
            cwd=SAMPLES_DIR,
        )
        edifact_file = SAMPLES_DIR / "sample.edifact.orders.txt"
        assert edifact_file.exists(), "File EDIFACT ORDERS non creato"
        content = edifact_file.read_text()
        assert "UNA:+.? '" in content
        assert "UNH+1+ORDERS" in content

    def test_gen_samples_creates_csv_file(self) -> None:
        """gen_samples.py deve creare il file CSV."""
        subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_samples.py")],
            capture_output=True,
            cwd=SAMPLES_DIR,
        )
        csv_file = SAMPLES_DIR / "sample.generic.csv"
        assert csv_file.exists(), "File CSV non creato"
        content = csv_file.read_text()
        assert "vo_order_id" in content
        assert "po_number" in content

    def test_gen_peppol_creates_xml_file(self) -> None:
        """gen_peppol.py deve creare il file Peppol Order XML."""
        subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_peppol.py")],
            capture_output=True,
            cwd=SAMPLES_DIR,
        )
        xml_file = SAMPLES_DIR / "sample.peppol-order.xml"
        assert xml_file.exists(), "File Peppol Order XML non creato"
        content = xml_file.read_text()
        assert "Order" in content
        assert "urn:oasis:names:specification:ubl:schema:xsd:Order-2" in content

    def test_gen_samples_with_missing_file_returns_error(self) -> None:
        """gen_samples.py deve restituire errore se il file non esiste."""
        result = subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_samples.py"), "/nonexistent/file.json"],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
        )
        assert result.returncode == 1
        assert "non trovato" in result.stderr

    def test_gen_peppol_with_missing_file_returns_error(self) -> None:
        """gen_peppol.py deve restituire errore se il file non esiste."""
        result = subprocess.run(
            [sys.executable, str(SAMPLES_DIR / "gen_peppol.py"), "/nonexistent/file.json"],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
        )
        assert result.returncode == 1
        assert "non trovato" in result.stderr
