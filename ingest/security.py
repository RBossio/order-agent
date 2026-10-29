"""Modulo di sicurezza per validazione e sanificazione dell'input."""

from __future__ import annotations

import email.header
import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath
from typing import BinaryIO


class DetectedFileType(str, Enum):
    """Tipi di file rilevati dai magic number."""
    PDF = "PDF"
    XLSX = "XLSX"
    XLS = "XLS"
    XLSM = "XLSM"
    ZIP = "ZIP"
    CSV = "CSV"
    EML = "EML"
    TEXT = "TEXT"
    EXECUTABLE_PE = "EXECUTABLE_PE"
    EXECUTABLE_ELF = "EXECUTABLE_ELF"
    EXECUTABLE_MACHO = "EXECUTABLE_MACHO"
    EXECUTABLE_SCRIPT = "EXECUTABLE_SCRIPT"
    OLE2 = "OLE2"
    UNKNOWN = "UNKNOWN"


@dataclass
class FileTypeResult:
    """Risultato del rilevamento tipo file."""
    detected_type: DetectedFileType
    confidence: str  # "high", "medium", "low"
    magic_bytes: bytes | None = None
    details: str | None = None


# Magic numbers per rilevamento tipo file
MAGIC_PDF = b"%PDF"
MAGIC_ZIP = b"PK\x03\x04"
MAGIC_OLE2 = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
MAGIC_PE = b"MZ"
MAGIC_ELF = b"\x7fELF"
MAGIC_MACHO_32 = b"\xFE\xED\xFA\xCE"
MAGIC_MACHO_64 = b"\xFE\xED\xFA\xCF"
MAGIC_MACHO_32_REV = b"\xCE\xFA\xED\xFE"
MAGIC_MACHO_64_REV = b"\xCF\xFA\xED\xFE"

# Nomi riservati Windows (case insensitive)
WINDOWS_RESERVED_NAMES = frozenset([
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
])

# Caratteri non consentiti nei nomi file
INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*\x00')

# Pattern shebang per script eseguibili
SHEBANG_PATTERN = re.compile(rb'^#!\s*/(?:usr/(?:local/)?)?bin/')


def detect_file_type(content: bytes | BinaryIO, read_size: int = 8192) -> FileTypeResult:
    """
    Rileva il tipo di file dai magic number (primi byte).

    Args:
        content: Contenuto del file (bytes o file-like object)
        read_size: Quanti byte leggere per l'analisi

    Returns:
        FileTypeResult con tipo rilevato e confidenza
    """
    if isinstance(content, bytes):
        header = content[:read_size]
    else:
        pos = content.tell()
        header = content.read(read_size)
        content.seek(pos)

    if len(header) < 4:
        return FileTypeResult(DetectedFileType.UNKNOWN, "low", details="File troppo piccolo")

    # PDF: %PDF
    if header.startswith(MAGIC_PDF):
        return FileTypeResult(DetectedFileType.PDF, "high", MAGIC_PDF, "Magic number PDF trovato")

    # Eseguibili PE (Windows)
    if header.startswith(MAGIC_PE):
        if len(header) > 64:
            pe_offset = struct.unpack_from("<I", header, 60)[0] if len(header) > 63 else 0
            if pe_offset > 0 and pe_offset < len(header) - 4:  # noqa: SIM102
                if header[pe_offset:pe_offset + 4] == b"PE\x00\x00":
                    return FileTypeResult(
                        DetectedFileType.EXECUTABLE_PE, "high", MAGIC_PE,
                        "Eseguibile Windows PE"
                    )
        return FileTypeResult(
            DetectedFileType.EXECUTABLE_PE, "medium", MAGIC_PE,
            "Possibile eseguibile Windows"
        )

    # Eseguibili ELF (Linux)
    if header.startswith(MAGIC_ELF):
        return FileTypeResult(
            DetectedFileType.EXECUTABLE_ELF, "high", MAGIC_ELF,
            "Eseguibile Linux ELF"
        )

    # Eseguibili Mach-O (macOS)
    if header[:4] in (MAGIC_MACHO_32, MAGIC_MACHO_64, MAGIC_MACHO_32_REV, MAGIC_MACHO_64_REV):
        return FileTypeResult(
            DetectedFileType.EXECUTABLE_MACHO, "high", header[:4],
            "Eseguibile macOS Mach-O"
        )

    # Script con shebang
    if SHEBANG_PATTERN.match(header):
        return FileTypeResult(
            DetectedFileType.EXECUTABLE_SCRIPT, "high", header[:32],
            "Script eseguibile con shebang"
        )

    # OLE2 (può essere .xls, .doc, .ppt, ecc.)
    if header.startswith(MAGIC_OLE2):
        ole_subtype = _detect_ole2_subtype(content if isinstance(content, bytes) else None)
        if ole_subtype == "xls":
            return FileTypeResult(DetectedFileType.XLS, "high", MAGIC_OLE2, "File Excel .xls (OLE2)")
        return FileTypeResult(DetectedFileType.OLE2, "medium", MAGIC_OLE2, "File OLE2 (tipo specifico sconosciuto)")

    # ZIP (può essere .xlsx, .xlsm, .docx, .zip, ecc.)
    if header.startswith(MAGIC_ZIP):
        zip_subtype = _detect_zip_subtype(content if isinstance(content, bytes) else None)
        if zip_subtype == "xlsx":
            return FileTypeResult(DetectedFileType.XLSX, "high", MAGIC_ZIP, "File Excel .xlsx (OOXML)")
        elif zip_subtype == "xlsm":
            return FileTypeResult(DetectedFileType.XLSM, "high", MAGIC_ZIP, "File Excel .xlsm con macro (OOXML)")
        return FileTypeResult(DetectedFileType.ZIP, "medium", MAGIC_ZIP, "File ZIP generico")

    # Testo/CSV/EML - euristica
    text_result = _detect_text_type(header)
    if text_result:
        return text_result

    return FileTypeResult(DetectedFileType.UNKNOWN, "low", header[:8], "Tipo file non riconosciuto")


def _detect_ole2_subtype(content: bytes | None) -> str | None:
    """
    Rileva il sottotipo di un file OLE2.
    Per ora restituisce 'xls' se sembra un file Excel.
    """
    if content is None:
        return None

    # Cerca marker specifici di Excel nel contenuto
    # Il Workbook stream in OLE2 ha specifici marker
    if b"Workbook" in content[:4096] or b"\x09\x08\x10\x00" in content[:512]:
        return "xls"

    return None


def _detect_zip_subtype(content: bytes | None) -> str | None:
    """
    Rileva il sottotipo di un file ZIP (OOXML).
    Verifica [Content_Types].xml per determinare xlsx vs xlsm.
    """
    if content is None:
        return None

    try:
        with zipfile.ZipFile(BytesIO(content), "r") as zf:
            if "[Content_Types].xml" not in zf.namelist():
                return None

            content_types = zf.read("[Content_Types].xml").decode("utf-8", errors="replace")

            # xlsm ha macro (vbaProject.bin)
            if "vbaProject.bin" in content_types or "application/vnd.ms-office.vbaProject" in content_types:
                return "xlsm"

            # xlsx normale
            if "spreadsheetml" in content_types.lower() or "application/vnd.openxmlformats-officedocument.spreadsheetml" in content_types:
                return "xlsx"

    except (zipfile.BadZipFile, OSError, KeyError):
        pass

    return None


def _detect_text_type(header: bytes) -> FileTypeResult | None:
    """
    Rileva se il contenuto è testo (CSV, EML, altro testo).
    """
    # Prova a decodificare come testo
    try:
        text = header.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = header.decode("latin-1")
        except UnicodeDecodeError:
            return None

    # Verifica se è prevalentemente testo stampabile
    printable_ratio = sum(1 for c in text if c.isprintable() or c in "\n\r\t") / len(text) if text else 0
    if printable_ratio < 0.85:
        return None

    # EML: cerca header email tipici
    eml_patterns = [
        r"^From:\s*",
        r"^To:\s*",
        r"^Subject:\s*",
        r"^Date:\s*",
        r"^MIME-Version:\s*",
        r"^Content-Type:\s*",
        r"^Message-ID:\s*",
        r"^Received:\s*",
    ]
    eml_matches = sum(1 for p in eml_patterns if re.search(p, text, re.MULTILINE | re.IGNORECASE))
    if eml_matches >= 3:
        return FileTypeResult(DetectedFileType.EML, "high", None, "File email (EML)")

    # CSV: cerca pattern tabellari con delimitatori
    lines = text.split("\n")[:20]
    if len(lines) >= 2:
        # Conta delimitatori comuni
        delimiters = {",": 0, ";": 0, "\t": 0, "|": 0}
        for line in lines:
            for d in delimiters:
                delimiters[d] += line.count(d)

        max_delimiter = max(delimiters.values())
        if max_delimiter >= len(lines) * 2:  # almeno 2 delimitatori per riga in media
            return FileTypeResult(DetectedFileType.CSV, "medium", None, "Probabile file CSV")

    return FileTypeResult(DetectedFileType.TEXT, "low", None, "File di testo generico")


def check_zip_bomb(content: bytes, max_decompressed_size: int) -> tuple[bool, int, str]:
    """
    Verifica se un file ZIP/XLSX è una zip bomb.

    Args:
        content: Contenuto del file ZIP
        max_decompressed_size: Dimensione massima consentita dopo decompressione

    Returns:
        Tuple (is_safe, estimated_size, message)
    """
    try:
        with zipfile.ZipFile(BytesIO(content), "r") as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())

            if total_uncompressed > max_decompressed_size:
                return (
                    False,
                    total_uncompressed,
                    f"Dimensione decompressa ({total_uncompressed:,} bytes) supera il limite ({max_decompressed_size:,} bytes)"
                )

            # Controllo ratio compressione sospetta
            compressed_size = len(content)
            if compressed_size > 0:
                ratio = total_uncompressed / compressed_size
                if ratio > 100:  # Ratio di compressione > 100:1 è sospetto
                    return (
                        False,
                        total_uncompressed,
                        f"Ratio di compressione sospetto ({ratio:.1f}:1)"
                    )

            return (True, total_uncompressed, "OK")

    except zipfile.BadZipFile as e:
        return (False, 0, f"File ZIP corrotto: {e}")
    except Exception as e:  # noqa: BLE001
        return (False, 0, f"Errore verifica ZIP: {e}")


def sanitize_filename(
    filename: str,
    max_length: int = 255,
    decode_rfc2231: bool = True,
    decode_rfc2047: bool = True,
) -> tuple[str, list[str]]:
    """
    Sanifica un nome file per uso sicuro.

    Operazioni:
    - Decodifica RFC 2231 (parametri header email)
    - Decodifica RFC 2047 (parole codificate nei nomi file)
    - Normalizzazione Unicode (NFC)
    - Rimozione path traversal (../, percorsi assoluti)
    - Rimozione caratteri di controllo
    - Gestione nomi riservati Windows
    - Troncamento a lunghezza massima

    Args:
        filename: Nome file originale
        max_length: Lunghezza massima consentita
        decode_rfc2231: Se decodificare RFC 2231
        decode_rfc2047: Se decodificare RFC 2047

    Returns:
        Tuple (nome_sanificato, lista_warning)
    """
    if not filename:
        return ("unnamed", ["Nome file vuoto sostituito con 'unnamed'"])

    warnings: list[str] = []
    result = filename

    # Decodifica RFC 2047 (es. =?utf-8?B?...?=)
    if decode_rfc2047 and ("=?" in result and "?=" in result):
        try:
            decoded_parts = email.header.decode_header(result)
            decoded_name = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    decoded_name += part.decode(encoding or "utf-8", errors="replace")
                else:
                    decoded_name += part
            if decoded_name != result:
                warnings.append(f"Decodificato RFC 2047: '{filename}' -> '{decoded_name}'")
                result = decoded_name
        except Exception:  # noqa: BLE001, S110
            pass

    # Normalizzazione Unicode (NFC)
    normalized = unicodedata.normalize("NFC", result)
    if normalized != result:
        warnings.append("Nome file normalizzato Unicode (NFC)")
        result = normalized

    # PRIMA: Rimuovi path traversal e percorsi assoluti (prima di sanificare i separatori)
    # Gestisci percorsi Windows (C:\Windows\...)
    if ":" in result and len(result) > 1:
        try:
            path = PureWindowsPath(result)
            if path.name and path.name != result:
                warnings.append(f"Rimosso percorso assoluto: '{result}' -> '{path.name}'")
                result = path.name
        except Exception:  # noqa: BLE001, S110
            pass

    # Gestisci percorsi POSIX assoluti (/etc/passwd)
    if result.startswith("/"):
        try:
            path = PurePosixPath(result)
            if path.name:
                warnings.append(f"Rimosso percorso assoluto: '{result}' -> '{path.name}'")
                result = path.name
        except Exception:  # noqa: BLE001, S110
            pass

    # Gestisci path traversal relativo (../../../etc/passwd)
    if ".." in result or "/" in result or "\\" in result:
        # Prova entrambi i formati
        for path_class in (PurePosixPath, PureWindowsPath):
            try:
                path = path_class(result)
                if path.name and path.name != result:
                    warnings.append(f"Rimosso path traversal: '{result}' -> '{path.name}'")
                    result = path.name
                    break
            except Exception:  # noqa: BLE001, S110
                pass

    # Rimuovi esplicitamente qualsiasi .. rimasto
    while ".." in result:
        result = result.replace("..", "_")
        if not any("path traversal" in w.lower() for w in warnings):
            warnings.append("Rimosso pattern path traversal")

    # POI: Rimuovi caratteri di controllo (U+0000-U+001F, U+007F-U+009F)
    # e caratteri bidirezionali pericolosi (U+202A-U+202E, U+2066-U+2069)
    bidi_control_chars = {
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # LRE, RLE, PDF, LRO, RLO
        0x2066, 0x2067, 0x2068, 0x2069,  # LRI, RLI, FSI, PDI
    }
    cleaned = ""
    for char in result:
        code = ord(char)
        if code < 0x20 or (0x7F <= code <= 0x9F) or code in bidi_control_chars:
            cleaned += "_"
        else:
            cleaned += char
    if cleaned != result:
        warnings.append("Rimossi caratteri di controllo")
        result = cleaned

    # Rimuovi caratteri non validi per Windows
    for char in INVALID_FILENAME_CHARS:
        if char in result:
            result = result.replace(char, "_")
            if not any("Rimossi caratteri non validi" in w for w in warnings):
                warnings.append("Rimossi caratteri non validi per file system")

    # Gestisci nomi riservati Windows
    name_without_ext = result.rsplit(".", 1)[0] if "." in result else result
    if name_without_ext.upper() in WINDOWS_RESERVED_NAMES:
        result = f"_{result}"
        warnings.append(f"Nome riservato Windows rinominato: '{name_without_ext}' -> '_{name_without_ext}'")

    # Rimuovi spazi iniziali/finali e punti finali (problematici su Windows)
    stripped = result.strip(" .")
    if stripped != result:
        warnings.append("Rimossi spazi/punti iniziali o finali")
        result = stripped

    # Se il nome è vuoto o contiene solo caratteri non validi dopo la sanificazione
    if not result or all(c in "_." for c in result):
        old_result = result
        result = "unnamed"
        if old_result:
            warnings.append(f"Nome file '{old_result}' non valido, sostituito con 'unnamed'")
        else:
            warnings.append("Nome file vuoto dopo sanificazione, sostituito con 'unnamed'")

    # Troncamento a lunghezza massima (preservando l'estensione se possibile)
    if len(result.encode("utf-8")) > max_length:
        if "." in result:
            name, ext = result.rsplit(".", 1)
            ext = "." + ext
            max_name_len = max_length - len(ext.encode("utf-8")) - 1
            if max_name_len > 0:
                # Tronca il nome mantenendo l'estensione
                while len(name.encode("utf-8")) > max_name_len:
                    name = name[:-1]
                result = name + ext
            else:
                # Estensione troppo lunga, tronca tutto
                while len(result.encode("utf-8")) > max_length:
                    result = result[:-1]
        else:
            while len(result.encode("utf-8")) > max_length:
                result = result[:-1]
        warnings.append(f"Nome file troncato a {max_length} bytes")

    return (result, warnings)


def is_extension_type_mismatch(
    filename: str,
    detected_type: DetectedFileType
) -> tuple[bool, str]:
    """
    Verifica se l'estensione del file corrisponde al tipo rilevato.

    Returns:
        Tuple (is_mismatch, message)
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    expected_types = {
        "pdf": {DetectedFileType.PDF},
        "xlsx": {DetectedFileType.XLSX},
        "xls": {DetectedFileType.XLS, DetectedFileType.OLE2},
        "xlsm": {DetectedFileType.XLSM},
        "csv": {DetectedFileType.CSV, DetectedFileType.TEXT},
        "eml": {DetectedFileType.EML, DetectedFileType.TEXT},
        "txt": {DetectedFileType.TEXT, DetectedFileType.CSV, DetectedFileType.EML},
    }

    if ext in expected_types:  # noqa: SIM102
        if detected_type not in expected_types[ext]:
            return (
                True,
                f"Estensione '.{ext}' non corrisponde al tipo rilevato '{detected_type.value}'"
            )

    return (False, "")


def is_dangerous_file_type(detected_type: DetectedFileType) -> tuple[bool, str]:
    """
    Verifica se il tipo di file è potenzialmente pericoloso.

    Returns:
        Tuple (is_dangerous, reason)
    """
    dangerous_types = {
        DetectedFileType.EXECUTABLE_PE: "File eseguibile Windows (PE)",
        DetectedFileType.EXECUTABLE_ELF: "File eseguibile Linux (ELF)",
        DetectedFileType.EXECUTABLE_MACHO: "File eseguibile macOS (Mach-O)",
        DetectedFileType.EXECUTABLE_SCRIPT: "Script eseguibile",
        DetectedFileType.XLSM: "File Excel con macro (potenzialmente pericoloso)",
    }

    if detected_type in dangerous_types:
        return (True, dangerous_types[detected_type])

    return (False, "")


@dataclass
class ValidationResult:
    """Risultato della validazione di un file."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    detected_type: DetectedFileType | None = None
    sanitized_filename: str | None = None


def validate_file_for_ingest(
    content: bytes,
    filename: str,
    max_file_size: int,
    max_xlsx_decompressed_size: int,
    max_filename_length: int = 255,
    reject_executables: bool = True,
    reject_macros: bool = True,
    warn_extension_mismatch: bool = True,
) -> ValidationResult:
    """
    Validazione completa di un file per l'ingestione.

    Args:
        content: Contenuto del file
        filename: Nome del file
        max_file_size: Dimensione massima consentita
        max_xlsx_decompressed_size: Dimensione massima decompressa per XLSX
        max_filename_length: Lunghezza massima nome file
        reject_executables: Se rifiutare eseguibili
        reject_macros: Se rifiutare file con macro
        warn_extension_mismatch: Se emettere warning per estensione non corrispondente

    Returns:
        ValidationResult con errori e warning
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Sanifica il nome file
    sanitized_name, name_warnings = sanitize_filename(filename, max_filename_length)
    warnings.extend(name_warnings)

    # Verifica dimensione file
    file_size = len(content)
    if file_size > max_file_size:
        errors.append(
            f"File troppo grande: {file_size:,} bytes (limite: {max_file_size:,} bytes)"
        )

    # Rileva tipo file
    type_result = detect_file_type(content)
    detected_type = type_result.detected_type

    # Verifica tipo pericoloso
    if reject_executables:
        is_dangerous, danger_reason = is_dangerous_file_type(detected_type)
        if is_dangerous and detected_type != DetectedFileType.XLSM:
            errors.append(f"Tipo file rifiutato: {danger_reason}")

    if reject_macros and detected_type == DetectedFileType.XLSM:
        errors.append("File Excel con macro (.xlsm) non consentito")

    # Verifica corrispondenza estensione
    if warn_extension_mismatch:
        is_mismatch, mismatch_msg = is_extension_type_mismatch(filename, detected_type)
        if is_mismatch:
            warnings.append(mismatch_msg)

    # Verifica zip bomb per file XLSX
    if detected_type in (DetectedFileType.XLSX, DetectedFileType.XLSM, DetectedFileType.ZIP):  # noqa: SIM102
        if content.startswith(MAGIC_ZIP):
            is_safe, _decompressed_size, bomb_msg = check_zip_bomb(content, max_xlsx_decompressed_size)
            if not is_safe:
                errors.append(f"Possibile zip bomb: {bomb_msg}")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        detected_type=detected_type,
        sanitized_filename=sanitized_name,
    )
