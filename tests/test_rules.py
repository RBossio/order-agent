"""Test per il motore di regole di validazione."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from rules import (
    DecisionRoute,
    Issue,
    RuleContext,
    Severity,
    ValidationEngine,
    ValidationResult,
    get_all_rules,
    get_rules_by_area,
)


def make_vof(
    po_number: str = "TEST-001",
    po_date: str | None = None,
    lines: list | None = None,
    buyer_resolved: dict | None = None,
    **kwargs,
) -> dict:
    """Helper per creare un VOF di test."""
    if po_date is None:
        po_date = datetime.now().strftime("%Y-%m-%d")
    
    if lines is None:
        lines = [{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 10,
            "uom_raw": "EA",
            "uom": "EA",
            "unit_price": 10.00,
            "line_amount": 100.00,
            "resolution": {
                "sku": "TEST-SKU",
                "erp_product_id": 100,
                "erp_uom": "EA",
                "method": "XREF",
                "score": 1.0,
            },
        }]
    
    vof = {
        "schema_version": "1.0",
        "order_id": str(uuid.uuid4()),
        "tenant_id": "test-tenant",
        "document_type": "ORIGINAL",
        "status": "EXTRACTED",
        "source": {
            "channel": "EMAIL_IMAP",
            "message_id": f"<test-{uuid.uuid4()}@test.example>",
            "from_address": "test@test.example",
            "subject": "Test Order",
            "received_at": datetime.now().isoformat() + "Z",
            "documents": [{
                "document_id": "doc-1",
                "kind": "PDF_TEXT",
                "sha256": "a" * 64,
            }],
        },
        "header": {
            "po_number": po_number,
            "po_date": po_date,
            "currency": "USD",
        },
        "buyer": {
            "name": "Test Buyer Inc.",
            "resolved": buyer_resolved or {
                "erp_partner_id": 1,
                "method": "EMAIL_DOMAIN",
                "score": 0.99,
            },
        },
        "lines": lines,
    }
    vof.update(kwargs)
    return vof


class TestRulesRegistry:
    """Test per il registro delle regole."""
    
    def test_all_rules_registered(self):
        """Verifica che tutte le regole siano registrate."""
        rules = get_all_rules()
        assert len(rules) >= 40, f"Attese almeno 40 regole, trovate {len(rules)}"
    
    def test_rules_by_area(self):
        """Verifica le regole per area."""
        areas = ["HDR", "CUS", "ITM", "UOM", "QTY", "PRC", "TOT", "DUP", "EXT", "SEC", "EXP"]
        for area in areas:
            rules = get_rules_by_area(area)
            assert len(rules) > 0, f"Nessuna regola trovata per area {area}"
    
    def test_rule_code_format(self):
        """Verifica il formato dei codici regola."""
        import re
        pattern = re.compile(r"^[A-Z]{2,4}-\d{2}$")
        for code in get_all_rules():
            assert pattern.match(code), f"Codice {code} non rispetta il formato AAA-00"


class TestHdrRules:
    """Test per le regole HDR (testata)."""
    
    def test_hdr_01_missing_po_number(self):
        """HDR-01: po_number mancante."""
        vof = make_vof(po_number="")
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-01" in codes
        assert result.has_blocking_issues()
    
    def test_hdr_01_valid_po_number(self):
        """HDR-01: po_number valido."""
        vof = make_vof(po_number="PO-12345")
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-01" not in codes
    
    def test_hdr_02_missing_po_date(self):
        """HDR-02: po_date mancante."""
        vof = make_vof()
        vof["header"]["po_date"] = None
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-02" in codes
    
    def test_hdr_02_future_date(self):
        """HDR-02: po_date oltre 7 giorni nel futuro."""
        future_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        vof = make_vof(po_date=future_date)
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-02" in codes
    
    def test_hdr_02_valid_date(self):
        """HDR-02: po_date valida."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        hdr02_issues = [i for i in result.issues if i.code == "HDR-02"]
        assert len(hdr02_issues) == 0
    
    def test_hdr_04_past_delivery_date(self):
        """HDR-04: delivery date nel passato."""
        vof = make_vof()
        past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        vof["header"]["requested_delivery_date"] = past_date
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-04" in codes
    
    def test_hdr_05_change_order(self):
        """HDR-05: ordine di tipo CHANGE."""
        vof = make_vof(document_type="CHANGE")
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "HDR-05" in codes


class TestCusRules:
    """Test per le regole CUS (cliente)."""
    
    def test_cus_01_no_customer(self):
        """CUS-01: cliente non trovato."""
        vof = make_vof(buyer_resolved=None)
        vof["buyer"]["resolved"] = None
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "CUS-01" in codes
        assert result.has_blocking_issues()
    
    def test_cus_01_valid_customer(self):
        """CUS-01: cliente valido."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "CUS-01" not in codes
    
    def test_cus_02_fuzzy_match_low_score(self):
        """CUS-02: cliente fuzzy con score basso."""
        vof = make_vof(buyer_resolved={
            "erp_partner_id": 1,
            "method": "FUZZY_NAME",
            "score": 0.85,
        })
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "CUS-02" in codes


class TestItmRules:
    """Test per le regole ITM (articoli)."""
    
    def test_itm_01_unresolved_line(self):
        """ITM-01: riga non risolta."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Unknown Product",
            "quantity": 5,
            "uom_raw": "EA",
            "resolution": None,
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-01" in codes
    
    def test_itm_01_low_score(self):
        """ITM-01: riga con score troppo basso."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 5,
            "uom_raw": "EA",
            "resolution": {
                "sku": "TEST",
                "method": "FUZZY",
                "score": 0.60,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-01" in codes
    
    def test_itm_03_fuzzy_match(self):
        """ITM-03: risoluzione fuzzy."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 5,
            "uom_raw": "EA",
            "buyer_item_code": "CUST-123",
            "resolution": {
                "sku": "TEST-SKU",
                "method": "FUZZY",
                "score": 0.88,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-03" in codes
    
    def test_itm_05_invalid_gtin(self):
        """ITM-05: GTIN con checksum non valido."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 5,
            "uom_raw": "EA",
            "gtin": "1234567890123",
            "resolution": {"sku": "TEST", "method": "XREF", "score": 1.0},
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-05" in codes
    
    def test_itm_05_valid_gtin(self):
        """ITM-05: GTIN valido."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 5,
            "uom_raw": "EA",
            "gtin": "0012345678905",
            "resolution": {"sku": "TEST", "method": "XREF", "score": 1.0},
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-05" not in codes
    
    def test_itm_06_duplicate_products(self):
        """ITM-06: stesso prodotto su più righe."""
        vof = make_vof(lines=[
            {
                "line_no": 1,
                "description": "Product A",
                "quantity": 5,
                "uom_raw": "EA",
                "resolution": {"sku": "SAME-SKU", "method": "XREF", "score": 1.0},
            },
            {
                "line_no": 2,
                "description": "Product A again",
                "quantity": 10,
                "uom_raw": "EA",
                "resolution": {"sku": "SAME-SKU", "method": "XREF", "score": 1.0},
            },
        ])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "ITM-06" in codes


class TestUomRules:
    """Test per le regole UOM (unità di misura)."""
    
    def test_uom_01_unknown_uom(self):
        """UOM-01: UoM non riconosciuta."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 5,
            "uom_raw": "UNKNOWN_UOM",
            "uom": None,
            "resolution": {"sku": "TEST", "method": "XREF", "score": 1.0},
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "UOM-01" in codes
    
    def test_uom_03_conversion_applied(self):
        """UOM-03: conversione applicata."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 2,
            "uom_raw": "CS",
            "uom": "CS",
            "resolution": {
                "sku": "TEST",
                "method": "XREF",
                "score": 1.0,
                "erp_uom": "EA",
                "erp_quantity": 24,
                "conversion_factor": 12,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "UOM-03" in codes
        
        uom03 = next(i for i in result.issues if i.code == "UOM-03")
        assert uom03.severity == Severity.INFO
    
    def test_uom_05_non_integer_quantity(self):
        """UOM-05: quantità non intera per unità indivisibile."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 2.5,
            "uom_raw": "EA",
            "uom": "EA",
            "resolution": {
                "sku": "TEST",
                "method": "XREF",
                "score": 1.0,
                "erp_uom": "EA",
                "erp_quantity": 2.5,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "UOM-05" in codes


class TestQtyRules:
    """Test per le regole QTY (quantità)."""
    
    def test_qty_01_missing_quantity(self):
        """QTY-01: quantità mancante."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": None,
            "uom_raw": "EA",
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "QTY-01" in codes
    
    def test_qty_01_zero_quantity(self):
        """QTY-01: quantità zero."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 0,
            "uom_raw": "EA",
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "QTY-01" in codes
    
    def test_qty_01_negative_quantity(self):
        """QTY-01: quantità negativa."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": -5,
            "uom_raw": "EA",
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "QTY-01" in codes
    
    def test_qty_01_valid_quantity(self):
        """QTY-01: quantità valida."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "QTY-01" not in codes


class TestPrcRules:
    """Test per le regole PRC (prezzi)."""
    
    def test_prc_01_price_above_tolerance(self):
        """PRC-01: prezzo sopra tolleranza."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 10,
            "uom_raw": "EA",
            "unit_price": 12.00,
            "line_amount": 120.00,
            "resolution": {
                "sku": "TEST",
                "method": "XREF",
                "score": 1.0,
                "erp_list_price": 10.00,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "PRC-01" in codes
    
    def test_prc_01_price_within_tolerance(self):
        """PRC-01: prezzo entro tolleranza."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 10,
            "uom_raw": "EA",
            "unit_price": 10.15,
            "line_amount": 101.50,
            "resolution": {
                "sku": "TEST",
                "method": "XREF",
                "score": 1.0,
                "erp_list_price": 10.00,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "PRC-01" not in codes
    
    def test_prc_02_missing_price(self):
        """PRC-02: prezzo mancante."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 10,
            "uom_raw": "EA",
            "unit_price": None,
            "resolution": {
                "sku": "TEST",
                "method": "XREF",
                "score": 1.0,
                "erp_list_price": 10.00,
            },
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "PRC-02" in codes
        
        prc02 = next(i for i in result.issues if i.code == "PRC-02")
        assert prc02.severity == Severity.INFO
    
    def test_prc_03_line_amount_mismatch(self):
        """PRC-03: importo riga non corrisponde."""
        vof = make_vof(lines=[{
            "line_no": 1,
            "description": "Test Product",
            "quantity": 10,
            "uom_raw": "EA",
            "unit_price": 10.00,
            "line_amount": 150.00,
            "resolution": {"sku": "TEST", "method": "XREF", "score": 1.0},
        }])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "PRC-03" in codes


class TestTotRules:
    """Test per le regole TOT (totali)."""
    
    def test_tot_01_total_mismatch(self):
        """TOT-01: totale non corrisponde."""
        vof = make_vof(
            totals={"total_amount_declared": 200.00}
        )
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "TOT-01" in codes
    
    def test_tot_01_total_matches(self):
        """TOT-01: totale corrisponde."""
        vof = make_vof(
            totals={"total_amount_declared": 100.00}
        )
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "TOT-01" not in codes
    
    def test_tot_02_no_lines(self):
        """TOT-02: nessuna riga."""
        vof = make_vof(lines=[])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "TOT-02" in codes
    
    def test_tot_02_missing_line_numbers(self):
        """TOT-02: numerazione con salti."""
        vof = make_vof(lines=[
            {"line_no": 1, "description": "A", "quantity": 1, "uom_raw": "EA",
             "resolution": {"sku": "A", "method": "XREF", "score": 1.0}},
            {"line_no": 3, "description": "C", "quantity": 1, "uom_raw": "EA",
             "resolution": {"sku": "C", "method": "XREF", "score": 1.0}},
        ])
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "TOT-02" in codes


class TestDupRules:
    """Test per le regole DUP (duplicati)."""
    
    def test_dup_02_duplicate_message_id(self):
        """DUP-02: Message-ID già elaborato."""
        vof = make_vof()
        message_id = vof["source"]["message_id"]
        
        ctx = RuleContext(
            tenant_id="test",
            processed_message_ids={message_id},
        )
        
        from rules.dup import rule_dup_02
        issues = rule_dup_02(vof, ctx)
        
        assert len(issues) == 1
        assert issues[0].code == "DUP-02"
    
    def test_dup_02_new_message(self):
        """DUP-02: nuovo messaggio."""
        vof = make_vof()
        
        ctx = RuleContext(
            tenant_id="test",
            processed_message_ids=set(),
        )
        
        from rules.dup import rule_dup_02
        issues = rule_dup_02(vof, ctx)
        
        assert len(issues) == 0


class TestExtRules:
    """Test per le regole EXT (estrazione)."""
    
    def test_ext_01_low_confidence(self):
        """EXT-01: confidenza bassa su campo critico."""
        vof = make_vof(
            evidence={
                "/header/po_number": {"confidence": 0.75},
            }
        )
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "EXT-01" in codes
    
    def test_ext_01_high_confidence(self):
        """EXT-01: confidenza alta."""
        vof = make_vof(
            evidence={
                "/header/po_number": {"confidence": 0.95},
            }
        )
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        ext01_issues = [i for i in result.issues if i.code == "EXT-01"]
        assert len(ext01_issues) == 0


class TestSecRules:
    """Test per le regole SEC (sicurezza)."""
    
    def test_sec_01_encrypted_attachment(self):
        """SEC-01: allegato cifrato."""
        vof = make_vof()
        vof["source"]["documents"] = [{
            "document_id": "doc-1",
            "kind": "PDF_TEXT",
            "sha256": "a" * 64,
            "filename": "order.pdf",
            "is_encrypted": True,
        }]
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "SEC-01" in codes
    
    def test_sec_01_macro_file(self):
        """SEC-01: file con macro."""
        vof = make_vof()
        vof["source"]["documents"] = [{
            "document_id": "doc-1",
            "kind": "XLSX",
            "sha256": "a" * 64,
            "filename": "order.xlsm",
        }]
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "SEC-01" in codes
    
    def test_sec_01_large_file(self):
        """SEC-01: file oltre il limite."""
        vof = make_vof()
        vof["source"]["documents"] = [{
            "document_id": "doc-1",
            "kind": "PDF_TEXT",
            "sha256": "a" * 64,
            "filename": "order.pdf",
            "size_bytes": 25 * 1024 * 1024,
        }]
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "SEC-01" in codes
    
    def test_sec_01_normal_pdf(self):
        """SEC-01: PDF normale."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        codes = [i.code for i in result.issues]
        assert "SEC-01" not in codes


class TestValidationEngine:
    """Test per il motore di validazione."""
    
    def test_validate_clean_order(self):
        """Ordine pulito senza issue."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        block_issues = [i for i in result.issues if i.severity == Severity.BLOCK]
        review_issues = [i for i in result.issues if i.severity == Severity.REVIEW]
        
        assert len(block_issues) == 0
        assert len(review_issues) == 0
    
    def test_validate_returns_result(self):
        """Validate restituisce ValidationResult."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "issues")
        assert hasattr(result, "route")
        assert hasattr(result, "score")
    
    def test_apply_to_vof(self):
        """Apply aggiorna il VOF."""
        vof = make_vof()
        engine = ValidationEngine()
        result = engine.validate(vof)
        
        updated_vof = engine.apply_to_vof(vof, result)
        
        assert "validation" in updated_vof
        assert "decision" in updated_vof
        assert "issues" in updated_vof["validation"]
        assert "route" in updated_vof["decision"]
        assert "score" in updated_vof["decision"]
    
    def test_route_reject_on_duplicate(self):
        """Route REJECT per duplicato."""
        result = ValidationResult()
        result.add_issue(Issue(
            code="DUP-01",
            severity=Severity.BLOCK,
            message="Duplicato",
        ))
        
        engine = ValidationEngine()
        engine._determine_route(result, RuleContext(tenant_id="test"))
        
        assert result.route == DecisionRoute.REJECT
    
    def test_route_review_on_block(self):
        """Route REVIEW per issue BLOCK."""
        result = ValidationResult()
        result.add_issue(Issue(
            code="ITM-01",
            severity=Severity.BLOCK,
            message="Articolo non risolto",
        ))
        
        engine = ValidationEngine()
        engine._determine_route(result, RuleContext(tenant_id="test"))
        
        assert result.route == DecisionRoute.REVIEW
    
    def test_config_loading(self):
        """Caricamento configurazione da file."""
        config_dir = Path(__file__).parent.parent / "config"
        if config_dir.exists():
            engine = ValidationEngine(config_dir=config_dir)
            config = engine.load_config("test-tenant")
            
            assert "thresholds" in config
            assert "rules" in config


class TestIssueModel:
    """Test per il modello Issue."""
    
    def test_issue_to_dict(self):
        """Conversione issue in dizionario."""
        issue = Issue(
            code="HDR-01",
            severity=Severity.BLOCK,
            message="Test message",
            path="/header/po_number",
            suggestion="Fix it",
        )
        
        d = issue.to_dict()
        
        assert d["code"] == "HDR-01"
        assert d["severity"] == "BLOCK"
        assert d["message"] == "Test message"
        assert d["path"] == "/header/po_number"
        assert d["suggestion"] == "Fix it"
    
    def test_issue_minimal(self):
        """Issue con campi minimi."""
        issue = Issue(
            code="TEST-01",
            severity=Severity.INFO,
            message="Info message",
        )
        
        d = issue.to_dict()
        
        assert "path" not in d
        assert "suggestion" not in d


class TestValidationResult:
    """Test per ValidationResult."""
    
    def test_add_block_issue(self):
        """Aggiunta issue BLOCK."""
        result = ValidationResult()
        result.add_issue(Issue(
            code="TEST-01",
            severity=Severity.BLOCK,
            message="Block",
        ))
        
        assert result.has_blocking_issues()
        assert result.route == DecisionRoute.REVIEW
        assert "TEST-01" in result.reasons
    
    def test_add_review_issue(self):
        """Aggiunta issue REVIEW."""
        result = ValidationResult()
        result.add_issue(Issue(
            code="TEST-01",
            severity=Severity.REVIEW,
            message="Review",
        ))
        
        assert result.has_review_issues()
        assert not result.has_blocking_issues()
        assert result.route == DecisionRoute.REVIEW
    
    def test_add_warn_issue(self):
        """Aggiunta issue WARN."""
        result = ValidationResult()
        initial_score = result.score
        result.add_issue(Issue(
            code="TEST-01",
            severity=Severity.WARN,
            message="Warn",
        ))
        
        assert result.score < initial_score
        assert result.route == DecisionRoute.AUTO_OK
    
    def test_final_status_validated(self):
        """Stato finale VALIDATED."""
        result = ValidationResult()
        assert result.get_final_status() == "VALIDATED"
    
    def test_final_status_needs_review(self):
        """Stato finale NEEDS_REVIEW."""
        result = ValidationResult()
        result.route = DecisionRoute.REVIEW
        assert result.get_final_status() == "NEEDS_REVIEW"
    
    def test_final_status_rejected(self):
        """Stato finale REJECTED."""
        result = ValidationResult()
        result.route = DecisionRoute.REJECT
        assert result.get_final_status() == "REJECTED"
