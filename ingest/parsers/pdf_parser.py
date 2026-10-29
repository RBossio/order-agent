"""Parser per file PDF usando pdfplumber."""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from ..models import (
    Cell,
    FileType,
    NormalizedInput,
    Part,
    PartType,
    Source,
    Table,
    Warning,
)


class PdfParser:
    """Parser per file PDF."""

    MIN_TEXT_CHARS_PER_PAGE = 50

    def __init__(self):
        pass

    def parse(self, file_path: Path | str) -> NormalizedInput:
        """Parsa un file PDF."""
        file_path = Path(file_path)
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        return self.parse_bytes(content, filename=file_path.name, file_path=str(file_path))

    def parse_bytes(
        self,
        content: bytes,
        filename: str = "document.pdf",
        file_path: str | None = None
    ) -> NormalizedInput:
        """Parsa contenuto PDF da bytes."""
        import pdfplumber
        
        sha256 = hashlib.sha256(content).hexdigest()
        source = Source(
            filename=filename,
            sha256=sha256,
            file_type=FileType.PDF,
            file_path=file_path,
            file_size_bytes=len(content),
        )
        
        result = NormalizedInput(source=source)
        
        buffer = BytesIO(content)
        
        try:
            with pdfplumber.open(buffer) as pdf:
                total_text_chars = 0
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_part = self._process_page(page, page_num, result)
                    result.parts.append(page_part)
                    
                    if page_part.text:
                        total_text_chars += len(page_part.text.strip())
                
                if len(pdf.pages) > 0:
                    avg_chars = total_text_chars / len(pdf.pages)
                    if avg_chars < self.MIN_TEXT_CHARS_PER_PAGE:
                        for part in result.parts:
                            part.needs_ocr = True
                        
                        result.warnings.append(Warning(
                            code="PDF-01",
                            message="PDF sembra essere una scansione, richiede OCR",
                            details={
                                "avg_chars_per_page": avg_chars,
                                "total_pages": len(pdf.pages),
                            }
                        ))
                        
        except Exception as e:
            result.warnings.append(Warning(
                code="PDF-02",
                message=f"Errore nel parsing del PDF: {str(e)}",
                details={"error": str(e)},
            ))
        
        return result

    def _process_page(
        self,
        page: Any,
        page_num: int,
        result: NormalizedInput
    ) -> Part:
        """Processa una singola pagina PDF."""
        part = Part(
            part_type=PartType.PDF_PAGE,
            page_number=page_num,
            mime_type="application/pdf",
        )
        
        try:
            text = page.extract_text() or ""
            part.text = text
        except Exception:
            part.text = ""
        
        try:
            text_layout = page.extract_text(
                layout=True,
                x_density=3,
                y_density=3,
            ) or ""
            part.text_layout = text_layout
        except Exception:
            part.text_layout = part.text
        
        content_for_hash = part.text or ""
        part.compute_sha256(content_for_hash)
        
        tables = self._extract_tables(page, page_num, result)
        part.tables = tables
        
        return part

    def _extract_tables(
        self,
        page: Any,
        page_num: int,
        result: NormalizedInput
    ) -> list[Table]:
        """Estrae tabelle da una pagina."""
        tables = []
        
        try:
            pdf_tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            })
            
            if not pdf_tables:
                pdf_tables = page.extract_tables(table_settings={
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 5,
                    "join_tolerance": 5,
                })
            
            for table_data in pdf_tables or []:
                if not table_data or len(table_data) < 2:
                    continue
                
                table = Table(
                    page_number=page_num,
                )
                
                for row_data in table_data:
                    if row_data is None:
                        continue
                    row = []
                    for cell_value in row_data:
                        cell = Cell(
                            value=cell_value.strip() if isinstance(cell_value, str) else cell_value,
                            raw_value=str(cell_value) if cell_value is not None else None,
                        )
                        row.append(cell)
                    if row:
                        table.rows.append(row)
                
                if table.rows:
                    header_idx = self._detect_header_row(table.rows)
                    table.header_row_index = header_idx
                    tables.append(table)
                    
        except Exception as e:
            result.warnings.append(Warning(
                code="PDF-03",
                message=f"Errore nell'estrazione delle tabelle dalla pagina {page_num}",
                details={"error": str(e), "page": page_num},
            ))
        
        return tables

    def _detect_header_row(self, rows: list[list[Cell]]) -> int | None:
        """Rileva euristicamente la riga di intestazione."""
        if not rows:
            return None
        
        header_keywords = {
            "item", "qty", "quantity", "price", "amount", "description",
            "code", "sku", "unit", "uom", "line", "total", "product",
            "articolo", "quantità", "prezzo", "importo", "descrizione",
            "codice", "unità", "riga", "totale", "prodotto",
        }
        
        for idx, row in enumerate(rows[:3]):
            text_cells = 0
            header_matches = 0
            
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    text_cells += 1
                    if cell.value.lower().strip() in header_keywords:
                        header_matches += 1
            
            if text_cells > 0 and header_matches >= 2:
                return idx
            
            if text_cells > 0 and header_matches >= 1 and text_cells >= len(row) * 0.5:
                return idx
        
        if rows and len(rows) > 1:
            first_row = rows[0]
            all_text = all(
                isinstance(cell.value, str) for cell in first_row if cell.value is not None
            )
            if all_text:
                return 0
        
        return None
