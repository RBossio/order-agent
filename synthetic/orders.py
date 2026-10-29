"""Generatore 150 ordini con documenti PDF, XLSX, EML e ground truth."""

import hashlib
import json
import random
import re
import uuid
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from pathlib import Path

from . import SEED

NUM_IN_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 15: "fifteen", 20: "twenty",
    24: "twenty-four", 25: "twenty-five", 50: "fifty", 100: "one hundred"
}

HARD_CASE_TYPES = [
    "UOM_CONVERSION",
    "CUSTOMER_CODES",
    "AMBIGUOUS_DESC",
    "TYPO_DESC",
    "TOTAL_MIXED",
    "MULTIPAGE_PDF",
    "DATE_FORMAT",
    "QTY_WORDS",
    "EMAIL_CONTRADICTORY",
    "MISSING_PO_NUMBER",
    "MISSING_QTY",
    "MISSING_DATE",
]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _format_date(dt: datetime, fmt: str) -> str:
    mapping = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "MM/DD/YYYY": "%m/%d/%Y",
        "DD-MMM-YYYY": "%d-%b-%Y",
        "M/D/YY": "%-m/%-d/%y",
        "YYYY/MM/DD": "%Y/%m/%d",
        "DD/MM/YYYY": "%d/%m/%Y",
        "MM-DD-YYYY": "%m-%d-%Y",
        "DD.MM.YYYY": "%d.%m.%Y",
        "MMM DD, YYYY": "%b %d, %Y",
    }
    py_fmt = mapping.get(fmt, "%Y-%m-%d")
    try:
        return dt.strftime(py_fmt)
    except ValueError:
        return dt.strftime("%Y-%m-%d")


def _add_typos(desc: str) -> str:
    typos = [
        ("Gloves", "Glovs"),
        ("Cleaner", "Clener"),
        ("Safety", "Safty"),
        ("Steel", "Stel"),
        ("industrial", "industral"),
        ("powder", "powdr"),
        ("free", "fre"),
        ("concentrate", "concetrate"),
        ("Screw", "Scew"),
        ("black", "blak"),
    ]
    for orig, typo in typos:
        if orig.lower() in desc.lower():
            return desc.replace(orig, typo, 1).replace(orig.lower(), typo.lower(), 1)
    return desc + " (approx)"


def _make_ambiguous(desc: str, catalog: list[dict]) -> str:
    desc_lower = desc.lower()
    if "liner" in desc_lower:
        return re.sub(r"\d+x\d+", "", desc)
    if "glove" in desc_lower:
        return re.sub(r"size \w+", "", desc)
    if "cleaner" in desc_lower:
        return desc.replace("concentrate", "").replace("ready to use", "")
    return desc.split()[0] + " " + " ".join(desc.split()[2:]) if len(desc.split()) > 2 else desc


def generate_pdf_order(
    order_data: dict,
    output_path: Path,
    hard_cases: list[str],
    catalog: list[dict]
) -> tuple[bytes, dict]:
    """Genera un ordine in formato PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, spaceAfter=12)
    normal_style = styles["Normal"]

    story.append(Paragraph("<b>PURCHASE ORDER</b>", title_style))
    story.append(Spacer(1, 0.2*inch))

    buyer = order_data["buyer"]
    header = order_data["header"]

    po_display = header["po_number"] if "MISSING_PO_NUMBER" not in hard_cases else ""
    date_display = header["po_date"]

    if "DATE_FORMAT" in hard_cases:
        formats = ["Jan 15, 2026", "15-Jan-26", "1/15/26", "15.01.2026"]
        date_display = random.choice(formats)

    header_data = [
        ["From:", buyer["name"]],
        ["PO Number:", po_display],
        ["Date:", date_display],
        ["Ship To:", order_data.get("ship_to", {}).get("name", buyer["name"])],
    ]

    if header.get("requested_delivery_date"):
        header_data.append(["Delivery Date:", header["requested_delivery_date"]])

    header_table = Table(header_data, colWidths=[1.5*inch, 4*inch])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*inch))

    lines = order_data["lines"]
    line_data = [["Line", "Item Code", "Description", "Qty", "UoM", "Price", "Amount"]]

    for i, line in enumerate(lines):
        desc = line["description"]
        qty = line["quantity"]

        if "TYPO_DESC" in hard_cases and i == 0:
            desc = _add_typos(desc)
        if "AMBIGUOUS_DESC" in hard_cases and i == 1 and len(lines) > 1:
            desc = _make_ambiguous(desc, catalog)
        if "QTY_WORDS" in hard_cases and i == 0:
            qty = NUM_IN_WORDS.get(int(qty), str(qty))
        if "MISSING_QTY" in hard_cases and i == len(lines) - 1:
            qty = ""

        line_data.append([
            str(line["line_no"]),
            line.get("buyer_item_code") or line.get("seller_item_code") or "",
            desc[:50] + "..." if len(desc) > 50 else desc,
            str(qty),
            line["uom_raw"],
            f"${line.get('unit_price', 0):.2f}" if line.get("unit_price") else "",
            f"${line.get('line_amount', 0):.2f}" if line.get("line_amount") else ""
        ])

    if "TOTAL_MIXED" in hard_cases:
        line_data.append(["", "", "*** Please confirm availability ***", "", "", "", ""])
        line_data.append(["", "", "SUBTOTAL", "", "", "", f"${order_data.get('totals', {}).get('lines_amount_declared', 0):.2f}"])

    line_table = Table(line_data, colWidths=[0.5*inch, 1*inch, 2.5*inch, 0.6*inch, 0.5*inch, 0.8*inch, 0.8*inch])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
    ]))
    story.append(line_table)

    if "MULTIPAGE_PDF" in hard_cases:
        story.append(Spacer(1, 4*inch))
        story.append(Paragraph("<b>Page 2 - Terms and Conditions</b>", title_style))
        story.append(Spacer(1, 0.2*inch))
        for _ in range(20):
            story.append(Paragraph("Standard terms and conditions apply. Delivery within stated timeframe. "
                                   "Payment terms as agreed. All prices in USD unless otherwise specified. "
                                   "Subject to availability.", normal_style))
            story.append(Spacer(1, 0.1*inch))

    story.append(Spacer(1, 0.3*inch))
    if header.get("notes"):
        story.append(Paragraph(f"<b>Notes:</b> {header['notes']}", normal_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    doc_info = {
        "document_id": f"doc-{uuid.uuid4().hex[:8]}",
        "kind": "PDF_TEXT",
        "filename": f"{header['po_number']}.pdf",
        "mime_type": "application/pdf",
        "sha256": _sha256(pdf_bytes),
        "page_count": 2 if "MULTIPAGE_PDF" in hard_cases else 1
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)

    return pdf_bytes, doc_info


def generate_xlsx_order(
    order_data: dict,
    output_path: Path,
    hard_cases: list[str],
    catalog: list[dict]
) -> tuple[bytes, dict]:
    """Genera un ordine in formato Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Purchase Order"

    header_font = Font(bold=True, size=14)
    label_font = Font(bold=True)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    ws.merge_cells("A1:G1")
    ws["A1"] = "PURCHASE ORDER"
    ws["A1"].font = header_font
    ws["A1"].alignment = Alignment(horizontal="center")

    buyer = order_data["buyer"]
    header = order_data["header"]

    po_display = header["po_number"] if "MISSING_PO_NUMBER" not in hard_cases else ""
    date_display = header["po_date"]
    if "DATE_FORMAT" in hard_cases:
        formats = ["15-Jan-2026", "01/15/26", "January 15, 2026"]
        date_display = random.choice(formats)

    ws["A3"] = "Company:"
    ws["B3"] = buyer["name"]
    ws["A3"].font = label_font

    ws["A4"] = "PO Number:"
    ws["B4"] = po_display
    ws["A4"].font = label_font

    ws["A5"] = "Date:"
    ws["B5"] = date_display
    ws["A5"].font = label_font

    if "MISSING_DATE" in hard_cases:
        ws["B5"] = ""

    ws["A6"] = "Ship To:"
    ws["B6"] = order_data.get("ship_to", {}).get("name", "")
    ws["A6"].font = label_font

    start_row = 8
    headers_row = ["Line", "Item Code", "Description", "Quantity", "UoM", "Unit Price", "Amount"]
    for col, h in enumerate(headers_row, 1):
        cell = ws.cell(row=start_row, column=col, value=h)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center")

    lines = order_data["lines"]
    for i, line in enumerate(lines):
        row = start_row + 1 + i
        desc = line["description"]
        qty = line["quantity"]

        if "TYPO_DESC" in hard_cases and i == 0:
            desc = _add_typos(desc)
        if "AMBIGUOUS_DESC" in hard_cases and i == 1 and len(lines) > 1:
            desc = _make_ambiguous(desc, catalog)
        if "QTY_WORDS" in hard_cases and i == 0:
            qty = NUM_IN_WORDS.get(int(qty), str(qty))
        if "MISSING_QTY" in hard_cases and i == len(lines) - 1:
            qty = None

        ws.cell(row=row, column=1, value=line["line_no"]).border = thin_border
        ws.cell(row=row, column=2, value=line.get("buyer_item_code") or line.get("seller_item_code") or "").border = thin_border
        ws.cell(row=row, column=3, value=desc).border = thin_border
        ws.cell(row=row, column=4, value=qty).border = thin_border
        ws.cell(row=row, column=5, value=line["uom_raw"]).border = thin_border
        ws.cell(row=row, column=6, value=line.get("unit_price")).border = thin_border
        ws.cell(row=row, column=7, value=line.get("line_amount")).border = thin_border

    if "TOTAL_MIXED" in hard_cases:
        note_row = start_row + len(lines) + 1
        ws.cell(row=note_row, column=3, value="Note: Confirm stock before shipping")
        total_row = note_row + 1
        ws.cell(row=total_row, column=6, value="TOTAL:")
        ws.cell(row=total_row, column=7, value=order_data.get("totals", {}).get("lines_amount_declared"))

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 8
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 12

    buffer = BytesIO()
    wb.save(buffer)
    xlsx_bytes = buffer.getvalue()

    doc_info = {
        "document_id": f"doc-{uuid.uuid4().hex[:8]}",
        "kind": "XLSX",
        "filename": f"{header['po_number']}.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sha256": _sha256(xlsx_bytes),
        "page_count": None
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(xlsx_bytes)

    return xlsx_bytes, doc_info


def generate_eml_order(
    order_data: dict,
    output_path: Path,
    hard_cases: list[str],
    catalog: list[dict],
    include_attachment: bool = False
) -> tuple[bytes, list[dict]]:
    """Genera un ordine in formato email EML."""
    buyer = order_data["buyer"]
    header = order_data["header"]
    contact = buyer.get("contact", {})

    msg = MIMEMultipart()
    msg["From"] = contact.get("email", "orders@example.com")
    msg["To"] = "orders@delta-industrial.example"
    msg["Subject"] = f"PO {header['po_number']} - Order from {buyer['name']}"
    msg["Message-ID"] = f"<po-{header['po_number']}@{buyer.get('email_domain', 'example.com')}>"
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    date_display = header["po_date"]
    if "DATE_FORMAT" in hard_cases:
        formats = ["Jan 15th, 2026", "15/01/2026", "2026.01.15"]
        date_display = random.choice(formats)
    if "MISSING_DATE" in hard_cases:
        date_display = ""

    po_display = header["po_number"] if "MISSING_PO_NUMBER" not in hard_cases else "[see attached]"

    body_lines = [
        "Hello,",
        "",
        "Please process the following order:",
        "",
        f"PO Number: {po_display}",
        f"Date: {date_display}",
        f"Ship To: {order_data.get('ship_to', {}).get('name', '')}",
        "",
        "Items:",
        "------",
    ]

    lines = order_data["lines"]
    for i, line in enumerate(lines):
        desc = line["description"]
        qty = line["quantity"]

        if "TYPO_DESC" in hard_cases and i == 0:
            desc = _add_typos(desc)
        if "AMBIGUOUS_DESC" in hard_cases and i == 1 and len(lines) > 1:
            desc = _make_ambiguous(desc, catalog)
        if "QTY_WORDS" in hard_cases and i == 0:
            qty = NUM_IN_WORDS.get(int(qty), str(qty))
        if "MISSING_QTY" in hard_cases and i == len(lines) - 1:
            qty = "TBD"

        item_code = line.get("buyer_item_code") or line.get("seller_item_code") or "N/A"
        price_str = f"@ ${line['unit_price']:.2f}" if line.get("unit_price") else ""
        body_lines.append(f"  {line['line_no']}. [{item_code}] {desc}")
        body_lines.append(f"     Qty: {qty} {line['uom_raw']} {price_str}")

    if "TOTAL_MIXED" in hard_cases:
        body_lines.append("")
        body_lines.append("Please confirm stock availability before shipping.")
        body_lines.append(f"Expected Total: ${order_data.get('totals', {}).get('lines_amount_declared', 0):.2f}")

    body_lines.extend([
        "",
        f"Delivery requested by: {header.get('requested_delivery_date', 'ASAP')}",
        "",
        "Thank you,",
        contact.get("name", "Purchasing Dept"),
        buyer["name"],
        contact.get("phone", ""),
    ])

    body_text = "\n".join(body_lines)
    msg.attach(MIMEText(body_text, "plain"))

    docs = []

    email_body_doc = {
        "document_id": f"doc-{uuid.uuid4().hex[:8]}",
        "kind": "EMAIL_BODY",
        "filename": None,
        "mime_type": "text/plain",
        "sha256": _sha256(body_text.encode("utf-8")),
        "page_count": None
    }
    docs.append(email_body_doc)

    if include_attachment or "EMAIL_CONTRADICTORY" in hard_cases:
        if "EMAIL_CONTRADICTORY" in hard_cases:
            modified_order = json.loads(json.dumps(order_data))
            for line in modified_order["lines"]:
                line["quantity"] = line["quantity"] * 2
                if line.get("line_amount"):
                    line["line_amount"] = line["line_amount"] * 2
            attach_bytes, attach_doc = generate_xlsx_order(
                modified_order,
                output_path.with_suffix(".xlsx"),
                [],
                catalog
            )
        else:
            attach_bytes, attach_doc = generate_xlsx_order(
                order_data,
                output_path.with_suffix(".xlsx"),
                [],
                catalog
            )

        attachment = MIMEApplication(attach_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        attachment.add_header("Content-Disposition", "attachment", filename=f"PO_{header['po_number']}.xlsx")
        msg.attach(attachment)
        docs.append(attach_doc)

    eml_bytes = msg.as_bytes()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(eml_bytes)

    return eml_bytes, docs


def _create_ground_truth(
    order_data: dict,
    documents: list[dict],
    channel: str,
    hard_cases: list[str]
) -> dict:
    """Crea il ground truth JSON conforme allo schema VOF."""
    order_id = str(uuid.uuid4())
    buyer = order_data["buyer"]
    header = order_data["header"]

    status = "VALIDATED"
    validation_issues = []

    if "MISSING_PO_NUMBER" in hard_cases:
        status = "NEEDS_REVIEW"
        validation_issues.append({
            "code": "HDR-01",
            "severity": "BLOCK",
            "path": "/header/po_number",
            "message": "Manca il numero d'ordine (PO number)"
        })

    if "MISSING_QTY" in hard_cases:
        status = "NEEDS_REVIEW"
        validation_issues.append({
            "code": "QTY-01",
            "severity": "BLOCK",
            "path": f"/lines/{len(order_data['lines'])-1}/quantity",
            "message": "Quantità mancante o non valida"
        })

    if "MISSING_DATE" in hard_cases:
        status = "NEEDS_REVIEW"
        validation_issues.append({
            "code": "HDR-02",
            "severity": "REVIEW",
            "path": "/header/po_date",
            "message": "Data ordine mancante o non plausibile"
        })

    if "EMAIL_CONTRADICTORY" in hard_cases:
        status = "NEEDS_REVIEW"
        validation_issues.append({
            "code": "ITM-04",
            "severity": "REVIEW",
            "path": "/lines",
            "message": "Quantità nel corpo email diverse dall'allegato"
        })

    if "AMBIGUOUS_DESC" in hard_cases:
        status = "NEEDS_REVIEW"
        validation_issues.append({
            "code": "ITM-03",
            "severity": "REVIEW",
            "path": "/lines/1/description",
            "message": "Descrizione ambigua, richiede conferma articolo"
        })

    if "UOM_CONVERSION" in hard_cases:
        validation_issues.append({
            "code": "UOM-03",
            "severity": "INFO",
            "path": "/lines/0",
            "message": "Conversione UoM applicata"
        })

    lines_gt = []
    for line in order_data["lines"]:
        line_gt = {
            "line_no": line["line_no"],
            "buyer_item_code": line.get("buyer_item_code"),
            "seller_item_code": line.get("seller_item_code"),
            "manufacturer_name": line.get("manufacturer_name"),
            "manufacturer_part_number": line.get("manufacturer_part_number"),
            "gtin": line.get("gtin"),
            "description": line["description"],
            "quantity": line["quantity"],
            "uom_raw": line["uom_raw"],
            "uom": line.get("uom"),
            "pack": line.get("pack"),
            "unit_price": line.get("unit_price"),
            "price_uom": line.get("price_uom"),
            "price_basis_qty": line.get("price_basis_qty"),
            "discount_pct": line.get("discount_pct"),
            "line_amount": line.get("line_amount"),
            "requested_delivery_date": line.get("requested_delivery_date"),
            "notes": line.get("notes"),
            "resolution": line.get("resolution")
        }
        lines_gt.append(line_gt)

    ground_truth = {
        "schema_version": "1.0",
        "order_id": order_id,
        "tenant_id": "delta-industrial-supply",
        "document_type": "ORIGINAL",
        "status": status,
        "source": {
            "channel": channel,
            "message_id": f"<po-{header['po_number']}@{buyer.get('email_domain', 'example.com')}>" if channel.startswith("EMAIL") else None,
            "from_address": buyer.get("contact", {}).get("email") if channel.startswith("EMAIL") else None,
            "subject": f"PO {header['po_number']} - Order from {buyer['name']}" if channel.startswith("EMAIL") else None,
            "received_at": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "documents": documents
        },
        "buyer": {
            "name": buyer["name"],
            "code_on_document": buyer.get("erp_partner_ref"),
            "tax_id": buyer.get("tax_id"),
            "gln": None,
            "peppol_endpoint": None,
            "address": buyer.get("address"),
            "contact": buyer.get("contact"),
            "resolved": {
                "erp_partner_id": buyer.get("erp_partner_id"),
                "erp_partner_ref": buyer.get("erp_partner_ref"),
                "method": "EMAIL_DOMAIN" if channel.startswith("EMAIL") else "CODE",
                "score": 0.99
            }
        },
        "seller": {
            "name": "Delta Industrial Supply LLC (SYNTHETIC)",
            "code_on_document": None,
            "tax_id": None,
            "address": {
                "line1": "55 Commerce Dr",
                "city": "Dayton",
                "region": "OH",
                "postal_code": "45402",
                "country": "US"
            },
            "resolved": None
        },
        "header": header,
        "lines": lines_gt,
        "charges": [],
        "totals": order_data.get("totals"),
        "decision": {
            "score": 0.75 if validation_issues else 0.98,
            "route": "REVIEW" if status == "NEEDS_REVIEW" else "AUTO_POST",
            "reasons": [i["code"] for i in validation_issues] if validation_issues else []
        },
        "processing": {
            "extractor": "synthetic/generator.py",
            "prompt_version": None,
            "created_at": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": None
        }
    }

    if order_data.get("ship_to"):
        ground_truth["ship_to"] = order_data["ship_to"]

    if validation_issues:
        ground_truth["validation"] = {"issues": validation_issues}

    if hard_cases:
        ground_truth["_synthetic_metadata"] = {
            "hard_case_types": hard_cases,
            "is_hard_case": True
        }
    else:
        ground_truth["_synthetic_metadata"] = {
            "hard_case_types": [],
            "is_hard_case": False
        }

    return ground_truth


def generate_orders(
    catalog: list[dict],
    customers: list[dict],
    output_dir: Path,
    num_orders: int = 150,
    hard_case_pct: float = 0.15
) -> tuple[list[dict], dict]:
    """Genera tutti gli ordini con documenti e ground truth.

    Args:
        catalog: Lista articoli.
        customers: Lista clienti.
        output_dir: Directory di output.
        num_orders: Numero totale ordini.
        hard_case_pct: Percentuale casi difficili.

    Returns:
        (lista ground truth, manifest)
    """
    random.seed(SEED + 2)

    num_hard = int(num_orders * hard_case_pct)
    num_normal = num_orders - num_hard

    hard_case_assignments = []
    for hc_type in HARD_CASE_TYPES:
        hard_case_assignments.append([hc_type])
    while len(hard_case_assignments) < num_hard:
        combo = random.sample(HARD_CASE_TYPES, random.randint(1, 2))
        hard_case_assignments.append(combo)
    random.shuffle(hard_case_assignments)
    hard_case_assignments = hard_case_assignments[:num_hard]

    order_configs: list[list[str]] = [[] for _ in range(num_normal)]
    order_configs.extend(hard_case_assignments)
    random.shuffle(order_configs)

    pdf_dir = output_dir / "documents" / "pdf"
    xlsx_dir = output_dir / "documents" / "xlsx"
    eml_dir = output_dir / "documents" / "eml"
    gt_dir = output_dir / "ground_truth"

    for d in [pdf_dir, xlsx_dir, eml_dir, gt_dir]:
        d.mkdir(parents=True, exist_ok=True)

    ground_truths = []
    manifest_entries = []

    base_date = datetime(2026, 1, 15)
    po_counter = 1000

    formats_count = {"PDF": 0, "XLSX": 0, "EML": 0}
    target_per_format = num_orders // 3

    for order_idx, hard_cases in enumerate(order_configs):
        customer = random.choice(customers)
        style = customer["order_style"]

        available_formats = []
        for fmt in style["format_preference"]:
            if formats_count[fmt] < target_per_format + 5:
                available_formats.append(fmt)
        if not available_formats:
            available_formats = ["PDF", "XLSX", "EML"]

        if "MULTIPAGE_PDF" in hard_cases:
            doc_format = "PDF"
        elif "EMAIL_CONTRADICTORY" in hard_cases:
            doc_format = "EML"
        else:
            doc_format = random.choice(available_formats)

        formats_count[doc_format] += 1

        po_number = f"{style['po_prefix']}{po_counter:05d}"
        po_counter += 1

        order_date = base_date + timedelta(days=random.randint(0, 180))
        delivery_date = order_date + timedelta(days=random.randint(5, 21))

        num_lines = random.randint(*style["typical_lines"])
        selected_items = random.sample(catalog, min(num_lines, len(catalog)))

        lines = []
        total_amount = 0.0

        for line_no, item in enumerate(selected_items, 1):
            qty_base = random.choice([1, 2, 3, 4, 5, 6, 10, 12, 24])

            if "UOM_CONVERSION" in hard_cases and line_no == 1:
                if item.get("pack"):
                    pack = item["pack"]
                    uom_raw = f"CS of {pack['inner_count']}"
                else:
                    uom_raw = random.choice(["DZ", "DZN", "DOZEN"])
                    qty_base = random.choice([1, 2, 3])
            else:
                uom_raw = item["uom"]

            buyer_item_code = None
            seller_item_code = None

            if style.get("uses_own_codes") and customer.get("xref"):
                xref_match = next((x for x in customer["xref"] if x["sku"] == item["sku"]), None)
                if xref_match:
                    if "CUSTOMER_CODES" in hard_cases or random.random() < 0.7:
                        buyer_item_code = xref_match["customer_code"]
                    else:
                        seller_item_code = item["sku"]
                else:
                    seller_item_code = item["sku"]
            else:
                seller_item_code = item["sku"]

            unit_price = item["price"]
            line_amount = round(qty_base * unit_price, 2)
            total_amount += line_amount

            line = {
                "line_no": line_no,
                "buyer_item_code": buyer_item_code,
                "seller_item_code": seller_item_code,
                "manufacturer_name": None,
                "manufacturer_part_number": None,
                "gtin": None,
                "description": item["description"],
                "quantity": qty_base,
                "uom_raw": uom_raw,
                "uom": item["uom"],
                "pack": item.get("pack"),
                "unit_price": unit_price,
                "price_uom": item["uom"],
                "price_basis_qty": 1,
                "discount_pct": None,
                "line_amount": line_amount,
                "requested_delivery_date": None,
                "notes": None,
                "resolution": {
                    "sku": item["sku"],
                    "erp_product_id": item["erp_product_id"],
                    "erp_uom": item["uom"],
                    "erp_uom_id": random.randint(1, 50),
                    "erp_quantity": qty_base,
                    "conversion_factor": 1,
                    "method": "XREF" if buyer_item_code else "SELLER_CODE",
                    "score": 1.0 if buyer_item_code else 0.98,
                    "candidates": [],
                    "erp_list_price": unit_price
                }
            }
            lines.append(line)

        ship_to_choice = random.choice(customer["ship_to"])
        ship_to = {
            "name": ship_to_choice["name"],
            "code_on_document": ship_to_choice["code"],
            "address": ship_to_choice["address"],
            "resolved": {
                "erp_partner_id": customer["erp_partner_id"] + 1,
                "erp_partner_ref": ship_to_choice["code"],
                "method": "CODE",
                "score": 1.0
            }
        }

        order_data = {
            "buyer": {
                "name": customer["name"],
                "tax_id": customer.get("tax_id"),
                "erp_partner_id": customer["erp_partner_id"],
                "erp_partner_ref": customer["erp_partner_ref"],
                "email_domain": customer.get("email_domain"),
                "contact": customer.get("contact"),
                "address": customer.get("address")
            },
            "ship_to": ship_to,
            "header": {
                "po_number": po_number,
                "po_revision": 0,
                "po_date": _format_date(order_date, style["date_format"]),
                "requested_delivery_date": _format_date(delivery_date, "YYYY-MM-DD"),
                "currency": style["currency"],
                "buyer_reference": f"Dept {random.randint(100, 999)}",
                "payment_terms_text": random.choice(["Net 30", "Net 45", "2% 10 Net 30"]),
                "incoterms": None,
                "ship_via": random.choice(["Best Way", "UPS Ground", "FedEx", None]),
                "notes": random.choice([None, "Rush order", "Confirm availability", "Call before delivery"]),
                "language": style["language"]
            },
            "lines": lines,
            "totals": {
                "lines_amount_declared": round(total_amount, 2),
                "tax_amount_declared": None,
                "total_amount_declared": round(total_amount, 2),
                "lines_amount_computed": round(total_amount, 2)
            }
        }

        filename_base = f"order_{order_idx+1:03d}_{po_number.replace('/', '-')}"

        if doc_format == "PDF":
            channel = "FOLDER"
            _, doc_info = generate_pdf_order(
                order_data,
                pdf_dir / f"{filename_base}.pdf",
                hard_cases,
                catalog
            )
            documents = [doc_info]
        elif doc_format == "XLSX":
            channel = "FOLDER"
            _, doc_info = generate_xlsx_order(
                order_data,
                xlsx_dir / f"{filename_base}.xlsx",
                hard_cases,
                catalog
            )
            documents = [doc_info]
        else:
            channel = "EMAIL_IMAP"
            include_attach = random.random() < 0.3 or "EMAIL_CONTRADICTORY" in hard_cases
            _, documents = generate_eml_order(
                order_data,
                eml_dir / f"{filename_base}.eml",
                hard_cases,
                catalog,
                include_attachment=include_attach
            )

        ground_truth = _create_ground_truth(order_data, documents, channel, hard_cases)

        gt_path = gt_dir / f"{filename_base}.json"
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, indent=2, ensure_ascii=False)

        ground_truths.append(ground_truth)

        manifest_entries.append({
            "order_index": order_idx + 1,
            "po_number": po_number,
            "customer_id": customer["customer_id"],
            "customer_name": customer["name"],
            "format": doc_format,
            "num_lines": len(lines),
            "total_amount": round(total_amount, 2),
            "is_hard_case": bool(hard_cases),
            "hard_case_types": hard_cases,
            "document_path": str(gt_path.relative_to(output_dir)),
            "ground_truth_path": str(gt_path.relative_to(output_dir))
        })

    manifest = {
        "generated_at": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": SEED,
        "total_orders": num_orders,
        "hard_cases": num_hard,
        "hard_case_percentage": round(num_hard / num_orders * 100, 1),
        "format_distribution": formats_count,
        "orders": manifest_entries
    }

    manifest_path = output_dir / "data" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    import csv
    csv_path = output_dir / "data" / "manifest.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "order_index", "po_number", "customer_id", "customer_name",
            "format", "num_lines", "total_amount", "is_hard_case",
            "hard_case_types", "document_path", "ground_truth_path"
        ])
        writer.writeheader()
        for entry in manifest_entries:
            row = entry.copy()
            row["hard_case_types"] = ";".join(entry["hard_case_types"])
            writer.writerow(row)

    return ground_truths, manifest


if __name__ == "__main__":
    from .catalog import generate_catalog
    from .customers import generate_customers

    output_dir = Path(__file__).parent

    catalog = generate_catalog(output_dir / "data" / "catalog.json")
    print(f"Generated {len(catalog)} catalog items")

    customers = generate_customers(catalog, output_dir / "data" / "customers.json")
    print(f"Generated {len(customers)} customers")

    ground_truths, manifest = generate_orders(catalog, customers, output_dir)
    print(f"Generated {len(ground_truths)} orders")
    print(f"Hard cases: {manifest['hard_cases']} ({manifest['hard_case_percentage']}%)")
    print(f"Format distribution: {manifest['format_distribution']}")
