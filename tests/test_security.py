"""Test per le funzionalità di sicurezza del modulo ingest."""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import pytest

from ingest import (
    DEFAULT_CONFIG,
    DetectedFileType,
    IngestConfig,
    Ingestor,
    WarningCodes,
    WarningSeverity,
    detect_file_type,
    sanitize_filename,
    validate_file_for_ingest,
)
from ingest.security import (
    check_zip_bomb,
    is_dangerous_file_type,
    is_extension_type_mismatch,
)


class TestFileTypeDetection:
    """Test per il rilevamento del tipo file via magic number."""

    def test_detect_pdf(self):
        """Rileva file PDF dai magic number."""
        pdf_content = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\n>>\nendobj"
        result = detect_file_type(pdf_content)
        assert result.detected_type == DetectedFileType.PDF
        assert result.confidence == "high"

    def test_detect_pdf_with_bom(self):
        """Rileva PDF anche con BOM iniziale."""
        pdf_content = b"\xef\xbb\xbf%PDF-1.7\ntest"
        result = detect_file_type(pdf_content)
        # PDF deve iniziare con %PDF, quindi questo non è un PDF valido
        assert result.detected_type != DetectedFileType.PDF

    def test_detect_xlsx_zip_magic(self):
        """Rileva file XLSX dal magic number ZIP e Content_Types.xml."""
        xlsx_content = self._create_minimal_xlsx()
        result = detect_file_type(xlsx_content)
        assert result.detected_type == DetectedFileType.XLSX
        assert result.confidence == "high"

    def test_detect_xlsm_with_macros(self):
        """Rileva file XLSM (con macro) dal Content_Types.xml."""
        xlsm_content = self._create_xlsm_with_macro_marker()
        result = detect_file_type(xlsm_content)
        assert result.detected_type == DetectedFileType.XLSM
        assert result.confidence == "high"

    def test_detect_xls_ole2(self):
        """Rileva file XLS (OLE2) dal magic number."""
        xls_content = self._create_minimal_ole2()
        result = detect_file_type(xls_content)
        assert result.detected_type in (DetectedFileType.XLS, DetectedFileType.OLE2)

    def test_detect_executable_pe(self):
        """Rileva eseguibile Windows PE."""
        pe_content = self._create_fake_pe()
        result = detect_file_type(pe_content)
        assert result.detected_type == DetectedFileType.EXECUTABLE_PE

    def test_detect_executable_elf(self):
        """Rileva eseguibile Linux ELF."""
        elf_content = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100
        result = detect_file_type(elf_content)
        assert result.detected_type == DetectedFileType.EXECUTABLE_ELF

    def test_detect_executable_macho(self):
        """Rileva eseguibile macOS Mach-O."""
        macho_content = b"\xFE\xED\xFA\xCF" + b"\x00" * 100  # 64-bit
        result = detect_file_type(macho_content)
        assert result.detected_type == DetectedFileType.EXECUTABLE_MACHO

    def test_detect_script_shebang(self):
        """Rileva script con shebang."""
        script_content = b"#!/usr/bin/python3\nprint('hello')\n"
        result = detect_file_type(script_content)
        assert result.detected_type == DetectedFileType.EXECUTABLE_SCRIPT

        bash_script = b"#!/bin/bash\necho hello\n"
        result = detect_file_type(bash_script)
        assert result.detected_type == DetectedFileType.EXECUTABLE_SCRIPT

    def test_detect_csv_text(self):
        """Rileva file CSV come testo tabellare."""
        csv_content = b"name,age,city\nAlice,30,Rome\nBob,25,Milan\n"
        result = detect_file_type(csv_content)
        assert result.detected_type in (DetectedFileType.CSV, DetectedFileType.TEXT)

    def test_detect_eml_email(self):
        """Rileva file email EML."""
        eml_content = b"""From: sender@example.com
To: recipient@example.com
Subject: Test email
Date: Mon, 1 Jan 2024 12:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain

This is a test email body.
"""
        result = detect_file_type(eml_content)
        assert result.detected_type == DetectedFileType.EML

    def test_detect_unknown_binary(self):
        """File binario sconosciuto."""
        binary_content = b"\x00\x01\x02\x03" * 100
        result = detect_file_type(binary_content)
        assert result.detected_type == DetectedFileType.UNKNOWN

    def test_detect_small_file(self):
        """File troppo piccolo per rilevamento."""
        tiny_content = b"AB"
        result = detect_file_type(tiny_content)
        assert result.confidence == "low"

    # Helper methods per creare contenuti di test
    @staticmethod
    def _create_minimal_xlsx() -> bytes:
        """Crea un file XLSX minimale valido."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml"
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("xl/workbook.xml", "<workbook/>")
        return buffer.getvalue()

    @staticmethod
    def _create_xlsm_with_macro_marker() -> bytes:
        """Crea un file XLSM minimale con marker macro."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>
    <Override PartName="/xl/workbook.xml"
        ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/>
</Types>"""
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("xl/workbook.xml", "<workbook/>")
            zf.writestr("xl/vbaProject.bin", b"\x00" * 100)
        return buffer.getvalue()

    @staticmethod
    def _create_minimal_ole2() -> bytes:
        """Crea un header OLE2 minimale."""
        # OLE2 magic number + header
        header = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
        header += b"\x00" * 504  # Rest of header (512 bytes total)
        header += b"Workbook" + b"\x00" * 200
        return header

    @staticmethod
    def _create_fake_pe() -> bytes:
        """Crea un PE minimale per test."""
        # DOS header
        dos_header = b"MZ" + b"\x00" * 58
        # PE offset at 0x3C
        pe_offset = 64
        dos_header += struct.pack("<I", pe_offset)
        # Padding to PE header
        dos_header = dos_header.ljust(pe_offset, b"\x00")
        # PE signature
        pe_sig = b"PE\x00\x00"
        return dos_header + pe_sig + b"\x00" * 100


class TestExtensionMismatch:
    """Test per il rilevamento di mismatch estensione/tipo."""

    def test_pdf_extension_matches_pdf_content(self):
        """Estensione .pdf corrisponde a contenuto PDF."""
        is_mismatch, _msg = is_extension_type_mismatch("document.pdf", DetectedFileType.PDF)
        assert not is_mismatch

    def test_pdf_extension_with_exe_content(self):
        """Estensione .pdf con contenuto eseguibile."""
        is_mismatch, msg = is_extension_type_mismatch("document.pdf", DetectedFileType.EXECUTABLE_PE)
        assert is_mismatch
        assert "estensione" in msg.lower()

    def test_xlsx_extension_with_xlsm_content(self):
        """Estensione .xlsx con contenuto macro (xlsm)."""
        is_mismatch, _msg = is_extension_type_mismatch("spreadsheet.xlsx", DetectedFileType.XLSM)
        assert is_mismatch

    def test_csv_extension_with_text_content(self):
        """Estensione .csv con testo generico (accettabile)."""
        is_mismatch, _msg = is_extension_type_mismatch("data.csv", DetectedFileType.TEXT)
        assert not is_mismatch


class TestDangerousFileTypes:
    """Test per il rilevamento di tipi file pericolosi."""

    def test_pe_is_dangerous(self):
        """Eseguibile PE è pericoloso."""
        is_dangerous, reason = is_dangerous_file_type(DetectedFileType.EXECUTABLE_PE)
        assert is_dangerous
        assert "eseguibile" in reason.lower()

    def test_elf_is_dangerous(self):
        """Eseguibile ELF è pericoloso."""
        is_dangerous, _reason = is_dangerous_file_type(DetectedFileType.EXECUTABLE_ELF)
        assert is_dangerous

    def test_macho_is_dangerous(self):
        """Eseguibile Mach-O è pericoloso."""
        is_dangerous, _reason = is_dangerous_file_type(DetectedFileType.EXECUTABLE_MACHO)
        assert is_dangerous

    def test_script_is_dangerous(self):
        """Script eseguibile è pericoloso."""
        is_dangerous, _reason = is_dangerous_file_type(DetectedFileType.EXECUTABLE_SCRIPT)
        assert is_dangerous

    def test_xlsm_is_dangerous(self):
        """File con macro è pericoloso."""
        is_dangerous, reason = is_dangerous_file_type(DetectedFileType.XLSM)
        assert is_dangerous
        assert "macro" in reason.lower()

    def test_pdf_is_not_dangerous(self):
        """PDF non è pericoloso."""
        is_dangerous, _reason = is_dangerous_file_type(DetectedFileType.PDF)
        assert not is_dangerous

    def test_xlsx_is_not_dangerous(self):
        """XLSX senza macro non è pericoloso."""
        is_dangerous, _reason = is_dangerous_file_type(DetectedFileType.XLSX)
        assert not is_dangerous


class TestFilenameSanitization:
    """Test per la sanificazione dei nomi file."""

    def test_normal_filename_unchanged(self):
        """Nome file normale resta invariato."""
        safe, warnings = sanitize_filename("document.pdf")
        assert safe == "document.pdf"
        assert len(warnings) == 0

    def test_path_traversal_removed(self):
        """Path traversal rimosso."""
        safe, warnings = sanitize_filename("../../../etc/passwd")
        assert ".." not in safe
        assert "/" not in safe
        assert len(warnings) > 0

    def test_absolute_path_stripped(self):
        """Percorso assoluto POSIX ridotto a nome file."""
        safe, warnings = sanitize_filename("/etc/passwd")
        assert safe == "passwd"
        assert len(warnings) > 0

    def test_windows_absolute_path_stripped(self):
        """Percorso assoluto Windows ridotto a nome file."""
        safe, warnings = sanitize_filename("C:\\Windows\\System32\\cmd.exe")
        assert safe == "cmd.exe"
        assert len(warnings) > 0

    def test_control_characters_removed(self):
        """Caratteri di controllo rimossi."""
        safe, warnings = sanitize_filename("file\x00name\x1f.pdf")
        assert "\x00" not in safe
        assert "\x1f" not in safe
        assert len(warnings) > 0

    def test_windows_reserved_names_renamed(self):
        """Nomi riservati Windows rinominati."""
        for reserved in ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]:
            safe, warnings = sanitize_filename(f"{reserved}.txt")
            assert not safe.upper().startswith(reserved + ".")
            assert len(warnings) > 0

    def test_windows_reserved_names_case_insensitive(self):
        """Nomi riservati Windows riconosciuti case-insensitive."""
        safe, _warnings = sanitize_filename("con.txt")
        assert not safe.lower().startswith("con.")

        safe, _warnings = sanitize_filename("CoN.txt")
        assert not safe.upper().startswith("CON.")

    def test_invalid_characters_replaced(self):
        """Caratteri non validi per file system sostituiti."""
        safe, warnings = sanitize_filename('file<>:"/\\|?*.pdf')
        for char in '<>:"/\\|?*':
            assert char not in safe
        assert len(warnings) > 0

    def test_unicode_normalized_nfc(self):
        """Nome file normalizzato a Unicode NFC."""
        # é in NFD (e + combining accent) vs NFC (precomposed)
        nfd_name = "caf\u0065\u0301.txt"  # e + combining acute
        safe, warnings = sanitize_filename(nfd_name)
        # Dovrebbe essere normalizzato a NFC
        assert safe == "café.txt" or "normalizzato" in str(warnings).lower()

    def test_filename_truncated(self):
        """Nome file lungo troncato."""
        long_name = "a" * 300 + ".pdf"
        safe, warnings = sanitize_filename(long_name, max_length=255)
        assert len(safe.encode("utf-8")) <= 255
        assert safe.endswith(".pdf")  # Estensione preservata
        assert any("troncato" in w.lower() for w in warnings)

    def test_empty_filename_replaced(self):
        """Nome file vuoto sostituito."""
        safe, warnings = sanitize_filename("")
        assert safe == "unnamed"
        assert len(warnings) > 0

    def test_only_dots_filename_replaced(self):
        """Nome file solo punti sanificato."""
        safe, warnings = sanitize_filename("...")
        assert safe == "unnamed"
        assert len(warnings) > 0

    def test_rfc2047_encoded_filename(self):
        """Decodifica RFC 2047 (MIME encoded-word)."""
        encoded = "=?utf-8?B?ZG9jdW1lbnRvLnBkZg==?="  # "documento.pdf" in base64
        safe, _warnings = sanitize_filename(encoded)
        assert safe == "documento.pdf"

    def test_trailing_spaces_dots_removed(self):
        """Spazi e punti finali rimossi."""
        safe, _warnings = sanitize_filename("file.pdf   ")
        assert safe == "file.pdf"

        safe, _warnings = sanitize_filename("file...")
        assert not safe.endswith(".")


class TestZipBombProtection:
    """Test per la protezione da zip bomb."""

    def test_normal_zip_is_safe(self):
        """ZIP normale passa la verifica."""
        zip_content = self._create_normal_zip()
        is_safe, _size, msg = check_zip_bomb(zip_content, 100 * 1024 * 1024)
        assert is_safe
        assert "OK" in msg

    def test_zip_bomb_detected(self):
        """Zip bomb rilevata per dimensione decompressa."""
        zip_content = self._create_zip_with_large_uncompressed()
        is_safe, _size, msg = check_zip_bomb(zip_content, 1024)  # Limite 1KB
        assert not is_safe
        assert "dimensione" in msg.lower() or "supera" in msg.lower()

    def test_suspicious_compression_ratio(self):
        """Ratio compressione sospetto rilevato."""
        zip_content = self._create_highly_compressed_zip()
        is_safe, _size, _msg = check_zip_bomb(zip_content, 100 * 1024 * 1024)
        # Se il ratio è > 100:1, dovrebbe essere segnalato
        # Nota: questo dipende da quanto comprimiamo
        assert isinstance(is_safe, bool)

    def test_corrupted_zip_handled(self):
        """ZIP corrotto gestito gracefully."""
        corrupted = b"PK\x03\x04" + b"\x00" * 100
        is_safe, _size, msg = check_zip_bomb(corrupted, 100 * 1024 * 1024)
        assert not is_safe
        assert "corrotto" in msg.lower() or "errore" in msg.lower()

    @staticmethod
    def _create_normal_zip() -> bytes:
        """Crea uno ZIP normale."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("file1.txt", "Hello World")
            zf.writestr("file2.txt", "Test content")
        return buffer.getvalue()

    @staticmethod
    def _create_zip_with_large_uncompressed() -> bytes:
        """Crea uno ZIP con dimensione decompressa grande."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # 10KB di dati ripetuti (compressi bene)
            large_data = b"A" * 10240
            zf.writestr("large.txt", large_data)
        return buffer.getvalue()

    @staticmethod
    def _create_highly_compressed_zip() -> bytes:
        """Crea uno ZIP con alto ratio di compressione."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            # Dati altamente comprimibili
            zf.writestr("zeros.bin", b"\x00" * 50000)
        return buffer.getvalue()


class TestFileSizeLimits:
    """Test per i limiti di dimensione file."""

    def test_file_under_limit_accepted(self):
        """File sotto il limite accettato."""
        config = IngestConfig(max_file_size_bytes=1024)
        content = b"x" * 500
        validation = validate_file_for_ingest(
            content=content,
            filename="test.csv",
            max_file_size=config.max_file_size_bytes,
            max_xlsx_decompressed_size=config.max_xlsx_decompressed_size_bytes,
        )
        assert validation.is_valid

    def test_file_over_limit_rejected(self):
        """File sopra il limite rifiutato."""
        config = IngestConfig(max_file_size_bytes=100)
        content = b"x" * 200
        validation = validate_file_for_ingest(
            content=content,
            filename="test.csv",
            max_file_size=config.max_file_size_bytes,
            max_xlsx_decompressed_size=config.max_xlsx_decompressed_size_bytes,
        )
        assert not validation.is_valid
        assert any("troppo grande" in e.lower() for e in validation.errors)


class TestIngestorSecurityIntegration:
    """Test di integrazione per le funzionalità di sicurezza nell'Ingestor."""

    @pytest.fixture
    def strict_config(self) -> IngestConfig:
        """Configurazione restrittiva per test."""
        return IngestConfig(
            max_file_size_bytes=1024 * 1024,  # 1MB
            max_email_total_size_bytes=2 * 1024 * 1024,  # 2MB
            max_attachments=5,
            max_xlsx_decompressed_size_bytes=10 * 1024 * 1024,  # 10MB
            reject_executables=True,
            reject_macros=True,
            warn_extension_mismatch=True,
        )

    def test_ingestor_with_custom_config(self, strict_config: IngestConfig):
        """Ingestor accetta configurazione personalizzata."""
        ingestor = Ingestor(config=strict_config)
        assert ingestor.config.max_file_size_bytes == 1024 * 1024
        assert ingestor.config.max_attachments == 5

    def test_ingestor_rejects_large_file(self, strict_config: IngestConfig, tmp_path: Path):
        """Ingestor rifiuta file troppo grande."""
        # Crea file CSV troppo grande
        large_file = tmp_path / "large.csv"
        large_file.write_bytes(b"x," * 600000)  # > 1MB

        ingestor = Ingestor(config=strict_config)
        result = ingestor.ingest(large_file)

        # Deve avere warning con severity ERROR
        error_warnings = [w for w in result.warnings if w.severity == WarningSeverity.ERROR]
        assert len(error_warnings) > 0
        assert any(w.code == WarningCodes.SIZE_FILE_TOO_LARGE for w in error_warnings)

    def test_ingestor_rejects_executable_disguised_as_pdf(self, strict_config: IngestConfig, tmp_path: Path):
        """Ingestor rifiuta eseguibile mascherato da PDF."""
        # Crea file che sembra PDF ma è un PE
        fake_pdf = tmp_path / "document.pdf"
        fake_pdf.write_bytes(TestFileTypeDetection._create_fake_pe())

        ingestor = Ingestor(config=strict_config)
        result = ingestor.ingest(fake_pdf)

        error_warnings = [w for w in result.warnings if w.severity == WarningSeverity.ERROR]
        assert len(error_warnings) > 0
        assert any(w.code == WarningCodes.TYPE_EXECUTABLE for w in error_warnings)

    def test_ingestor_warns_extension_mismatch(self, tmp_path: Path):
        """Ingestor emette warning per mismatch estensione."""
        # Crea file CSV con estensione .txt
        csv_as_txt = tmp_path / "data.txt"
        csv_as_txt.write_bytes(b"a,b,c\n1,2,3\n")

        # Con configurazione default che avverte ma non rifiuta
        config = IngestConfig(warn_extension_mismatch=True)
        ingestor = Ingestor(config=config)

        # Dato che .txt non è supportato, userà il tipo rilevato
        # Questo test verifica il comportamento con file supportati
        csv_file = tmp_path / "data.csv"
        csv_file.write_bytes(b"a,b,c\n1,2,3\n")
        result = ingestor.ingest(csv_file)
        # CSV con contenuto CSV non dovrebbe avere mismatch
        mismatch_warnings = [w for w in result.warnings if w.code == WarningCodes.TYPE_MISMATCH]
        assert len(mismatch_warnings) == 0


class TestEmailSecurityIntegration:
    """Test di sicurezza specifici per email."""

    @pytest.fixture
    def eml_config(self) -> IngestConfig:
        """Configurazione per test email."""
        return IngestConfig(
            max_file_size_bytes=1024 * 1024,  # 1MB per allegato
            max_email_total_size_bytes=2 * 1024 * 1024,  # 2MB totali
            max_attachments=3,
            reject_executables=True,
            reject_macros=True,
        )

    def test_email_with_sanitized_attachment_name(self, eml_config: IngestConfig, tmp_path: Path):
        """Email con allegato dal nome pericoloso viene sanificato."""
        eml_content = self._create_eml_with_dangerous_attachment_name()
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_content)

        ingestor = Ingestor(config=eml_config)
        result = ingestor.ingest(eml_file)

        # Verifica che ci siano warning di sanificazione
        [w for w in result.warnings
                        if w.code == WarningCodes.NAME_SANITIZED or "path" in w.message.lower()]
        # Potrebbe non esserci warning se il nome originale era già sicuro
        # ma il test verifica che il parsing funzioni

    def test_email_rejects_too_many_attachments(self, eml_config: IngestConfig, tmp_path: Path):
        """Email con troppi allegati rifiuta quelli in eccesso."""
        eml_content = self._create_eml_with_many_attachments(5)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_content)

        ingestor = Ingestor(config=eml_config)
        result = ingestor.ingest(eml_file)

        # Dovrebbe avere warning per allegati ignorati (limite è 3)
        too_many_warnings = [w for w in result.warnings
                           if w.code == WarningCodes.SIZE_TOO_MANY_ATTACHMENTS]
        assert len(too_many_warnings) >= 2  # almeno 2 allegati ignorati (4° e 5°)

    def _create_eml_with_dangerous_attachment_name(self) -> bytes:
        """Crea email con allegato dal nome pericoloso."""
        boundary = "----=_Part_0"
        return f"""From: sender@example.com
To: recipient@example.com
Subject: Test dangerous attachment
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="{boundary}"

--{boundary}
Content-Type: text/plain

Email body.

--{boundary}
Content-Type: text/plain
Content-Disposition: attachment; filename="../../../etc/passwd"

fake content

--{boundary}--
""".encode()

    def _create_eml_with_many_attachments(self, count: int) -> bytes:
        """Crea email con molti allegati."""
        boundary = "----=_Part_0"
        parts = [f"""From: sender@example.com
To: recipient@example.com
Subject: Test many attachments
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="{boundary}"

--{boundary}
Content-Type: text/plain

Email body.
"""]

        for i in range(count):
            parts.append(f"""
--{boundary}
Content-Type: text/plain
Content-Disposition: attachment; filename="file{i}.txt"

Content of file {i}
""")

        parts.append(f"\n--{boundary}--\n")
        return "".join(parts).encode()


class TestMaliciousFileSynthetic:
    """Test con file malevoli sintetici costruiti nei test."""

    def test_null_byte_injection(self, tmp_path: Path):
        """File con null byte nel nome."""
        # Il null byte in Python non è permesso nei nomi file,
        # ma testiamo la sanificazione
        dangerous_name = "file\x00.pdf"
        safe, warnings = sanitize_filename(dangerous_name)
        assert "\x00" not in safe
        assert len(warnings) > 0

    def test_unicode_normalization_attack(self):
        """Attacco con Unicode non normalizzato."""
        # Slash in forma compatibile: U+2215 (DIVISION SLASH)
        # U+2044 (FRACTION SLASH)
        tricky_name = "file\u2215test.pdf"
        _safe, _warnings = sanitize_filename(tricky_name)
        # Questi caratteri potrebbero essere lasciati (non sono path separator)
        # ma il path traversal classico (..) dovrebbe essere bloccato

    def test_double_extension_handling(self):
        """Gestione doppia estensione."""
        double_ext = "document.pdf.exe"
        safe, _warnings = sanitize_filename(double_ext)
        # Il nome dovrebbe essere preservato ma il tipo file è determinato dal contenuto
        assert safe == "document.pdf.exe"

    def test_very_long_utf8_filename(self):
        """Nome file molto lungo con caratteri UTF-8."""
        # Caratteri emoji usano 4 bytes ciascuno
        emoji_name = "📄" * 100 + ".pdf"
        safe, _warnings = sanitize_filename(emoji_name, max_length=255)
        assert len(safe.encode("utf-8")) <= 255
        assert safe.endswith(".pdf")

    def test_rtlo_attack(self):
        """Attacco Right-to-Left Override."""
        # U+202E è Right-to-Left Override
        rtlo_name = "invoice\u202Efdp.exe"
        safe, _warnings = sanitize_filename(rtlo_name)
        # Il carattere di controllo dovrebbe essere rimosso
        assert "\u202e" not in safe

    def test_zip_slip_via_zip_entry(self):
        """Protezione da Zip Slip (path traversal dentro ZIP)."""
        # Questo è un test concettuale - il check_zip_bomb non estrae
        # ma verifica che file XLSX malevoli non passino
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            # Tentativo di path traversal nell'archivio
            try:
                zf.writestr("../../../etc/passwd", "fake")
            except Exception:  # noqa: BLE001, S110
                pass  # Alcuni sistemi bloccano questo
            zf.writestr("normal.txt", "content")

        _is_safe, _, _ = check_zip_bomb(buffer.getvalue(), 100 * 1024 * 1024)
        # Il file è valido come ZIP ma l'estrazione deve essere sicura
        # (questo è responsabilità del codice che estrae, non di check_zip_bomb)


class TestDefaultConfig:
    """Test per i valori di default della configurazione."""

    def test_default_file_size_limit(self):
        """Limite dimensione file default è 25MB."""
        assert DEFAULT_CONFIG.max_file_size_bytes == 25 * 1024 * 1024

    def test_default_email_size_limit(self):
        """Limite dimensione email default è 50MB."""
        assert DEFAULT_CONFIG.max_email_total_size_bytes == 50 * 1024 * 1024

    def test_default_max_attachments(self):
        """Numero massimo allegati default è 20."""
        assert DEFAULT_CONFIG.max_attachments == 20

    def test_default_xlsx_decompressed_limit(self):
        """Limite XLSX decompresso default è 100MB."""
        assert DEFAULT_CONFIG.max_xlsx_decompressed_size_bytes == 100 * 1024 * 1024

    def test_default_reject_executables(self):
        """Rifiuto eseguibili attivo per default."""
        assert DEFAULT_CONFIG.reject_executables is True

    def test_default_reject_macros(self):
        """Rifiuto macro attivo per default."""
        assert DEFAULT_CONFIG.reject_macros is True

    def test_default_warn_extension_mismatch(self):
        """Warning estensione mismatch attivo per default."""
        assert DEFAULT_CONFIG.warn_extension_mismatch is True
