"""Parser per i vari formati di file."""

from .eml_parser import EmlParser
from .pdf_parser import PdfParser
from .excel_parser import ExcelParser
from .csv_parser import CsvParser

__all__ = ["EmlParser", "PdfParser", "ExcelParser", "CsvParser"]
