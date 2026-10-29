"""
Estrattore principale: NormalizedInput -> VentureOrder.

Combina pre-elaborazione deterministica e LLM per estrarre
ordini strutturati da documenti normalizzati.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import jsonschema

from .backends import LLMBackend, MockBackend
from .models import (
    ExtractionResult,
    ExtractionWarning,
    ExtractedHeader,
    ExtractedLine,
    ExtractedOrder,
    ExtractedPack,
    ExtractedParty,
    ExtractedTotals,
    FieldConfidence,
    WarningSeverity,
)
from .preprocessor import Preprocessor, PreprocessedData, PreprocessedLine
from .prompts import (
    EXTRACTION_JSON_SCHEMA,
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_prompt,
    build_retry_prompt,
)


class OrderExtractor:
    """
    Estrattore di ordini da NormalizedInput.
    
    Combina:
    1. Pre-elaborazione deterministica (tabelle strutturate)
    2. Estrazione LLM (testata, righe ambigue, testo libero)
    3. Validazione JSON schema
    4. Retry con messaggio di errore se validazione fallisce
    """

    def __init__(
        self,
        backend: LLMBackend | None = None,
        max_retries: int = 1,
        validate_output: bool = True,
    ):
        """
        Inizializza l'estrattore.
        
        Args:
            backend: Backend LLM da usare. Default: MockBackend.
            max_retries: Numero massimo di retry dopo errore validazione.
            validate_output: Se validare l'output contro lo schema JSON.
        """
        self.backend = backend or MockBackend()
        self.preprocessor = Preprocessor()
        self.max_retries = max_retries
        self.validate_output = validate_output
        self._schema_path = Path(__file__).parent.parent / "schema" / "venture-order.v1.schema.json"

    def extract(self, normalized_input: dict) -> ExtractionResult:
        """
        Estrae un ordine da un NormalizedInput.
        
        Args:
            normalized_input: Dizionario con struttura NormalizedInput.
            
        Returns:
            ExtractionResult con ordine estratto e metadati.
        """
        start_time = time.time()
        warnings: list[ExtractionWarning] = []
        field_confidences: list[FieldConfidence] = []
        llm_calls = 0
        total_tokens = 0
        preprocessed_fields: list[str] = []
        
        preprocessed = self.preprocessor.preprocess(normalized_input)
        
        if preprocessed.header and preprocessed.header.po_number:
            preprocessed_fields.append("/header/po_number")
        
        for idx, line in enumerate(preprocessed.lines):
            if not line.needs_llm:
                preprocessed_fields.append(f"/lines/{idx}")
        
        document_content = self._build_document_content(normalized_input, preprocessed)
        
        preprocessed_lines_dict = [
            {
                "line_no": l.row_index,
                "seller_item_code": l.seller_item_code,
                "buyer_item_code": l.buyer_item_code,
                "description": l.description,
                "quantity": l.quantity,
                "uom_raw": l.uom_raw,
                "unit_price": l.unit_price,
            }
            for l in preprocessed.lines
        ]
        
        preprocessed_header_dict = None
        if preprocessed.header:
            preprocessed_header_dict = {
                "po_number": preprocessed.header.po_number,
                "po_date": preprocessed.header.po_date,
                "currency": preprocessed.header.currency,
                "buyer_name": preprocessed.header.buyer_name,
            }
        
        prompt = build_extraction_prompt(
            document_content,
            preprocessed_lines=preprocessed_lines_dict if preprocessed.lines else None,
            preprocessed_header=preprocessed_header_dict,
        )
        
        llm_response = self.backend.generate(
            prompt=prompt,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            json_schema=EXTRACTION_JSON_SCHEMA,
            temperature=0.0,
        )
        llm_calls += 1
        total_tokens += llm_response.total_tokens
        
        extracted_json, parse_error = self._parse_json_response(llm_response.content)
        
        if parse_error and self.max_retries > 0:
            retry_prompt = build_retry_prompt(
                error_message=parse_error,
                document_summary=document_content[:2000],
            )
            
            retry_response = self.backend.generate(
                prompt=retry_prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                json_schema=EXTRACTION_JSON_SCHEMA,
                temperature=0.0,
            )
            llm_calls += 1
            total_tokens += retry_response.total_tokens
            
            extracted_json, parse_error = self._parse_json_response(retry_response.content)
        
        if parse_error:
            warnings.append(ExtractionWarning(
                code="EXT-01",
                severity=WarningSeverity.BLOCK,
                message=f"Errore parsing JSON: {parse_error}",
            ))
            extracted_json = {"header": {}, "lines": []}
        
        order = self._build_order(
            extracted_json,
            preprocessed,
            normalized_input,
            field_confidences,
            warnings,
        )
        
        if self.validate_output:
            validation_errors = self._validate_order(order)
            for err in validation_errors:
                warnings.append(err)
        
        extraction_time = int((time.time() - start_time) * 1000)
        
        order.status = "NEEDS_REVIEW" if any(
            w.severity == WarningSeverity.BLOCK for w in warnings
        ) else "EXTRACTED"
        
        return ExtractionResult(
            order=order,
            field_confidences=field_confidences,
            warnings=warnings,
            llm_calls=llm_calls,
            llm_tokens_used=total_tokens,
            extraction_time_ms=extraction_time,
            preprocessed_fields=preprocessed_fields,
        )

    def extract_from_file(self, file_path: Path | str) -> ExtractionResult:
        """
        Estrae da un file JSON NormalizedInput.
        
        Args:
            file_path: Percorso al file JSON.
            
        Returns:
            ExtractionResult con ordine estratto.
        """
        file_path = Path(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            normalized_input = json.load(f)
        return self.extract(normalized_input)

    def _build_document_content(
        self,
        normalized_input: dict,
        preprocessed: PreprocessedData,
    ) -> str:
        """Costruisce il contenuto testuale per il prompt."""
        parts = []
        
        email_meta = normalized_input.get("email_metadata")
        if email_meta:
            parts.append("=== EMAIL METADATA ===")
            if email_meta.get("from_name"):
                parts.append(f"From: {email_meta['from_name']} <{email_meta.get('from_address', '')}>")
            elif email_meta.get("from_address"):
                parts.append(f"From: {email_meta['from_address']}")
            if email_meta.get("subject"):
                parts.append(f"Subject: {email_meta['subject']}")
            if email_meta.get("date"):
                parts.append(f"Date: {email_meta['date']}")
            parts.append("")
        
        if preprocessed.unstructured_text:
            parts.append(preprocessed.unstructured_text)
        
        for part in normalized_input.get("parts", []):
            if part.get("part_type") in ("EXCEL_SHEET", "CSV_DATA"):
                tables = part.get("tables", [])
                for table in tables:
                    table_text = self._table_to_text(table)
                    if table_text:
                        parts.append(f"\n=== TABELLA ({part.get('sheet_name', 'Foglio')}) ===")
                        parts.append(table_text)
        
        return "\n".join(parts)

    def _table_to_text(self, table: dict) -> str:
        """Converte una tabella in formato testuale."""
        rows = table.get("rows", [])
        if not rows:
            return ""
        
        lines = []
        for row in rows[:30]:
            cells = []
            for cell in row:
                if isinstance(cell, dict):
                    val = cell.get("value", "")
                else:
                    val = cell
                cells.append(str(val) if val is not None else "")
            lines.append(" | ".join(cells))
        
        if len(rows) > 30:
            lines.append(f"... ({len(rows) - 30} righe aggiuntive)")
        
        return "\n".join(lines)

    def _parse_json_response(self, content: str) -> tuple[dict | None, str | None]:
        """
        Parsa la risposta JSON dall'LLM.
        
        Returns:
            Tuple (json_dict, error_message).
        """
        content = content.strip()
        
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        
        try:
            data = json.loads(content)
            return data, None
        except json.JSONDecodeError as e:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data, None
                except json.JSONDecodeError:
                    pass
            return None, f"JSON non valido: {e}"

    def _build_order(
        self,
        extracted_json: dict,
        preprocessed: PreprocessedData,
        normalized_input: dict,
        field_confidences: list[FieldConfidence],
        warnings: list[ExtractionWarning],
    ) -> ExtractedOrder:
        """Costruisce l'ordine finale combinando preprocessed e LLM."""
        order = ExtractedOrder()
        
        source = normalized_input.get("source", {})
        order.source_channel = self._infer_channel(source.get("file_type", ""))
        
        email_meta = normalized_input.get("email_metadata")
        if email_meta:
            order.source_message_id = email_meta.get("message_id")
            order.source_from_address = email_meta.get("from_address")
            order.source_subject = email_meta.get("subject")
            order.source_received_at = email_meta.get("date_parsed")
        
        order.source_documents = [{
            "document_id": f"doc-{normalized_input.get('input_id', 'unknown')[:8]}",
            "kind": self._file_type_to_kind(source.get("file_type", "")),
            "filename": source.get("filename"),
            "sha256": source.get("sha256", "0" * 64),
        }]
        
        header_data = extracted_json.get("header", {})
        
        po_number = header_data.get("po_number")
        if not po_number and preprocessed.header:
            po_number = preprocessed.header.po_number
        
        po_date = header_data.get("po_date")
        if not po_date and preprocessed.header:
            po_date = preprocessed.header.po_date
        
        if not po_number:
            warnings.append(ExtractionWarning(
                code="HDR-01",
                severity=WarningSeverity.BLOCK,
                message="Numero PO mancante",
                path="/header/po_number",
            ))
            po_number = "UNKNOWN"
        
        if not po_date:
            warnings.append(ExtractionWarning(
                code="HDR-02",
                severity=WarningSeverity.REVIEW,
                message="Data ordine mancante",
                path="/header/po_date",
            ))
            po_date = "1970-01-01"
        
        order.header = ExtractedHeader(
            po_number=po_number,
            po_date=po_date,
            currency=header_data.get("currency") or preprocessed.header.currency if preprocessed.header else "USD",
            requested_delivery_date=header_data.get("requested_delivery_date"),
            buyer_reference=header_data.get("buyer_reference"),
            payment_terms_text=header_data.get("payment_terms"),
            ship_via=header_data.get("ship_via"),
            notes=header_data.get("notes"),
        )
        
        field_confidences.append(FieldConfidence(
            path="/header/po_number",
            confidence=0.95 if po_number != "UNKNOWN" else 0.0,
            source="llm" if header_data.get("po_number") else "preprocessor",
        ))
        
        buyer_data = extracted_json.get("buyer", {})
        if buyer_data:
            order.buyer = ExtractedParty(
                name=buyer_data.get("name"),
                code_on_document=buyer_data.get("code"),
                contact_email=buyer_data.get("contact_email"),
                contact_name=buyer_data.get("contact_name"),
            )
            if buyer_data.get("address"):
                order.buyer.address_line1 = buyer_data["address"]
        
        ship_to_data = extracted_json.get("ship_to", {})
        if ship_to_data:
            order.ship_to = ExtractedParty(
                name=ship_to_data.get("name"),
            )
            if ship_to_data.get("address"):
                order.ship_to.address_line1 = ship_to_data["address"]
        
        lines = self._build_lines(
            extracted_json.get("lines", []),
            preprocessed.lines,
            field_confidences,
            warnings,
        )
        order.lines = lines
        
        if not lines:
            warnings.append(ExtractionWarning(
                code="LIN-01",
                severity=WarningSeverity.BLOCK,
                message="Nessuna riga ordine estratta",
            ))
        
        totals_data = extracted_json.get("totals", {})
        if totals_data:
            order.totals = ExtractedTotals(
                lines_amount_declared=totals_data.get("subtotal"),
                tax_amount_declared=totals_data.get("tax"),
                total_amount_declared=totals_data.get("total"),
            )
        
        if field_confidences:
            avg_confidence = sum(fc.confidence for fc in field_confidences) / len(field_confidences)
            order.overall_confidence = avg_confidence
        
        return order

    def _build_lines(
        self,
        llm_lines: list[dict],
        preprocessed_lines: list[PreprocessedLine],
        field_confidences: list[FieldConfidence],
        warnings: list[ExtractionWarning],
    ) -> list[ExtractedLine]:
        """Costruisce le righe ordine combinando preprocessed e LLM."""
        final_lines: list[ExtractedLine] = []
        
        if preprocessed_lines and not llm_lines:
            for idx, pl in enumerate(preprocessed_lines, start=1):
                if pl.description and pl.quantity is not None:
                    line = ExtractedLine(
                        line_no=idx,
                        description=pl.description,
                        quantity=pl.quantity,
                        uom_raw=pl.uom_raw or "EA",
                        seller_item_code=pl.seller_item_code,
                        buyer_item_code=pl.buyer_item_code,
                        unit_price=pl.unit_price,
                        line_amount=pl.line_amount,
                        confidence=pl.confidence,
                    )
                    final_lines.append(line)
                    field_confidences.append(FieldConfidence(
                        path=f"/lines/{idx-1}",
                        confidence=pl.confidence,
                        source="preprocessor",
                    ))
        
        elif llm_lines:
            for idx, ll in enumerate(llm_lines, start=1):
                description = ll.get("description", "")
                quantity = ll.get("quantity")
                uom_raw = ll.get("uom_raw", "EA")
                
                if not description:
                    continue
                
                if quantity is None:
                    warnings.append(ExtractionWarning(
                        code="QTY-01",
                        severity=WarningSeverity.BLOCK,
                        message=f"Quantità mancante per riga {idx}",
                        path=f"/lines/{idx-1}/quantity",
                    ))
                    quantity = 1
                
                pack = None
                pack_info = ll.get("pack_info")
                if pack_info:
                    pack = self._parse_pack_info(pack_info)
                
                line = ExtractedLine(
                    line_no=ll.get("line_no", idx),
                    description=description,
                    quantity=float(quantity),
                    uom_raw=uom_raw,
                    seller_item_code=ll.get("seller_item_code"),
                    buyer_item_code=ll.get("buyer_item_code"),
                    unit_price=ll.get("unit_price"),
                    line_amount=ll.get("line_amount"),
                    pack=pack,
                    notes=ll.get("notes"),
                    confidence=0.85,
                )
                final_lines.append(line)
                field_confidences.append(FieldConfidence(
                    path=f"/lines/{idx-1}",
                    confidence=0.85,
                    source="llm",
                ))
        
        return final_lines

    def _parse_pack_info(self, pack_info: str) -> ExtractedPack | None:
        """Parsa informazioni confezione (es. '4/1 GAL', '100/BX')."""
        if not pack_info:
            return None
        
        pack = ExtractedPack(raw=pack_info)
        
        match = re.match(r'(\d+)/(\d+(?:\.\d+)?)\s*([A-Z]+)', pack_info, re.IGNORECASE)
        if match:
            pack.inner_count = float(match.group(1))
            pack.inner_size = float(match.group(2))
            pack.inner_uom = match.group(3).upper()
            return pack
        
        match = re.match(r'(\d+)/([A-Z]+)', pack_info, re.IGNORECASE)
        if match:
            pack.inner_count = float(match.group(1))
            pack.inner_size = 1
            pack.inner_uom = match.group(2).upper()
            return pack
        
        return pack

    def _validate_order(self, order: ExtractedOrder) -> list[ExtractionWarning]:
        """Valida l'ordine contro lo schema venture-order.v1."""
        warnings = []
        
        if not self._schema_path.exists():
            return warnings
        
        try:
            with open(self._schema_path) as f:
                schema = json.load(f)
            
            order_dict = order.to_dict()
            validator = jsonschema.Draft202012Validator(schema)
            
            for error in validator.iter_errors(order_dict):
                path = "/" + "/".join(str(p) for p in error.absolute_path) if error.absolute_path else ""
                warnings.append(ExtractionWarning(
                    code="VAL-01",
                    severity=WarningSeverity.WARN,
                    message=error.message[:200],
                    path=path or None,
                ))
        except Exception:
            pass
        
        return warnings

    def _infer_channel(self, file_type: str) -> str:
        """Inferisce il canale dalla tipologia file."""
        if file_type == "EML":
            return "EMAIL_IMAP"
        return "FOLDER"

    def _file_type_to_kind(self, file_type: str) -> str:
        """Converte file_type in document kind."""
        mapping = {
            "EML": "EMAIL_BODY",
            "PDF": "PDF_TEXT",
            "XLSX": "XLSX",
            "XLS": "XLS",
            "CSV": "CSV",
        }
        return mapping.get(file_type, "PDF_TEXT")
