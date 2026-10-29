"""Parser per i vari formati di file."""

from .csv_parser import CsvParser
from .eml_parser import EmlParser
from .excel_parser import ExcelParser
from .pdf_parser import PdfParser

__all__ = ["CsvParser", "EmlParser", "ExcelParser", "PdfParser"]
