"""Parser per file CSV."""

from __future__ import annotations

import csv
import hashlib
from io import StringIO
from pathlib import Path

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


def _get_cell_ref(row: int, col: int) -> str:
    """Converte indici riga/colonna in riferimento cella (es. A1, B2)."""
    result = ""
    col_num = col + 1
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        result = chr(65 + remainder) + result
    return f"{result}{row + 1}"


def _detect_encoding(content: bytes) -> str:
    """Rileva l'encoding del file."""
    encodings_to_try = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
    
    for encoding in encodings_to_try:
        try:
            content.decode(encoding)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue
    
    return "utf-8"


def _detect_delimiter(sample: str) -> str:
    """Rileva il delimitatore del CSV."""
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:  # noqa: BLE001
        comma_count = sample.count(",")
        semicolon_count = sample.count(";")
        tab_count = sample.count("\t")
        
        if tab_count > comma_count and tab_count > semicolon_count:
            return "\t"
        elif semicolon_count > comma_count:
            return ";"
        return ","


class CsvParser:
    """Parser per file CSV."""

    def __init__(self):
        pass

    def parse(self, file_path: Path | str) -> NormalizedInput:
        """Parsa un file CSV."""
        file_path = Path(file_path)
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        return self.parse_bytes(content, filename=file_path.name, file_path=str(file_path))

    def parse_bytes(
        self,
        content: bytes,
        filename: str = "data.csv",
        file_path: str | None = None
    ) -> NormalizedInput:
        """Parsa contenuto CSV da bytes."""
        sha256 = hashlib.sha256(content).hexdigest()
        source = Source(
            filename=filename,
            sha256=sha256,
            file_type=FileType.CSV,
            file_path=file_path,
            file_size_bytes=len(content),
        )
        
        result = NormalizedInput(source=source)
        
        encoding = _detect_encoding(content)
        try:
            text_content = content.decode(encoding)
        except Exception:  # noqa: BLE001
            text_content = content.decode("utf-8", errors="replace")
        
        sample = text_content[:8192]
        delimiter = _detect_delimiter(sample)
        
        try:
            part = self._process_csv(text_content, delimiter, result)
            result.parts.append(part)
        except Exception as e:  # noqa: BLE001
            result.warnings.append(Warning(
                code="CSV-01",
                message=f"Errore nel parsing del file CSV: {e!s}",
                details={"error": str(e)},
            ))
        
        return result

    def _process_csv(
        self,
        text_content: str,
        delimiter: str,
        result: NormalizedInput
    ) -> Part:
        """Processa il contenuto CSV."""
        part = Part(
            part_type=PartType.CSV_DATA,
            mime_type="text/csv",
        )
        
        table = Table()
        text_lines = []
        
        reader = csv.reader(StringIO(text_content), delimiter=delimiter)
        
        for row_idx, row_data in enumerate(reader):
            row_cells: list[Cell] = []
            row_text_parts: list[str] = []
            
            for col_idx, cell_value in enumerate(row_data):
                cell_ref = _get_cell_ref(row_idx, col_idx)
                
                value: str | int | float | None = cell_value.strip() if cell_value else None
                
                if value:
                    try:
                        if "." in value or "," in value:
                            value = float(value.replace(",", "."))
                        else:
                            value = int(value)
                    except ValueError:
                        pass
                
                table_cell = Cell(
                    value=value,
                    raw_value=cell_value if cell_value else None,
                    cell_ref=cell_ref,
                )
                row_cells.append(table_cell)
                
                if cell_value:
                    row_text_parts.append(cell_value)
            
            table.rows.append(row_cells)
            if row_text_parts:
                text_lines.append(delimiter.join(row_text_parts))
        
        header_idx = self._detect_header_row(table.rows)
        table.header_row_index = header_idx
        part.tables = [table]
        
        part.text = "\n".join(text_lines)
        part.compute_sha256(part.text)
        
        part.metadata = {
            "delimiter": delimiter,
            "total_rows": len(table.rows),
        }
        
        return part

    def _detect_header_row(self, rows: list[list[Cell]]) -> int | None:
        """Rileva euristicamente la riga di intestazione."""
        if not rows:
            return None
        
        header_keywords = {
            "item", "qty", "quantity", "price", "amount", "description",
            "code", "sku", "unit", "uom", "line", "total", "product",
            "articolo", "quantità", "prezzo", "importo", "descrizione",
            "codice", "unità", "riga", "totale", "prodotto",
            "name", "id", "date", "number", "type",
        }
        
        first_row = rows[0]
        text_cells = 0
        header_matches = 0
        
        for cell in first_row:
            if cell.value is not None and isinstance(cell.value, str):
                text_cells += 1
                cell_lower = cell.value.lower().strip()
                if cell_lower in header_keywords:
                    header_matches += 1
                for kw in header_keywords:
                    if kw in cell_lower:
                        header_matches += 0.5
                        break
        
        if text_cells > 0 and header_matches >= 1:
            return 0
        
        if text_cells > 0:
            all_text = all(
                isinstance(c.value, str) for c in first_row if c.value is not None
            )
            if all_text and len(rows) > 1:
                has_nums_in_second = False
                for c in rows[1]:
                    if isinstance(c.value, (int, float)):
                        has_nums_in_second = True
                        break
                if has_nums_in_second:
                    return 0
        
        return 0 if rows else None
