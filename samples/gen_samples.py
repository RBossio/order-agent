#!/usr/bin/env python3
"""Riferimento: genera export X12 850 ed EDIFACT ORDERS D96A dal VOF (profilo SELLER).

Solo dati sintetici. Non è codice di produzione.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

X12_UOM_MAP = {
    "EA": "EA",
    "BX": "BX",
    "CS": "CA",
    "DZN": "DZ",
    "GLL": "GA",
    "PK": "PK",
    "RO": "RL",
    "PR": "PR",
    "C62": "EA",
    "H87": "EA",
}

EDIFACT_UOM_MAP = {
    "EA": "EA",
    "BX": "BX",
    "CS": "CS",
    "DZN": "DZN",
    "GLL": "GLL",
    "PK": "PK",
    "RO": "RO",
    "PR": "PR",
}


def format_number(value: float) -> str:
    """Format a number removing trailing zeros."""
    return f"{value:f}".rstrip("0").rstrip(".")


def get_seller_line(line: dict[str, Any]) -> tuple[float, str, float, str]:
    """Extract seller line data from VOF line."""
    resolution = line["resolution"]
    factor = resolution["conversion_factor"] or 1
    quantity = resolution["erp_quantity"]
    price_uom = line.get("price_uom")
    erp_uom = resolution["erp_uom"]
    unit_price = line["unit_price"]

    if price_uom == erp_uom:
        price = unit_price
    else:
        price = round(unit_price / factor, 4)

    return quantity, erp_uom, price, resolution["sku"]


def escape_edifact(text: str) -> str:
    """Escape special characters for EDIFACT."""
    for char in "?+:'":
        text = text.replace(char, "?" + char)
    return text


def build_nad_segment(qualifier: str, party: dict[str, Any]) -> str:
    """Build NAD segment for EDIFACT."""
    address = party["address"]
    code_on_doc = party.get("code_on_document")
    code_part = f"{escape_edifact(code_on_doc)}::92" if code_on_doc else ""
    street = escape_edifact(address["line1"])
    if address.get("line2"):
        street += ":" + escape_edifact(address["line2"])
    return (
        f"NAD+{qualifier}+{code_part}++{escape_edifact(party['name'])}+"
        f"{street}+{escape_edifact(address['city'])}+"
        f"{address['region']}+{address['postal_code']}+{address['country']}"
    )


def generate_x12_850(order: dict[str, Any], output_dir: Path) -> None:
    """Generate X12 850 004010 file."""
    header = order["header"]
    lines = order["lines"]
    ctrl = "000000101"

    isa = (
        f"ISA*00*{'':10}*00*{'':10}*ZZ*{'ACMEMFG':15}*ZZ*{'DELTAIND':15}"
        f"*261103*1422*U*00401*{ctrl}*0*T*>"
    )

    segments = [
        "ST*850*0001",
        f"BEG*00*SA*{header['po_number']}**{header['po_date'].replace('-', '')}",
        f"CUR*BY*{header['currency']}",
        f"REF*DP*{header['buyer_reference']}",
        f"PER*BD*{order['buyer']['contact']['name']}*EM*{order['buyer']['contact']['email']}",
        f"DTM*002*{header['requested_delivery_date'].replace('-', '')}",
    ]

    for qualifier, party in [("BT", order["bill_to"]), ("ST", order["ship_to"])]:
        address = party["address"]
        n1_seg = f"N1*{qualifier}*{party['name']}"
        if party.get("code_on_document"):
            n1_seg += f"*92*{party['code_on_document']}"

        n3_seg = "N3*" + address["line1"]
        if address.get("line2"):
            n3_seg += "*" + address["line2"]

        segments.extend([
            n1_seg,
            n3_seg,
            f"N4*{address['city']}*{address['region']}*{address['postal_code']}*{address['country']}",
        ])

    for line in lines:
        qty, uom, price, sku = get_seller_line(line)
        po1 = (
            f"PO1*{line['line_no']}*{format_number(qty)}*{X12_UOM_MAP[uom]}"
            f"*{format_number(price)}**BP*{line['buyer_item_code']}*VP*{sku}"
        )
        if line.get("gtin"):
            po1 += f"*UK*{line['gtin']}"
        if line.get("manufacturer_part_number"):
            po1 += f"*MG*{line['manufacturer_part_number']}"
        segments.extend([po1, f"PID*F****{line['description']}"])

    segments.append(f"CTT*{len(lines)}")
    segments.append(f"SE*{len(segments) + 1}*0001")

    x12_content = [
        isa,
        "GS*PO*ACMEMFG*DELTAIND*20261103*1422*101*X*004010",
        *segments,
        "GE*1*101",
        f"IEA*1*{ctrl}",
    ]

    output_path = output_dir / "sample.x12.850.txt"
    with open(output_path, "w", encoding="utf-8") as outfile:
        outfile.write("~\n".join(x12_content) + "~\n")


def generate_edifact_orders(order: dict[str, Any], output_dir: Path) -> None:
    """Generate EDIFACT ORDERS D96A file."""
    header = order["header"]
    lines = order["lines"]

    messages = [
        "UNH+1+ORDERS:D:96A:UN",
        f"BGM+220+{header['po_number']}+9",
        f"DTM+137:{header['po_date'].replace('-', '')}:102",
        f"DTM+2:{header['requested_delivery_date'].replace('-', '')}:102",
        f"FTX+AAI+++{escape_edifact(header['notes'])}",
        f"RFF+CR:{escape_edifact(header['buyer_reference'])}",
    ]

    messages.extend([
        build_nad_segment("BY", order["buyer"]),
        build_nad_segment("SU", order["seller"]),
        build_nad_segment("DP", order["ship_to"]),
        build_nad_segment("IV", order["bill_to"]),
        f"CUX+2:{header['currency']}:9",
    ])

    for line in lines:
        qty, uom, price, sku = get_seller_line(line)
        lin_seg = f"LIN+{line['line_no']}"
        if line.get("gtin"):
            lin_seg += f"++{line['gtin']}:SRV"
        messages.append(lin_seg)
        messages.append(f"PIA+5+{escape_edifact(sku)}:SA")

        pia_buyer = f"PIA+1+{escape_edifact(line['buyer_item_code'])}:IN"
        if line.get("manufacturer_part_number"):
            pia_buyer += f"+{escape_edifact(line['manufacturer_part_number'])}:MF"
        messages.append(pia_buyer)

        messages.extend([
            f"IMD+F++:::{escape_edifact(line['description'][:35])}",
            f"QTY+21:{format_number(qty)}:{EDIFACT_UOM_MAP[uom]}",
            f"PRI+AAA:{format_number(price)}",
        ])

    messages.extend(["UNS+S", f"CNT+2:{len(lines)}"])
    messages.append(f"UNT+{len(messages) + 1}+1")

    edi_content = [
        "UNA:+.? '",
        "UNB+UNOC:3+ACMEMFG:ZZZ+DELTAIND:ZZZ+261103:1422+101",
        *messages,
        "UNZ+1+101",
    ]

    output_path = output_dir / "sample.edifact.orders.txt"
    with open(output_path, "w", encoding="utf-8") as outfile:
        outfile.write(edi_content[0] + "\n" + "'\n".join(edi_content[1:]) + "'\n")


def generate_csv(order: dict[str, Any], output_dir: Path) -> None:
    """Generate generic CSV export (profilo SELLER)."""
    header = order["header"]
    lines = order["lines"]

    output_path = output_dir / "sample.generic.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "vo_order_id", "po_number", "po_revision", "po_date", "customer_ref",
            "ship_to_code", "requested_date", "currency", "line_no", "sku",
            "customer_item_code", "description", "quantity", "uom", "unit_price",
            "line_amount", "match_method", "match_score",
        ])

        for line in lines:
            qty, uom, price, sku = get_seller_line(line)
            writer.writerow([
                order["order_id"],
                header["po_number"],
                header["po_revision"],
                header["po_date"],
                order["buyer"]["resolved"]["erp_partner_ref"],
                order["ship_to"].get("code_on_document") or "",
                header["requested_delivery_date"],
                header["currency"],
                line["line_no"],
                sku,
                line["buyer_item_code"],
                line["description"],
                format_number(qty),
                uom,
                format_number(price),
                format_number(line["line_amount"]),
                line["resolution"]["method"],
                line["resolution"]["score"],
            ])


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Genera export X12 850, EDIFACT ORDERS e CSV dal VOF.",
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=str(Path(__file__).parent.parent / "schema" / "example-mro.json"),
        help="File VOF di input (default: ../schema/example-mro.json)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory di output (default: directory dello script)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Errore: file non trovato: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).parent

    with open(input_path, encoding="utf-8") as infile:
        order = json.load(infile)

    generate_x12_850(order, output_dir)
    generate_edifact_orders(order, output_dir)
    generate_csv(order, output_dir)

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
