"""
Estrattore principale: NormalizedInput -> VentureOrder.

Pre-elaborazione deterministica prima dell'LLM (Excel/PDF con tabelle).
L'LLM è ripiego e per le email. In caso di disaccordo: REVIEW.
Confidenza tarata da fonte, accordo e controlli — non auto-dichiarata dall'LLM.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema

from .backends import LLMBackend, MockBackend
from .catalog import CatalogMatcher
from .checks import apply_cross_checks
from .confidence import (
    LLM_ONLY,
    REVIEW_THRESHOLD,
    calibrate,
    drop_below_review,
)
from .dates import parse_date_obj, to_iso_date
from .models import (
    ExtractedHeader,
    ExtractedLine,
    ExtractedOrder,
    ExtractedPack,
    ExtractedParty,
    ExtractedTotals,
    ExtractionResult,
    ExtractionWarning,
    FieldConfidence,
    WarningSeverity,
)
from .preprocessor import PreprocessedData, PreprocessedLine, Preprocessor
from .prompts import (
    EXTRACTION_JSON_SCHEMA,
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_prompt,
    build_retry_prompt,
)

_SYNTHETIC_AS_OF = date(2026, 6, 15)


class OrderExtractor:
    """
    Estrattore di ordini da NormalizedInput.

    Combina:
    1. Pre-elaborazione deterministica (tabelle strutturate)
    2. Estrazione LLM solo come ripiego / email
    3. Controlli incrociati e motore regole (REVIEW)
    4. Validazione JSON schema
    """

    def __init__(
        self,
        backend: LLMBackend | None = None,
        max_retries: int = 1,
        validate_output: bool = True,
        catalog: CatalogMatcher | None = None,
        run_rules: bool = True,
        use_llm: bool = True,
    ):
        self.backend = backend or MockBackend()
        self.preprocessor = Preprocessor()
        self.max_retries = max_retries
        self.validate_output = validate_output
        self.catalog = catalog if catalog is not None else CatalogMatcher()
        self.run_rules = run_rules
        self.use_llm = use_llm
        self._engine = None
        self._schema_path = Path(__file__).parent.parent / "schema" / "venture-order.v1.schema.json"

    def extract(self, normalized_input: dict) -> ExtractionResult:
        """Estrae un ordine da un NormalizedInput."""
        start_time = time.time()
        warnings: list[ExtractionWarning] = []
        field_confidences: list[FieldConfidence] = []
        llm_calls = 0
        llm_timeouts = 0
        total_tokens = 0
        preprocessed_fields: list[str] = []
        extracted_json: dict = {"header": {}, "lines": []}
        llm_used = False

        preprocessed = self.preprocessor.preprocess(normalized_input)
        if preprocessed.header and preprocessed.header.po_number:
            preprocessed_fields.append("/header/po_number")
        for idx, line in enumerate(preprocessed.lines):
            if not line.needs_llm:
                preprocessed_fields.append(f"/lines/{idx}")

        file_type = (normalized_input.get("source") or {}).get("file_type", "")
        is_email = file_type == "EML" or bool(normalized_input.get("email_metadata"))
        skip_llm = (not self.use_llm) or ((not is_email) and self._preprocessor_complete(preprocessed))

        if not skip_llm:
            llm_used = True
            extracted_json, llm_calls, llm_timeouts, total_tokens = self._invoke_llm(
                normalized_input, preprocessed, warnings,
            )

        if preprocessed.source_disagreement:
            warnings.append(ExtractionWarning(
                code="EXT-01",
                severity=WarningSeverity.REVIEW,
                message="Allegato e corpo email discordanti: ordine in revisione",
                path="/lines",
            ))

        order = self._build_order(
            extracted_json if llm_used else {"header": {}, "lines": []},
            preprocessed,
            normalized_input,
            field_confidences,
            warnings,
            llm_used=llm_used,
        )

        apply_cross_checks(
            order,
            self.catalog,
            field_confidences,
            warnings,
            as_of=_as_of_for_order(order),
        )

        if self.validate_output:
            warnings.extend(self._validate_order(order))

        document_text = self._build_document_content(normalized_input, preprocessed)
        decision = self._run_rules(
            order, field_confidences, warnings, preprocessed, document_text=document_text,
        )

        if any(w.severity in {WarningSeverity.BLOCK, WarningSeverity.REVIEW} for w in warnings):
            order.status = "NEEDS_REVIEW"
        if decision and decision.get("route") == "REJECT":
            order.status = "REJECTED"
        elif decision and decision.get("route") in {"REVIEW", "REJECT"}:
            order.status = "NEEDS_REVIEW"

        if field_confidences:
            order.overall_confidence = min(fc.confidence for fc in field_confidences)

        extraction_time = int((time.time() - start_time) * 1000)
        return ExtractionResult(
            order=order,
            field_confidences=field_confidences,
            warnings=warnings,
            llm_calls=llm_calls,
            llm_timeouts=llm_timeouts,
            llm_tokens_used=total_tokens,
            extraction_time_ms=extraction_time,
            preprocessed_fields=preprocessed_fields,
            decision=decision,
        )

    def _invoke_llm(
        self,
        normalized_input: dict,
        preprocessed: PreprocessedData,
        warnings: list[ExtractionWarning],
    ) -> tuple[dict, int, int, int]:
        """Chiama l'LLM (con un retry) e restituisce JSON, chiamate, timeout, token."""
        extracted_json: dict = {"header": {}, "lines": []}
        llm_calls = 0
        llm_timeouts = 0
        total_tokens = 0
        parse_error: str | None = None
        document_content = self._build_document_content(normalized_input, preprocessed)
        prompt = build_extraction_prompt(
            document_content,
            preprocessed_lines=self._lines_as_prompt(preprocessed.lines),
            preprocessed_header=self._header_as_prompt(preprocessed.header),
        )
        try:
            llm_response = self.backend.generate(
                prompt=prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                json_schema=EXTRACTION_JSON_SCHEMA,
                temperature=0.0,
                max_tokens=2048,
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
                    max_tokens=2048,
                )
                llm_calls += 1
                total_tokens += retry_response.total_tokens
                extracted_json, parse_error = self._parse_json_response(retry_response.content)
        except Exception as exc:
            parse_error = str(exc)
            if _is_timeout(exc):
                llm_timeouts += 1
            warnings.append(ExtractionWarning(
                code="EXT-02",
                severity=WarningSeverity.BLOCK,
                message=f"Errore LLM: {exc}",
            ))
            extracted_json = {"header": {}, "lines": []}

        if parse_error:
            warnings.append(ExtractionWarning(
                code="EXT-01",
                severity=WarningSeverity.REVIEW,
                message=f"Errore parsing JSON: {parse_error}",
            ))
            if not extracted_json:
                extracted_json = {"header": {}, "lines": []}
        return extracted_json or {"header": {}, "lines": []}, llm_calls, llm_timeouts, total_tokens

    def extract_from_file(self, file_path: Path | str) -> ExtractionResult:
        file_path = Path(file_path)
        with open(file_path, encoding="utf-8") as f:
            normalized_input = json.load(f)
        return self.extract(normalized_input)

    def _preprocessor_complete(self, preprocessed: PreprocessedData) -> bool:
        header = preprocessed.header
        has_po = bool(header and self.preprocessor._looks_like_po(header.po_number))
        has_lines = any(
            line.quantity is not None and (line.description or line.seller_item_code)
            for line in preprocessed.lines
        )
        return has_po and has_lines

    @staticmethod
    def _lines_as_prompt(lines: list[PreprocessedLine]) -> list[dict] | None:
        if not lines:
            return None
        return [
            {
                "line_no": line.row_index,
                "seller_item_code": line.seller_item_code,
                "buyer_item_code": line.buyer_item_code,
                "description": line.description,
                "quantity": line.quantity,
                "uom_raw": line.uom_raw,
                "unit_price": line.unit_price,
            }
            for line in lines
        ]

    @staticmethod
    def _header_as_prompt(header) -> dict | None:
        if header is None:
            return None
        return {
            "po_number": header.po_number,
            "po_date": header.po_date,
            "currency": header.currency,
            "buyer_name": header.buyer_name,
            "requested_delivery_date": header.delivery_date,
        }

    def _build_document_content(
        self,
        normalized_input: dict,
        preprocessed: PreprocessedData,
    ) -> str:
        parts = []
        email_meta = normalized_input.get("email_metadata")
        if email_meta:
            parts.append("=== EMAIL METADATA ===")
            if email_meta.get("from_name"):
                parts.append(
                    f"From: {email_meta['from_name']} <{email_meta.get('from_address', '')}>"
                )
            elif email_meta.get("from_address"):
                parts.append(f"From: {email_meta['from_address']}")
            if email_meta.get("subject"):
                parts.append(f"Subject: {email_meta['subject']}")
            parts.append("")

        if preprocessed.unstructured_text:
            parts.append(preprocessed.unstructured_text)

        for part in normalized_input.get("parts", []):
            if part.get("part_type") in ("EXCEL_SHEET", "CSV_DATA"):
                for table in part.get("tables", []):
                    table_text = self._table_to_text(table)
                    if table_text:
                        parts.append(f"\n=== TABELLA ({part.get('sheet_name', 'Foglio')}) ===")
                        parts.append(table_text)
        return "\n".join(parts)

    def _table_to_text(self, table: dict) -> str:
        rows = table.get("rows", [])
        if not rows:
            return ""
        lines = []
        for row in rows[:30]:
            cells = []
            for cell in row:
                val = cell.get("value", "") if isinstance(cell, dict) else cell
                cells.append(str(val) if val is not None else "")
            lines.append(" | ".join(cells))
        if len(rows) > 30:
            lines.append(f"... ({len(rows) - 30} righe aggiuntive)")
        return "\n".join(lines)

    def _parse_json_response(self, content: str) -> tuple[dict | None, str | None]:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        try:
            return json.loads(content), None
        except json.JSONDecodeError as exc:
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    return json.loads(json_match.group()), None
                except json.JSONDecodeError:
                    pass
            return None, f"JSON non valido: {exc}"

    def _build_order(
        self,
        extracted_json: dict,
        preprocessed: PreprocessedData,
        normalized_input: dict,
        field_confidences: list[FieldConfidence],
        warnings: list[ExtractionWarning],
        *,
        llm_used: bool,
    ) -> ExtractedOrder:
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

        llm_header = (extracted_json or {}).get("header") or {}
        pre_header = preprocessed.header

        po_number, po_src, po_agreed = _pick_value(
            pre_header.po_number if pre_header else None,
            llm_header.get("po_number"),
            llm_used=llm_used,
            looks_ok=self.preprocessor._looks_like_po,
        )
        po_date_raw, date_src, date_agreed = _pick_value(
            pre_header.po_date if pre_header else None,
            llm_header.get("po_date"),
            llm_used=llm_used,
        )
        currency, cur_src, cur_agreed = _pick_value(
            pre_header.currency if pre_header else None,
            llm_header.get("currency"),
            llm_used=llm_used,
        )
        currency_from_doc = currency not in (None, "")
        delivery_raw, del_src, del_agreed = _pick_value(
            pre_header.delivery_date if pre_header else None,
            llm_header.get("requested_delivery_date"),
            llm_used=llm_used,
        )

        if po_agreed is False:
            warnings.append(ExtractionWarning(
                code="EXT-01",
                severity=WarningSeverity.REVIEW,
                message="Numero PO discordante tra preprocessor e LLM",
                path="/header/po_number",
            ))
        if date_agreed is False:
            warnings.append(ExtractionWarning(
                code="EXT-01",
                severity=WarningSeverity.REVIEW,
                message="Data ordine discordante tra preprocessor e LLM",
                path="/header/po_date",
            ))

        if not po_number:
            warnings.append(ExtractionWarning(
                code="HDR-01",
                severity=WarningSeverity.BLOCK,
                message="Numero PO mancante",
                path="/header/po_number",
            ))
            po_number = "UNKNOWN"

        po_date = to_iso_date(po_date_raw) or po_date_raw
        if not po_date:
            warnings.append(ExtractionWarning(
                code="HDR-02",
                severity=WarningSeverity.REVIEW,
                message="Data ordine mancante",
                path="/header/po_date",
            ))
            po_date = "1970-01-01"

        delivery_date = to_iso_date(delivery_raw) or delivery_raw

        order.header = ExtractedHeader(
            po_number=po_number,
            po_date=po_date,
            currency=currency or "",
            requested_delivery_date=delivery_date,
            buyer_reference=llm_header.get("buyer_reference"),
            payment_terms_text=(
                (pre_header.payment_terms if pre_header else None)
                or llm_header.get("payment_terms")
            ),
            ship_via=llm_header.get("ship_via"),
            notes=llm_header.get("notes"),
        )

        _add_conf(
            field_confidences, "/header/po_number", po_src, po_agreed,
            present=po_number != "UNKNOWN", snippet=po_number,
        )
        _add_conf(
            field_confidences, "/header/po_date", date_src, date_agreed,
            present=po_date != "1970-01-01", snippet=str(po_date_raw) if po_date_raw else None,
        )
        if po_date_raw and not _is_iso_date(po_date_raw):
            _cap_confidence(field_confidences, "/header/po_date", LLM_ONLY)
        _add_conf(
            field_confidences, "/header/requested_delivery_date", del_src, del_agreed,
            present=bool(delivery_date), snippet=str(delivery_raw) if delivery_raw else None,
        )
        if delivery_raw and not _is_iso_date(delivery_raw):
            _cap_confidence(field_confidences, "/header/requested_delivery_date", LLM_ONLY)

        buyer_name = (pre_header.buyer_name if pre_header else None)
        llm_buyer = (extracted_json or {}).get("buyer") or {}
        if not buyer_name:
            buyer_name = llm_buyer.get("name")

        customer_hint = None
        order.buyer = ExtractedParty(
            name=buyer_name,
            code_on_document=llm_buyer.get("code"),
            contact_email=llm_buyer.get("contact_email"),
            contact_name=llm_buyer.get("contact_name"),
        )
        if llm_buyer.get("address"):
            order.buyer.address_line1 = llm_buyer["address"]

        ship_to_data = (extracted_json or {}).get("ship_to") or {}
        ship_name = (pre_header.ship_to_name if pre_header else None) or ship_to_data.get("name")
        if ship_name or ship_to_data:
            order.ship_to = ExtractedParty(name=ship_name)
            if ship_to_data.get("address"):
                addr = ship_to_data["address"]
                if isinstance(addr, dict):
                    order.ship_to.address_line1 = addr.get("line1")
                    order.ship_to.address_city = addr.get("city")
                    order.ship_to.address_postal_code = addr.get("postal_code")
                    order.ship_to.address_country = addr.get("country")
                else:
                    order.ship_to.address_line1 = str(addr)

        order.lines = self._build_lines(
            (extracted_json or {}).get("lines") or [],
            preprocessed.lines,
            field_confidences,
            warnings,
            llm_used=llm_used,
            customer_ref_holder={"ref": customer_hint},
        )

        if not order.lines:
            warnings.append(ExtractionWarning(
                code="LIN-01",
                severity=WarningSeverity.BLOCK,
                message="Nessuna riga ordine estratta",
            ))

        item_customer = None
        for line in order.lines:
            resolution = line.resolution or {}
            if resolution.get("method") == "XREF":
                hit = self.catalog.classify_item_code(
                    line.buyer_item_code or line.seller_item_code
                )
                if hit.customer_ref:
                    item_customer = hit.customer_ref
                    break

        resolved = self.catalog.resolve_buyer(
            buyer_name,
            order.source_from_address,
            item_customer,
        )
        if resolved and order.buyer:
            order.buyer.resolved = resolved
            code_only = (
                resolved.get("method") == "CODE"
                and not buyer_name
                and not order.buyer.address_line1
            )
            _add_conf(
                field_confidences, "/buyer",
                "llm" if code_only else "preprocessor", None,
                present=True, snippet=buyer_name,
            )
            _add_conf(
                field_confidences, "/buyer/resolved",
                "llm" if code_only else "preprocessor", None,
                present=True,
            )
        elif order.buyer:
            _add_conf(
                field_confidences, "/buyer", "llm" if llm_buyer else "preprocessor", None,
                present=bool(buyer_name), snippet=buyer_name,
            )

        currency, cur_src = self._resolve_currency(
            currency, currency_from_doc, cur_src, resolved,
        )
        if order.header:
            order.header.currency = currency
        _add_conf(
            field_confidences, "/header/currency", cur_src, cur_agreed,
            present=bool(currency),
            snippet=currency if currency_from_doc else None,
        )

        if order.ship_to:
            customer_ref = (resolved or {}).get("erp_partner_ref")
            ship_resolved = self.catalog.resolve_ship_to(order.ship_to.name, customer_ref)
            if ship_resolved:
                order.ship_to.resolved = ship_resolved

        totals_data = (extracted_json or {}).get("totals") or {}
        total = (
            (pre_header.total_amount if pre_header else None)
            or preprocessed.total_amount
            or totals_data.get("total")
        )
        subtotal = totals_data.get("subtotal")
        if total is not None or subtotal is not None:
            order.totals = ExtractedTotals(
                lines_amount_declared=subtotal,
                tax_amount_declared=totals_data.get("tax"),
                total_amount_declared=total,
            )

        if preprocessed.source_disagreement:
            for fc in field_confidences:
                if fc.path.startswith("/lines/"):
                    fc.confidence = min(fc.confidence, calibrate("preprocessor", agreed=False))
                    drop_below_review(field_confidences, fc.path)

        return order

    def _resolve_currency(
        self,
        currency: str | None,
        from_doc: bool,
        source: str,
        resolved: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """Valuta dal documento, altrimenti anagrafica (motivata), altrimenti default basso."""
        if from_doc and currency:
            return currency, source
        customer_currency = None
        if resolved and self.catalog.provider is not None:
            ref = resolved.get("erp_partner_ref")
            if ref:
                customer = self.catalog.provider.get_customer_by_ref(str(ref))
                if customer is not None and customer.currency:
                    customer_currency = customer.currency
        if customer_currency:
            return customer_currency, "catalog"
        return "USD", "default"

    def _build_lines(
        self,
        llm_lines: list[dict],
        preprocessed_lines: list[PreprocessedLine],
        field_confidences: list[FieldConfidence],
        warnings: list[ExtractionWarning],
        *,
        llm_used: bool,
        customer_ref_holder: dict,
    ) -> list[ExtractedLine]:
        usable_preprocessed = [
            pl for pl in preprocessed_lines
            if pl.description and (pl.quantity is not None or pl.needs_llm)
        ]

        final_lines: list[ExtractedLine] = []
        if usable_preprocessed:
            llm_by_code = _index_llm_lines(llm_lines)
            for idx, pl in enumerate(usable_preprocessed):
                llm_match = _match_llm_line(pl, llm_by_code, llm_lines, idx) if llm_used else None
                line, disagreements = self._merge_line(pl, llm_match, idx)
                self._attach_resolution(line, customer_ref_holder.get("ref"))
                final_lines.append(line)
                src = "preprocessor"
                agreed: bool | None = None
                if llm_used and llm_match is not None:
                    agreed = not disagreements
                    src = "agreed" if agreed else "preprocessor"
                    for path, message in disagreements:
                        warnings.append(ExtractionWarning(
                            code="EXT-01",
                            severity=WarningSeverity.REVIEW,
                            message=message,
                            path=path,
                        ))
                elif llm_used:
                    src = "preprocessor"
                conf = calibrate(src, agreed=agreed)
                if pl.needs_llm and line.quantity is None:
                    conf = calibrate("llm", agreed=False)
                self._line_confidences(field_confidences, idx, line, conf, src)
                if disagreements:
                    for path, _ in disagreements:
                        drop_below_review(field_confidences, path)

        elif llm_lines:
            for idx, ll in enumerate(llm_lines):
                description = ll.get("description") or ""
                if not description:
                    continue
                quantity = ll.get("quantity")
                if quantity is None:
                    warnings.append(ExtractionWarning(
                        code="QTY-01",
                        severity=WarningSeverity.BLOCK,
                        message=f"Quantità mancante per riga {idx + 1}",
                        path=f"/lines/{idx}/quantity",
                    ))
                    quantity = 1
                pack = None
                if ll.get("pack_info"):
                    pack = self._parse_pack_info(ll["pack_info"])
                line = ExtractedLine(
                    line_no=ll.get("line_no", idx + 1),
                    description=description,
                    quantity=float(quantity),
                    uom_raw=ll.get("uom_raw") or "EA",
                    seller_item_code=ll.get("seller_item_code"),
                    buyer_item_code=ll.get("buyer_item_code"),
                    unit_price=ll.get("unit_price"),
                    line_amount=ll.get("line_amount"),
                    pack=pack,
                    notes=ll.get("notes"),
                    confidence=calibrate("llm"),
                )
                self._classify_line_codes(line)
                self._attach_resolution(line, customer_ref_holder.get("ref"))
                final_lines.append(line)
                self._line_confidences(
                    field_confidences, idx, line, calibrate("llm"), "llm",
                )

        return final_lines

    def _merge_line(
        self,
        pl: PreprocessedLine,
        llm_match: dict | None,
        idx: int,
    ) -> tuple[ExtractedLine, list[tuple[str, str]]]:
        disagreements: list[tuple[str, str]] = []
        seller = pl.seller_item_code
        buyer = pl.buyer_item_code
        description = pl.description or ""
        quantity = pl.quantity
        uom_raw = pl.uom_raw or "EA"
        unit_price = pl.unit_price
        line_amount = pl.line_amount

        if llm_match:
            def _maybe(pre_val, llm_val, path, label, numeric=False):
                if llm_val in (None, "") or pre_val in (None, ""):
                    return pre_val if pre_val not in (None, "") else llm_val
                if numeric:
                    try:
                        if abs(float(pre_val) - float(llm_val)) < 1e-6:
                            return pre_val
                    except (TypeError, ValueError):
                        pass
                    disagreements.append((
                        path,
                        f"Riga {idx + 1}: {label} discordante tra preprocessor e LLM",
                    ))
                    return pre_val
                if _norm(pre_val) == _norm(llm_val):
                    return pre_val
                disagreements.append((
                    path,
                    f"Riga {idx + 1}: {label} discordante tra preprocessor e LLM",
                ))
                return pre_val

            seller = _maybe(
                seller, llm_match.get("seller_item_code"),
                f"/lines/{idx}/seller_item_code", "codice",
            )
            quantity = _maybe(
                quantity, llm_match.get("quantity"),
                f"/lines/{idx}/quantity", "quantità", numeric=True,
            )
            uom_raw = _maybe(
                uom_raw, llm_match.get("uom_raw"),
                f"/lines/{idx}/uom_raw", "UoM",
            ) or "EA"
            unit_price = _maybe(
                unit_price, llm_match.get("unit_price"),
                f"/lines/{idx}/unit_price", "prezzo", numeric=True,
            )
            if not description:
                description = llm_match.get("description") or ""
            if buyer is None:
                buyer = llm_match.get("buyer_item_code")
            if line_amount is None:
                line_amount = llm_match.get("line_amount")

        if quantity is None:
            quantity = 1

        line = ExtractedLine(
            line_no=idx + 1,
            description=description,
            quantity=float(quantity),
            uom_raw=uom_raw,
            seller_item_code=seller,
            buyer_item_code=buyer,
            unit_price=unit_price,
            line_amount=line_amount,
            confidence=calibrate("preprocessor", agreed=not disagreements if llm_match else None),
        )
        self._classify_line_codes(line)
        return line, disagreements

    def _classify_line_codes(self, line: ExtractedLine) -> None:
        """Se il codice stampato è un xref, copialo anche su buyer_item_code.

        Non sovrascrivere seller_item_code con lo SKU di catalogo: il codice
        del documento resta quello stampato (serve al matching in eval).
        """
        code = line.seller_item_code
        if not code:
            return
        hit = self.catalog.classify_item_code(code)
        if hit.role == "buyer" and not line.buyer_item_code:
            line.buyer_item_code = code

    def _attach_resolution(self, line: ExtractedLine, customer_ref: str | None) -> None:
        line.resolution = self.catalog.resolve_line(
            line.seller_item_code,
            line.buyer_item_code,
            customer_ref=customer_ref,
            uom_raw=line.uom_raw,
            quantity=line.quantity,
        )
        if line.uom_raw:
            from ventureorder.rules.access import normalize_uom
            line.uom = normalize_uom(line.uom_raw) or line.uom_raw

    def _line_confidences(
        self,
        field_confidences: list[FieldConfidence],
        idx: int,
        line: ExtractedLine,
        conf: float,
        source: str,
    ) -> None:
        field_confidences.append(FieldConfidence(
            path=f"/lines/{idx}",
            confidence=conf,
            source=source,
        ))
        for field_name, value in (
            ("quantity", line.quantity),
            ("seller_item_code", line.seller_item_code),
            ("buyer_item_code", line.buyer_item_code),
            ("uom", line.uom),
            ("uom_raw", line.uom_raw),
            ("unit_price", line.unit_price),
        ):
            # buyer_item_code è opzionale: assente ≠ confidenza 0 (EXT-01).
            if field_name == "buyer_item_code" and value in (None, ""):
                continue
            field_confidences.append(FieldConfidence(
                path=f"/lines/{idx}/{field_name}",
                confidence=conf if value not in (None, "") else 0.0,
                source=source,
                snippet=str(value) if value not in (None, "") else None,
            ))

    def _parse_pack_info(self, pack_info: str) -> ExtractedPack | None:
        if not pack_info:
            return None
        pack = ExtractedPack(raw=pack_info)
        match = re.match(r"(\d+)/(\d+(?:\.\d+)?)\s*([A-Z]+)", pack_info, re.IGNORECASE)
        if match:
            pack.inner_count = float(match.group(1))
            pack.inner_size = float(match.group(2))
            pack.inner_uom = match.group(3).upper()
            return pack
        match = re.match(r"(\d+)/([A-Z]+)", pack_info, re.IGNORECASE)
        if match:
            pack.inner_count = float(match.group(1))
            pack.inner_size = 1
            pack.inner_uom = match.group(2).upper()
            return pack
        return pack

    def _run_rules(
        self,
        order: ExtractedOrder,
        field_confidences: list[FieldConfidence],
        warnings: list[ExtractionWarning],
        preprocessed: PreprocessedData,
        document_text: str | None = None,
    ) -> dict | None:
        if not self.run_rules:
            return None
        try:
            from ventureorder.rules import ValidationEngine
            from ventureorder.rules.models import Severity
        except ImportError:
            return None

        if self._engine is None:
            self._engine = ValidationEngine(
                reference_data=self.catalog.provider,
                as_of=_SYNTHETIC_AS_OF,
            )

        vof = ExtractionResult(
            order=order,
            field_confidences=field_confidences,
            warnings=warnings,
        ).to_dict()
        as_of = _as_of_for_order(order)
        try:
            if self.catalog.provider is not None:
                from ventureorder.match.pipeline import apply_matches

                apply_matches(
                    vof,
                    self.catalog.provider,
                    overwrite=False,
                    thresholds=self._engine.thresholds,
                )
            result = self._engine.validate(
                vof,
                document_text=document_text or preprocessed.unstructured_text or None,
                as_of=as_of,
                llm_schema_valid=True,
            )
        except Exception:
            return None

        seen = {(w.code, w.path) for w in warnings}
        for issue in result.issues:
            if issue.severity not in {Severity.BLOCK, Severity.REVIEW}:
                continue
            key = (issue.rule_id, issue.json_pointer)
            if key in seen:
                continue
            seen.add(key)
            warnings.append(ExtractionWarning(
                code=issue.rule_id,
                severity=WarningSeverity(issue.severity.value),
                message=issue.message,
                path=issue.json_pointer,
            ))
            if issue.json_pointer:
                drop_below_review(field_confidences, issue.json_pointer)

        # Re-applica EXT-01: se un controllo ha abbassato la confidenza, resta sotto soglia.
        for fc in field_confidences:
            if fc.confidence < REVIEW_THRESHOLD and fc.path:
                already = any(w.path == fc.path and w.code == "EXT-01" for w in warnings)
                if not already and _is_critical_path(fc.path):
                    warnings.append(ExtractionWarning(
                        code="EXT-01",
                        severity=WarningSeverity.REVIEW,
                        message=(
                            f"Campo critico '{fc.path}' con confidenza "
                            f"{fc.confidence:.0%} (< {REVIEW_THRESHOLD:.0%})"
                        ),
                        path=fc.path,
                    ))

        return {
            "score": round(result.score, 4),
            "route": result.decision.value,
            "reasons": list(result.reasons),
        }

    def _validate_order(self, order: ExtractedOrder) -> list[ExtractionWarning]:
        warnings: list[ExtractionWarning] = []
        if not self._schema_path.exists():
            return warnings
        try:
            with open(self._schema_path) as handle:
                schema = json.load(handle)
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
        except (jsonschema.exceptions.SchemaError, KeyError, TypeError):
            pass
        return warnings

    def _infer_channel(self, file_type: str) -> str:
        if file_type == "EML":
            return "EMAIL_IMAP"
        return "FOLDER"

    def _file_type_to_kind(self, file_type: str) -> str:
        mapping = {
            "EML": "EMAIL_BODY",
            "PDF": "PDF_TEXT",
            "XLSX": "XLSX",
            "XLS": "XLS",
            "CSV": "CSV",
        }
        return mapping.get(file_type, "PDF_TEXT")


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "").replace(" ", "")


def _values_equal(left, right) -> bool:
    if left in (None, "") or right in (None, ""):
        return not (left not in (None, "") and right not in (None, ""))
    if isinstance(left, int | float) or isinstance(right, int | float):
        try:
            return abs(float(left) - float(right)) < 1e-6
        except (TypeError, ValueError):
            return False
    left_iso, right_iso = to_iso_date(left), to_iso_date(right)
    if left_iso and right_iso:
        return left_iso == right_iso
    return _norm(left) == _norm(right)


def _pick_value(
    pre_val,
    llm_val,
    *,
    llm_used: bool,
    looks_ok=None,
):
    """Sceglie preprocessor vs LLM. Ritorna (valore, source, agreed|None)."""
    pre_ok = pre_val not in (None, "")
    llm_ok = llm_used and llm_val not in (None, "")
    if looks_ok:
        pre_ok = pre_ok and looks_ok(pre_val)
        llm_ok = llm_ok and looks_ok(llm_val)
    if pre_ok and llm_ok:
        if _values_equal(pre_val, llm_val):
            return pre_val, "agreed", True
        return pre_val, "preprocessor", False
    if pre_ok:
        return pre_val, "preprocessor", None
    if llm_ok:
        return llm_val, "llm", None
    fallback = pre_val or llm_val
    if looks_ok and fallback not in (None, "") and not looks_ok(fallback):
        return None, "preprocessor", None
    source = "llm" if llm_used and llm_val not in (None, "") else "preprocessor"
    return fallback, source, None


def _add_conf(
    fields: list[FieldConfidence],
    path: str,
    source: str,
    agreed: bool | None,
    *,
    present: bool,
    snippet: str | None = None,
) -> None:
    fields.append(FieldConfidence(
        path=path,
        confidence=calibrate(source, agreed=agreed, present=present),
        source=source,
        snippet=snippet,
    ))


def _index_llm_lines(llm_lines: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for line in llm_lines:
        for key in (line.get("seller_item_code"), line.get("buyer_item_code")):
            token = _norm(key)
            if token:
                indexed[token] = line
    return indexed


def _match_llm_line(
    pl: PreprocessedLine,
    indexed: dict[str, dict],
    llm_lines: list[dict],
    idx: int,
) -> dict | None:
    for key in (pl.seller_item_code, pl.buyer_item_code):
        token = _norm(key)
        if token and token in indexed:
            return indexed[token]
    if idx < len(llm_lines):
        return llm_lines[idx]
    return None


def _as_of_for_order(order: ExtractedOrder) -> date:
    if order.header:
        parsed = parse_date_obj(order.header.po_date)
        if parsed is not None and parsed.year >= 2020:
            return parsed
    return _SYNTHETIC_AS_OF


def _is_iso_date(value: object) -> bool:
    text = str(value).strip()
    return len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[:10] == to_iso_date(text)


def _cap_confidence(fields: list[FieldConfidence], path: str, maximum: float) -> None:
    for field in fields:
        if field.path == path:
            field.confidence = min(field.confidence, maximum)
            return


def _is_timeout(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text


def _is_critical_path(path: str) -> bool:
    if path in {
        "/header/po_number", "/header/currency",
        "/buyer", "/buyer/name", "/buyer/resolved",
    }:
        return True
    return any(
        path.endswith(suffix)
        for suffix in (
            "/quantity", "/seller_item_code", "/buyer_item_code",
            "/uom", "/uom_raw", "/unit_price",
        )
    )
