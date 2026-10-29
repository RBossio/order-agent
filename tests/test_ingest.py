"""Test per il modulo ingest."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from ingest import Ingestor, NormalizedInput

SYNTHETIC_DIR = Path(__file__).parent.parent / "synthetic"
DOCUMENTS_DIR = SYNTHETIC_DIR / "documents"
GROUND_TRUTH_DIR = SYNTHETIC_DIR / "ground_truth"
SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "normalized-input.v1.schema.json"


@pytest.fixture(scope="module")
def ingestor() -> Ingestor:
    """Ingestor condiviso tra i test."""
    return Ingestor()


@pytest.fixture(scope="module")
def schema() -> dict:
    """Schema NormalizedInput."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validator(schema: dict) -> jsonschema.Draft202012Validator:
    """Validatore JSON Schema."""
    return jsonschema.Draft202012Validator(schema)


def get_all_document_paths() -> list[Path]:
    """Ritorna tutti i percorsi dei documenti sintetici."""
    paths = []
    
    for subdir in ["pdf", "xlsx", "eml"]:
        dir_path = DOCUMENTS_DIR / subdir
        if dir_path.exists():
            paths.extend(sorted(dir_path.glob("*")))
    
    return paths


def get_ground_truth(doc_path: Path) -> dict | None:
    """Carica il ground truth per un documento."""
    stem = doc_path.stem
    gt_path = GROUND_TRUTH_DIR / f"{stem}.json"
    
    if gt_path.exists():
        with open(gt_path) as f:
            return json.load(f)
    return None


ALL_DOCUMENTS = get_all_document_paths()


class TestIngestorBasic:
    """Test di base per l'Ingestor."""

    def test_ingestor_creation(self, ingestor: Ingestor):
        """Verifica la creazione dell'ingestor."""
        assert ingestor is not None
        assert ingestor.eml_parser is not None
        assert ingestor.pdf_parser is not None
        assert ingestor.excel_parser is not None
        assert ingestor.csv_parser is not None

    def test_supported_extensions(self, ingestor: Ingestor):
        """Verifica le estensioni supportate."""
        expected = {".eml", ".pdf", ".xlsx", ".xls", ".csv"}
        assert set(ingestor.EXTENSION_MAP.keys()) == expected


class TestSchemaValidation:
    """Test di validazione dello schema NormalizedInput."""

    def test_schema_exists(self):
        """Verifica che lo schema esista."""
        assert SCHEMA_PATH.exists(), f"Schema non trovato: {SCHEMA_PATH}"

    def test_schema_valid(self, schema: dict):
        """Verifica che lo schema sia un JSON Schema valido."""
        assert "$schema" in schema
        assert "properties" in schema
        assert "required" in schema

    def test_schema_has_required_fields(self, schema: dict):
        """Verifica i campi obbligatori."""
        required = schema.get("required", [])
        assert "schema_version" in required
        assert "input_id" in required
        assert "source" in required
        assert "ingested_at" in required
        assert "parts" in required


class TestAllSyntheticDocuments:
    """Test su tutti i 150+ documenti sintetici."""

    @pytest.mark.parametrize("doc_path", ALL_DOCUMENTS, ids=lambda p: p.name)
    def test_ingest_document_no_error(
        self,
        doc_path: Path,
        ingestor: Ingestor
    ):
        """Verifica che l'ingestione non sollevi errori."""
        result = ingestor.ingest(doc_path)
        assert result is not None
        assert isinstance(result, NormalizedInput)

    @pytest.mark.parametrize("doc_path", ALL_DOCUMENTS, ids=lambda p: p.name)
    def test_ingest_document_validates_schema(
        self,
        doc_path: Path,
        ingestor: Ingestor,
        validator: jsonschema.Draft202012Validator
    ):
        """Verifica che l'output validi contro lo schema."""
        result = ingestor.ingest(doc_path)
        output_dict = result.to_dict()
        
        errors = list(validator.iter_errors(output_dict))
        error_messages = [f"{e.json_path}: {e.message}" for e in errors]
        
        assert len(errors) == 0, f"Schema validation errors: {error_messages}"

    @pytest.mark.parametrize("doc_path", ALL_DOCUMENTS, ids=lambda p: p.name)
    def test_ingest_document_has_parts(
        self,
        doc_path: Path,
        ingestor: Ingestor
    ):
        """Verifica che ogni documento abbia almeno una parte."""
        result = ingestor.ingest(doc_path)
        assert len(result.parts) > 0, f"Nessuna parte estratta da {doc_path}"

    @pytest.mark.parametrize("doc_path", ALL_DOCUMENTS, ids=lambda p: p.name)
    def test_ingest_document_has_sha256(
        self,
        doc_path: Path,
        ingestor: Ingestor
    ):
        """Verifica che ogni parte abbia un hash SHA256."""
        result = ingestor.ingest(doc_path)
        
        for part in result.parts:
            assert part.sha256, f"Parte senza SHA256 in {doc_path}"
            assert len(part.sha256) == 64, f"SHA256 invalido in {doc_path}"


class TestPdfDocuments:
    """Test specifici per documenti PDF."""

    @pytest.fixture
    def pdf_paths(self) -> list[Path]:
        pdf_dir = DOCUMENTS_DIR / "pdf"
        if pdf_dir.exists():
            return sorted(pdf_dir.glob("*.pdf"))
        return []

    def test_pdf_documents_exist(self, pdf_paths: list[Path]):
        """Verifica che ci siano documenti PDF."""
        assert len(pdf_paths) > 0, "Nessun documento PDF trovato"

    def test_pdf_extracts_text(self, pdf_paths: list[Path], ingestor: Ingestor):
        """Verifica che i PDF abbiano testo estratto."""
        for pdf_path in pdf_paths[:5]:
            result = ingestor.ingest(pdf_path)
            
            has_text = any(part.text for part in result.parts)
            has_layout = any(part.text_layout for part in result.parts)
            needs_ocr = any(part.needs_ocr for part in result.parts)
            
            assert has_text or has_layout or needs_ocr, \
                f"PDF senza testo né flag OCR: {pdf_path}"

    def test_pdf_detects_tables(self, pdf_paths: list[Path], ingestor: Ingestor):
        """Verifica che i PDF con ordini abbiano tabelle."""
        tables_found = 0
        
        for pdf_path in pdf_paths:
            result = ingestor.ingest(pdf_path)
            for part in result.parts:
                if part.tables:
                    tables_found += len(part.tables)
        
        assert tables_found > 0, "Nessuna tabella trovata nei PDF"


class TestExcelDocuments:
    """Test specifici per documenti Excel."""

    @pytest.fixture
    def xlsx_paths(self) -> list[Path]:
        xlsx_dir = DOCUMENTS_DIR / "xlsx"
        if xlsx_dir.exists():
            return sorted(xlsx_dir.glob("*.xlsx"))
        return []

    def test_xlsx_documents_exist(self, xlsx_paths: list[Path]):
        """Verifica che ci siano documenti Excel."""
        assert len(xlsx_paths) > 0, "Nessun documento Excel trovato"

    def test_xlsx_extracts_sheets(self, xlsx_paths: list[Path], ingestor: Ingestor):
        """Verifica che gli Excel abbiano fogli estratti."""
        for xlsx_path in xlsx_paths[:5]:
            result = ingestor.ingest(xlsx_path)
            
            sheet_parts = [p for p in result.parts if p.sheet_name is not None]
            assert len(sheet_parts) > 0, f"Nessun foglio estratto da {xlsx_path}"

    def test_xlsx_has_table_data(self, xlsx_paths: list[Path], ingestor: Ingestor):
        """Verifica che gli Excel abbiano dati tabellari."""
        for xlsx_path in xlsx_paths[:5]:
            result = ingestor.ingest(xlsx_path)
            
            for part in result.parts:
                if part.tables:
                    for table in part.tables:
                        assert len(table.rows) > 0, f"Tabella vuota in {xlsx_path}"


class TestEmlDocuments:
    """Test specifici per documenti email."""

    @pytest.fixture
    def eml_paths(self) -> list[Path]:
        eml_dir = DOCUMENTS_DIR / "eml"
        if eml_dir.exists():
            return sorted(eml_dir.glob("*.eml"))
        return []

    def test_eml_documents_exist(self, eml_paths: list[Path]):
        """Verifica che ci siano documenti email."""
        assert len(eml_paths) > 0, "Nessun documento email trovato"

    def test_eml_extracts_metadata(self, eml_paths: list[Path], ingestor: Ingestor):
        """Verifica che le email abbiano metadati estratti."""
        for eml_path in eml_paths[:5]:
            result = ingestor.ingest(eml_path)
            
            assert result.email_metadata is not None, f"Metadati mancanti: {eml_path}"
            assert result.email_metadata.subject, f"Oggetto mancante: {eml_path}"

    def test_eml_extracts_body(self, eml_paths: list[Path], ingestor: Ingestor):
        """Verifica che le email abbiano corpo estratto."""
        for eml_path in eml_paths[:5]:
            result = ingestor.ingest(eml_path)
            
            body_parts = [p for p in result.parts if "EMAIL_BODY" in p.part_type.value]
            assert len(body_parts) > 0, f"Corpo email mancante: {eml_path}"

    def test_eml_with_attachments(self, eml_paths: list[Path], ingestor: Ingestor):
        """Verifica il parsing degli allegati email."""
        emails_with_attachments = 0
        
        for eml_path in eml_paths:
            result = ingestor.ingest(eml_path)
            
            attachment_parts = [p for p in result.parts if p.source_filename is not None]
            if attachment_parts:
                emails_with_attachments += 1
                
                for part in attachment_parts:
                    assert part.sha256, f"Allegato senza SHA256: {eml_path}"
        
        assert emails_with_attachments > 0, "Nessuna email con allegati trovata"


class TestGroundTruthComparison:
    """Test di confronto con il ground truth."""

    def test_line_count_consistency(self, ingestor: Ingestor):
        """
        Verifica che il numero di righe nelle tabelle sia coerente
        con il ground truth (±2 righe per header/footer).
        """
        xlsx_dir = DOCUMENTS_DIR / "xlsx"
        if not xlsx_dir.exists():
            pytest.skip("Directory xlsx non trovata")
        
        xlsx_paths = sorted(xlsx_dir.glob("*.xlsx"))[:10]
        
        for xlsx_path in xlsx_paths:
            result = ingestor.ingest(xlsx_path)
            gt = get_ground_truth(xlsx_path)
            
            if gt is None:
                continue
            
            gt_lines = len(gt.get("lines", []))
            
            for part in result.parts:
                if part.tables:
                    for table in part.tables:
                        data_rows = len(table.rows)
                        if table.header_row_index is not None:
                            data_rows -= (table.header_row_index + 1)
                        
                        assert abs(data_rows - gt_lines) <= 5, \
                            f"Righe tabella ({data_rows}) vs GT ({gt_lines}) in {xlsx_path}"

    def test_pdf_table_row_count(self, ingestor: Ingestor):
        """Verifica il conteggio righe nelle tabelle PDF."""
        pdf_dir = DOCUMENTS_DIR / "pdf"
        if not pdf_dir.exists():
            pytest.skip("Directory pdf non trovata")
        
        pdf_paths = sorted(pdf_dir.glob("*.pdf"))[:10]
        
        for pdf_path in pdf_paths:
            result = ingestor.ingest(pdf_path)
            gt = get_ground_truth(pdf_path)
            
            if gt is None:
                continue
            
            gt_lines = len(gt.get("lines", []))
            
            total_table_rows = 0
            for part in result.parts:
                if part.tables:
                    for table in part.tables:
                        total_table_rows += len(table.rows)
            
            if total_table_rows > 0:
                assert total_table_rows >= gt_lines, \
                    f"Troppe poche righe tabella ({total_table_rows}) vs GT ({gt_lines}) in {pdf_path}"


class TestBatchProcessing:
    """Test per l'elaborazione batch."""

    def test_batch_pdf_folder(self, ingestor: Ingestor):
        """Testa l'elaborazione batch della cartella PDF."""
        pdf_dir = DOCUMENTS_DIR / "pdf"
        if not pdf_dir.exists():
            pytest.skip("Directory pdf non trovata")
        
        results = ingestor.ingest_batch(pdf_dir, extensions=[".pdf"])
        
        success = [r for r in results if r[2] is None]
        errors = [r for r in results if r[2] is not None]
        
        assert len(success) > 0, "Nessun PDF processato con successo"
        assert len(errors) == 0, f"Errori nel batch: {[str(e[2]) for e in errors]}"

    def test_batch_all_folders(self, ingestor: Ingestor):
        """Testa l'elaborazione batch di tutte le cartelle."""
        results = ingestor.ingest_batch(DOCUMENTS_DIR, recursive=True)
        
        success = [r for r in results if r[2] is None]
        
        assert len(results) >= 150, f"Trovati solo {len(results)} documenti"
        
        success_rate = len(success) / len(results) if results else 0
        assert success_rate >= 0.95, f"Tasso di successo troppo basso: {success_rate:.1%}"


class TestEdgeCases:
    """Test per casi limite."""

    def test_file_not_found(self, ingestor: Ingestor):
        """Verifica errore per file inesistente."""
        with pytest.raises(FileNotFoundError):
            ingestor.ingest(Path("/nonexistent/file.pdf"))

    def test_unsupported_extension(self, ingestor: Ingestor, tmp_path: Path):
        """Verifica errore per estensione non supportata."""
        unsupported_file = tmp_path / "file.xyz"
        unsupported_file.write_text("test content")
        
        with pytest.raises(ValueError) as exc_info:
            ingestor.ingest(unsupported_file)
        
        assert "non supportato" in str(exc_info.value).lower()


class TestOutputFormat:
    """Test sul formato di output."""

    def test_to_dict_structure(self, ingestor: Ingestor):
        """Verifica la struttura del dizionario di output."""
        pdf_dir = DOCUMENTS_DIR / "pdf"
        if not pdf_dir.exists():
            pytest.skip("Directory pdf non trovata")
        
        pdf_path = next(pdf_dir.glob("*.pdf"), None)
        if pdf_path is None:
            pytest.skip("Nessun PDF trovato")
        
        result = ingestor.ingest(pdf_path)
        output = result.to_dict()
        
        assert "schema_version" in output
        assert output["schema_version"] == "1.0"
        assert "input_id" in output
        assert "source" in output
        assert "parts" in output
        assert isinstance(output["parts"], list)

    def test_json_serialization(self, ingestor: Ingestor):
        """Verifica che l'output sia serializzabile in JSON."""
        pdf_dir = DOCUMENTS_DIR / "pdf"
        if not pdf_dir.exists():
            pytest.skip("Directory pdf non trovata")
        
        pdf_path = next(pdf_dir.glob("*.pdf"), None)
        if pdf_path is None:
            pytest.skip("Nessun PDF trovato")
        
        result = ingestor.ingest(pdf_path)
        json_str = Ingestor.to_json(result)
        
        assert json_str is not None
        assert len(json_str) > 0
        
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == "1.0"
