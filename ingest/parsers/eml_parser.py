"""Parser per file .eml (email)."""

from __future__ import annotations

import email
import email.utils
import hashlib
import re
import uuid
from datetime import datetime
from email.message import Message
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from ..models import (
    EmailAddress,
    EmailMetadata,
    FileType,
    NormalizedInput,
    Part,
    PartType,
    Source,
    Warning,
)


class HTMLTextExtractor(HTMLParser):
    """Estrae testo pulito da HTML."""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_data = False
        self._skip_tags = {"script", "style", "head", "meta", "link"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._skip_tags:
            self._skip_data = True
        elif tag.lower() in ("br", "p", "div", "tr", "li"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._skip_data = False
        elif tag.lower() in ("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_data:
            self.text_parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.text_parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


def _extract_html_text(html: str) -> str:
    """Estrae testo pulito da HTML."""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def _parse_address(addr_str: str | None) -> list[EmailAddress]:
    """Parsa una stringa di indirizzi email."""
    if not addr_str:
        return []
    
    addresses = []
    for name, addr in email.utils.getaddresses([addr_str]):
        addresses.append(EmailAddress(
            name=name if name else None,
            address=addr if addr else None
        ))
    return addresses


def _parse_date(date_str: str | None) -> str | None:
    """Parsa una data email in formato ISO 8601."""
    if not date_str:
        return None
    
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


SIGNATURE_PATTERNS = [
    r"^--\s*$",
    r"^_{3,}$",
    r"^-{3,}$",
    r"^Best regards,?\s*$",
    r"^Kind regards,?\s*$",
    r"^Regards,?\s*$",
    r"^Cordiali saluti,?\s*$",
    r"^Distinti saluti,?\s*$",
    r"^Thanks?,?\s*$",
    r"^Thank you,?\s*$",
    r"^Grazie,?\s*$",
    r"^Sincerely,?\s*$",
    r"^Sent from my iPhone$",
    r"^Sent from my iPad$",
    r"^Inviato da iPhone$",
]

QUOTE_PATTERNS = [
    r"^>+\s*",
    r"^On .+ wrote:$",
    r"^Il .+ ha scritto:$",
    r"^-{5,}Original Message-{5,}$",
    r"^From: .+$",
    r"^Sent: .+$",
    r"^To: .+$",
    r"^Subject: .+$",
]


def _separate_signature_and_quotes(text: str) -> tuple[str, str | None, str | None]:
    """
    Separa il corpo principale dalla firma e dalle citazioni.
    Ritorna (body, signature, quoted).
    """
    lines = text.split("\n")
    
    signature_start = None
    for i, line in enumerate(lines):
        for pattern in SIGNATURE_PATTERNS:
            if re.match(pattern, line, re.IGNORECASE):
                signature_start = i
                break
        if signature_start is not None:
            break
    
    quote_start = None
    for i, line in enumerate(lines):
        if signature_start is not None and i >= signature_start:
            continue
        for pattern in QUOTE_PATTERNS:
            if re.match(pattern, line, re.IGNORECASE):
                quote_start = i
                break
        if quote_start is not None:
            break
    
    body_end = len(lines)
    if signature_start is not None and quote_start is not None:
        body_end = min(signature_start, quote_start)
    elif signature_start is not None:
        body_end = signature_start
    elif quote_start is not None:
        body_end = quote_start
    
    body = "\n".join(lines[:body_end]).strip()
    
    signature = None
    if signature_start is not None:
        sig_end = quote_start if quote_start is not None and quote_start > signature_start else len(lines)
        signature = "\n".join(lines[signature_start:sig_end]).strip()
        if not signature:
            signature = None
    
    quoted = None
    if quote_start is not None:
        quoted = "\n".join(lines[quote_start:]).strip()
        if not quoted:
            quoted = None
    
    return body, signature, quoted


class EmlParser:
    """Parser per file .eml."""

    SUPPORTED_ATTACHMENT_TYPES = {
        "application/pdf": FileType.PDF,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileType.XLSX,
        "application/vnd.ms-excel": FileType.XLS,
        "text/csv": FileType.CSV,
        "application/octet-stream": None,
    }

    def __init__(self):
        self._attachment_parsers: dict = {}

    def set_attachment_parsers(self, parsers: dict) -> None:
        """Imposta i parser per gli allegati."""
        self._attachment_parsers = parsers

    def parse(self, file_path: Path | str) -> NormalizedInput:
        """Parsa un file .eml."""
        file_path = Path(file_path)
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        return self.parse_bytes(content, filename=file_path.name, file_path=str(file_path))

    def parse_bytes(
        self,
        content: bytes,
        filename: str = "email.eml",
        file_path: str | None = None
    ) -> NormalizedInput:
        """Parsa contenuto .eml da bytes."""
        msg = email.message_from_bytes(content)
        
        sha256 = hashlib.sha256(content).hexdigest()
        source = Source(
            filename=filename,
            sha256=sha256,
            file_type=FileType.EML,
            file_path=file_path,
            file_size_bytes=len(content),
        )
        
        from_addrs = _parse_address(msg.get("From"))
        email_meta = EmailMetadata(
            message_id=msg.get("Message-ID"),
            from_address=from_addrs[0].address if from_addrs else None,
            from_name=from_addrs[0].name if from_addrs else None,
            to_addresses=_parse_address(msg.get("To")),
            cc_addresses=_parse_address(msg.get("Cc")),
            subject=msg.get("Subject"),
            date=msg.get("Date"),
            date_parsed=_parse_date(msg.get("Date")),
        )
        
        result = NormalizedInput(
            source=source,
            email_metadata=email_meta,
        )
        
        text_body, html_body = self._extract_body(msg)
        
        if text_body:
            body, signature, quoted = _separate_signature_and_quotes(text_body)
            
            body_part = Part(
                part_type=PartType.EMAIL_BODY,
                mime_type="text/plain",
                text=body,
            )
            body_part.compute_sha256(body)
            result.parts.append(body_part)
            
            if signature:
                sig_part = Part(
                    part_type=PartType.EMAIL_SIGNATURE,
                    mime_type="text/plain",
                    text=signature,
                )
                sig_part.compute_sha256(signature)
                result.parts.append(sig_part)
            
            if quoted:
                quote_part = Part(
                    part_type=PartType.EMAIL_QUOTED,
                    mime_type="text/plain",
                    text=quoted,
                )
                quote_part.compute_sha256(quoted)
                result.parts.append(quote_part)
                
        elif html_body:
            clean_text = _extract_html_text(html_body)
            body, signature, quoted = _separate_signature_and_quotes(clean_text)
            
            body_part = Part(
                part_type=PartType.EMAIL_BODY_HTML,
                mime_type="text/html",
                text=body,
            )
            body_part.compute_sha256(body)
            result.parts.append(body_part)
            
            if signature:
                sig_part = Part(
                    part_type=PartType.EMAIL_SIGNATURE,
                    mime_type="text/plain",
                    text=signature,
                )
                sig_part.compute_sha256(signature)
                result.parts.append(sig_part)
        
        attachments = self._extract_attachments(msg, result)
        result.parts.extend(attachments)
        
        return result

    def _extract_body(self, msg: Message) -> tuple[str | None, str | None]:
        """Estrae corpo text/plain e text/html."""
        text_body = None
        html_body = None
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and text_body is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            text_body = payload.decode(charset, errors="replace")
                        except Exception:
                            text_body = payload.decode("utf-8", errors="replace")
                elif content_type == "text/html" and html_body is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            html_body = payload.decode(charset, errors="replace")
                        except Exception:
                            html_body = payload.decode("utf-8", errors="replace")
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except Exception:
                    decoded = payload.decode("utf-8", errors="replace")
                
                if content_type == "text/plain":
                    text_body = decoded
                elif content_type == "text/html":
                    html_body = decoded
        
        return text_body, html_body

    def _extract_attachments(self, msg: Message, result: NormalizedInput) -> list[Part]:
        """Estrae e processa gli allegati."""
        attachments = []
        
        if not msg.is_multipart():
            return attachments
        
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" not in content_disposition.lower():
                continue
            
            filename = part.get_filename()
            if not filename:
                continue
            
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            
            content_type = part.get_content_type()
            sha256 = hashlib.sha256(payload).hexdigest()
            
            file_ext = Path(filename).suffix.lower()
            
            parser = None
            if file_ext == ".pdf" and "PdfParser" in self._attachment_parsers:
                parser = self._attachment_parsers["PdfParser"]
            elif file_ext in (".xlsx", ".xls") and "ExcelParser" in self._attachment_parsers:
                parser = self._attachment_parsers["ExcelParser"]
            elif file_ext == ".csv" and "CsvParser" in self._attachment_parsers:
                parser = self._attachment_parsers["CsvParser"]
            
            if parser:
                try:
                    sub_result = parser.parse_bytes(payload, filename=filename)
                    for sub_part in sub_result.parts:
                        sub_part.source_filename = filename
                        attachments.append(sub_part)
                    result.warnings.extend(sub_result.warnings)
                except Exception as e:
                    warn = Warning(
                        code="ATT-02",
                        message=f"Errore nel parsing dell'allegato: {filename}",
                        details={"error": str(e), "filename": filename},
                    )
                    result.warnings.append(warn)
                    
                    att_part = Part(
                        part_type=PartType.ATTACHMENT,
                        source_filename=filename,
                        mime_type=content_type,
                    )
                    att_part.sha256 = sha256
                    attachments.append(att_part)
            else:
                warn = Warning(
                    code="ATT-01",
                    message=f"Tipo di allegato non supportato: {filename}",
                    details={"mime_type": content_type, "filename": filename},
                )
                result.warnings.append(warn)
                
                att_part = Part(
                    part_type=PartType.ATTACHMENT,
                    source_filename=filename,
                    mime_type=content_type,
                )
                att_part.sha256 = sha256
                attachments.append(att_part)
        
        return attachments
