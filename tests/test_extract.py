"""Test per il modulo extract."""

import json
import pytest
from pathlib import Path

from extract.backends import MockBackend, LLMBackend
from extract.backends.base import LLMResponse
from extract.extractor import OrderExtractor
from extract.models import (
    ExtractionResult,
    ExtractedOrder,
    ExtractedLine,
    WarningSeverity,
)
from extract.preprocessor import Preprocessor, PreprocessedData


class TestMockBackend:
    """Test per il backend mock."""

    def test_is_available(self):
        """Il backend mock è sempre disponibile."""
        backend = MockBackend()
        assert backend.is_available() is True

    def test_model_name(self):
        """Verifica nome modello."""
        backend = MockBackend()
        assert backend.model_name == "mock/deterministic"

    def test_generate_returns_json(self):
        """La risposta è JSON parsabile."""
        backend = MockBackend()
        prompt = """
        PO Number: TEST-001
        Date: 2026-01-15
        
        Item | Description | Qty | UOM
        ABC-123 | Test Product | 10 | EA
        """
        response = backend.generate(prompt)
        
        assert isinstance(response, LLMResponse)
        assert response.content
        
        data = json.loads(response.content)
        assert "header" in data or "lines" in data

    def test_extracts_po_number(self):
        """Estrae il numero PO dal prompt."""
        backend = MockBackend()
        prompt = "Purchase Order: PO-2026-001\nDate: 01/15/2026"
        response = backend.generate(prompt)
        
        data = json.loads(response.content)
        po_number = data.get("header", {}).get("po_number", "")
        assert "PO" in po_number or "2026" in po_number

    def test_call_count(self):
        """Traccia il numero di chiamate."""
        backend = MockBackend()
        assert backend.call_count == 0
        
        backend.generate("test")
        assert backend.call_count == 1
        
        backend.generate("test2")
        assert backend.call_count == 2
        
        backend.reset_call_count()
        assert backend.call_count == 0


class TestPreprocessor:
    """Test per il preprocessor."""

    def test_preprocess_empty_input(self):
        """Gestisce input vuoto."""
        preprocessor = Preprocessor()
        result = preprocessor.preprocess({"parts": []})
        
        assert isinstance(result, PreprocessedData)
        assert result.lines == []

    def test_extract_header_from_email(self):
        """Estrae testata da metadati email."""
        preprocessor = Preprocessor()
        normalized = {
            "email_metadata": {
                "subject": "PO ABC-123 - Order Request",
                "from_name": "Test Customer Inc.",
                "from_address": "orders@test.example",
                "date_parsed": "2026-01-15T10:00:00Z",
            },
            "parts": [],
        }
        
        result = preprocessor.preprocess(normalized)
        
        assert result.header is not None
        assert result.header.po_number == "ABC-123"
        assert result.header.buyer_name == "Test Customer Inc."

    def test_extract_lines_from_table(self):
        """Estrae righe da tabella strutturata."""
        preprocessor = Preprocessor()
        normalized = {
            "parts": [{
                "part_type": "EXCEL_SHEET",
                "tables": [{
                    "table_id": "tbl-1",
                    "header_row_index": 0,
                    "rows": [
                        [{"value": "Item"}, {"value": "Description"}, {"value": "Qty"}, {"value": "UOM"}],
                        [{"value": "SKU-001"}, {"value": "Test Product"}, {"value": 5}, {"value": "EA"}],
                        [{"value": "SKU-002"}, {"value": "Another Item"}, {"value": 10}, {"value": "CS"}],
                    ],
                }],
            }],
        }
        
        result = preprocessor.preprocess(normalized)
        
        assert len(result.lines) == 2
        assert result.lines[0].seller_item_code == "SKU-001"
        assert result.lines[0].description == "Test Product"
        assert result.lines[0].quantity == 5
        assert result.lines[0].uom_raw == "EA"

    def test_skip_total_rows(self):
        """Salta righe di totale."""
        preprocessor = Preprocessor()
        normalized = {
            "parts": [{
                "part_type": "EXCEL_SHEET",
                "tables": [{
                    "table_id": "tbl-1",
                    "header_row_index": 0,
                    "rows": [
                        [{"value": "Item"}, {"value": "Description"}, {"value": "Qty"}],
                        [{"value": "SKU-001"}, {"value": "Product"}, {"value": 5}],
                        [{"value": "Total"}, {"value": ""}, {"value": 5}],
                    ],
                }],
            }],
        }
        
        result = preprocessor.preprocess(normalized)
        
        assert len(result.lines) == 1


class TestOrderExtractor:
    """Test per l'estrattore principale."""

    def test_extract_with_mock_backend(self):
        """Estrazione base con backend mock."""
        backend = MockBackend()
        extractor = OrderExtractor(backend=backend, validate_output=False)
        
        normalized = {
            "input_id": "test-123",
            "source": {
                "filename": "test.xlsx",
                "sha256": "a" * 64,
                "file_type": "XLSX",
            },
            "ingested_at": "2026-01-15T10:00:00Z",
            "parts": [{
                "part_id": "part-1",
                "part_type": "EXCEL_SHEET",
                "sha256": "b" * 64,
                "text": "PO Number: TEST-001\nDate: 01/15/2026",
                "tables": [{
                    "table_id": "tbl-1",
                    "header_row_index": 0,
                    "rows": [
                        [{"value": "Item"}, {"value": "Description"}, {"value": "Qty"}, {"value": "UOM"}],
                        [{"value": "ABC-123"}, {"value": "Test Product"}, {"value": 10}, {"value": "EA"}],
                    ],
                }],
            }],
        }
        
        result = extractor.extract(normalized)
        
        assert isinstance(result, ExtractionResult)
        assert isinstance(result.order, ExtractedOrder)
        assert result.llm_calls >= 1
        assert len(result.order.lines) > 0

    def test_extract_preserves_source_info(self):
        """Preserva informazioni sorgente."""
        backend = MockBackend()
        extractor = OrderExtractor(backend=backend, validate_output=False)
        
        normalized = {
            "input_id": "test-456",
            "source": {
                "filename": "order.pdf",
                "sha256": "c" * 64,
                "file_type": "PDF",
            },
            "email_metadata": {
                "message_id": "<msg-123@test.example>",
                "from_address": "buyer@customer.example",
                "subject": "PO REQ-2026-001",
            },
            "ingested_at": "2026-01-15T10:00:00Z",
            "parts": [{
                "part_id": "part-1",
                "part_type": "PDF_PAGE",
                "sha256": "d" * 64,
                "text": "Purchase Order\nPO: REQ-2026-001\nDate: 01/15/2026",
            }],
        }
        
        result = extractor.extract(normalized)
        
        assert result.order.source_message_id == "<msg-123@test.example>"
        assert result.order.source_from_address == "buyer@customer.example"

    def test_warnings_for_missing_fields(self):
        """Genera avvisi per campi mancanti o estrazione incompleta."""
        backend = MockBackend()
        extractor = OrderExtractor(backend=backend, validate_output=False)
        
        normalized = {
            "input_id": "test-789",
            "source": {
                "filename": "empty.txt",
                "sha256": "e" * 64,
                "file_type": "CSV",
            },
            "ingested_at": "2026-01-15T10:00:00Z",
            "parts": [{
                "part_id": "part-1",
                "part_type": "CSV_DATA",
                "sha256": "f" * 64,
                "text": "Some random text without order data",
            }],
        }
        
        result = extractor.extract(normalized)
        
        assert isinstance(result, ExtractionResult)
        assert result.order is not None

    def test_retry_on_invalid_json(self):
        """Riprova se JSON non valido."""
        class BadJsonBackend(LLMBackend):
            def __init__(self):
                self._calls = 0
            
            @property
            def model_name(self):
                return "test/bad-json"
            
            def is_available(self):
                return True
            
            def generate(self, prompt, **kwargs):
                self._calls += 1
                if self._calls == 1:
                    return LLMResponse(
                        content="not valid json {",
                        model=self.model_name,
                    )
                return LLMResponse(
                    content='{"header": {"po_number": "TEST", "po_date": "2026-01-01"}, "lines": []}',
                    model=self.model_name,
                )
        
        backend = BadJsonBackend()
        extractor = OrderExtractor(backend=backend, max_retries=1, validate_output=False)
        
        normalized = {
            "input_id": "test",
            "source": {"filename": "test.txt", "sha256": "0" * 64, "file_type": "CSV"},
            "ingested_at": "2026-01-01T00:00:00Z",
            "parts": [{"part_id": "p1", "part_type": "CSV_DATA", "sha256": "1" * 64, "text": "test"}],
        }
        
        result = extractor.extract(normalized)
        
        assert result.llm_calls == 2


class TestExtractedModels:
    """Test per i modelli dati estratti."""

    def test_extracted_line_to_dict(self):
        """Serializzazione riga estratta."""
        line = ExtractedLine(
            line_no=1,
            description="Test Product",
            quantity=10.0,
            uom_raw="EA",
            seller_item_code="SKU-001",
            unit_price=25.50,
        )
        
        d = line.to_dict()
        
        assert d["line_no"] == 1
        assert d["description"] == "Test Product"
        assert d["quantity"] == 10.0
        assert d["uom_raw"] == "EA"
        assert d["seller_item_code"] == "SKU-001"
        assert d["unit_price"] == 25.50

    def test_extraction_result_to_dict(self):
        """Serializzazione risultato completo."""
        from extract.models import ExtractedHeader, FieldConfidence, ExtractionWarning
        
        order = ExtractedOrder()
        order.header = ExtractedHeader(
            po_number="TEST-001",
            po_date="2026-01-15",
            currency="USD",
        )
        order.lines = [
            ExtractedLine(
                line_no=1,
                description="Product",
                quantity=5,
                uom_raw="EA",
            ),
        ]
        
        result = ExtractionResult(
            order=order,
            field_confidences=[
                FieldConfidence(path="/header/po_number", confidence=0.95),
            ],
            warnings=[
                ExtractionWarning(
                    code="TEST-01",
                    severity=WarningSeverity.WARN,
                    message="Test warning",
                ),
            ],
        )
        
        d = result.to_dict()
        
        assert d["schema_version"] == "1.0"
        assert d["header"]["po_number"] == "TEST-001"
        assert len(d["lines"]) == 1
        assert "evidence" in d
        assert "validation" in d


class TestIntegrationWithIngest:
    """Test di integrazione con il modulo ingest."""

    @pytest.fixture
    def sample_normalized_path(self, tmp_path):
        """Crea un file NormalizedInput di esempio."""
        normalized = {
            "schema_version": "1.0",
            "input_id": "integration-test-001",
            "source": {
                "filename": "test_order.xlsx",
                "sha256": "abcd1234" * 8,
                "file_type": "XLSX",
            },
            "ingested_at": "2026-01-15T10:00:00Z",
            "parts": [{
                "part_id": "part-001",
                "part_type": "EXCEL_SHEET",
                "sha256": "efgh5678" * 8,
                "sheet_name": "Order",
                "tables": [{
                    "table_id": "tbl-001",
                    "header_row_index": 0,
                    "rows": [
                        [{"value": "Item Code"}, {"value": "Description"}, {"value": "Quantity"}, {"value": "UOM"}, {"value": "Unit Price"}],
                        [{"value": "JAN-LNR-3340"}, {"value": "Can Liner 33x40"}, {"value": 10}, {"value": "CS"}, {"value": 31.50}],
                        [{"value": "PPE-GLOVE-L"}, {"value": "Nitrile Gloves Large"}, {"value": 5}, {"value": "BX"}, {"value": 12.99}],
                    ],
                }],
                "text": "Purchase Order\nPO#: INT-TEST-001\nDate: January 15, 2026\nCustomer: Integration Test Corp.",
            }],
        }
        
        file_path = tmp_path / "normalized_input.json"
        with open(file_path, "w") as f:
            json.dump(normalized, f)
        
        return file_path

    def test_extract_from_file(self, sample_normalized_path):
        """Estrae da file JSON."""
        backend = MockBackend()
        extractor = OrderExtractor(backend=backend, validate_output=False)
        
        result = extractor.extract_from_file(sample_normalized_path)
        
        assert isinstance(result, ExtractionResult)
        assert result.order.header is not None
        assert len(result.order.lines) >= 1

    def test_full_pipeline_with_preprocessor(self, sample_normalized_path):
        """Pipeline completa con pre-elaborazione."""
        with open(sample_normalized_path) as f:
            normalized = json.load(f)
        
        preprocessor = Preprocessor()
        preprocessed = preprocessor.preprocess(normalized)
        
        assert len(preprocessed.lines) == 2
        assert preprocessed.lines[0].seller_item_code == "JAN-LNR-3340"
        assert preprocessed.lines[0].quantity == 10
        
        backend = MockBackend()
        extractor = OrderExtractor(backend=backend, validate_output=False)
        result = extractor.extract(normalized)
        
        assert len(result.order.lines) >= 1


class TestEvaluation:
    """Test per lo script di valutazione."""

    def test_compare_values_numbers(self):
        """Confronto numerico con tolleranza."""
        from extract.eval import compare_values
        
        assert compare_values(10.0, 10) is True
        assert compare_values(10.01, 10.0) is True
        assert compare_values(11.0, 10.0) is False
        assert compare_values(None, None) is True
        assert compare_values(None, 10) is False

    def test_compare_values_strings(self):
        """Confronto stringhe con fuzzy matching."""
        from extract.eval import compare_values, normalize_string
        
        assert compare_values("ABC-123", "ABC-123") is True
        assert compare_values("abc-123", "ABC-123", fuzzy=True) is True
        assert compare_values("ABC123", "ABC-123", fuzzy=True) is True

    def test_evaluate_order_basic(self):
        """Valutazione base ordine."""
        from extract.eval import evaluate_order
        
        extracted = {
            "header": {
                "po_number": "TEST-001",
                "po_date": "2026-01-15",
                "currency": "USD",
            },
            "lines": [
                {"line_no": 1, "seller_item_code": "SKU-001", "description": "Product A", "quantity": 10, "uom_raw": "EA"},
            ],
        }
        
        ground_truth = {
            "order_id": "gt-001",
            "header": {
                "po_number": "TEST-001",
                "po_date": "2026-01-15",
                "currency": "USD",
            },
            "lines": [
                {"line_no": 1, "seller_item_code": "SKU-001", "description": "Product A", "quantity": 10, "uom_raw": "EA"},
            ],
            "_synthetic_metadata": {"is_hard_case": False},
        }
        
        score = evaluate_order(extracted, ground_truth)
        
        assert score.header_accuracy() > 0.9
        assert score.lines_matched == 1
        assert score.lines_expected == 1
