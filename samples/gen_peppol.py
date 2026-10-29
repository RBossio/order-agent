#!/usr/bin/env python3
"""Riferimento: VOF -> Peppol BIS Order 3 (UBL 2.1 Order).

Profilo SELLER. Dati sintetici.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lxml import etree

NAMESPACES = {
    "": "urn:oasis:names:specification:ubl:schema:xsd:Order-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}

CAC_NS = f"{{{NAMESPACES['cac']}}}"
CBC_NS = f"{{{NAMESPACES['cbc']}}}"

REC20_UOM_MAP = {
    "EA": "EA",
    "BX": "BX",
    "CS": "CS",
    "DZN": "DZN",
    "GLL": "GLL",
}


def compute_gln_check_digit(base12: str) -> str:
    """Compute GLN with valid GS1 check digit."""
    total = sum(
        int(digit) * (3 if idx % 2 == 0 else 1)
        for idx, digit in enumerate(reversed(base12))
    )
    check_digit = (10 - total % 10) % 10
    return base12 + str(check_digit)


def format_number(value: float) -> str:
    """Format a number removing trailing zeros."""
    return f"{value:f}".rstrip("0").rstrip(".")


def add_subelement(
    parent: etree._Element,
    tag: str,
    text: str | None = None,
    **attributes: str,
) -> etree._Element:
    """Add a subelement with the appropriate namespace prefix."""
    if tag.startswith("cbc:"):
        full_tag = CBC_NS + tag[4:]
    else:
        full_tag = CAC_NS + tag[4:]

    element = etree.SubElement(parent, full_tag, **attributes)
    if text is not None:
        element.text = str(text)
    return element


def add_party(
    root: etree._Element,
    tag: str,
    party: dict[str, Any],
    gln: str,
    include_address: bool,
) -> None:
    """Add a party element to the document."""
    party_wrapper = add_subelement(root, tag)
    party_elem = add_subelement(party_wrapper, "cac:Party")

    add_subelement(party_elem, "cbc:EndpointID", gln, schemeID="0088")
    party_id = add_subelement(party_elem, "cac:PartyIdentification")
    add_subelement(party_id, "cbc:ID", gln, schemeID="0088")

    party_name = add_subelement(party_elem, "cac:PartyName")
    add_subelement(party_name, "cbc:Name", party["name"])

    if include_address:
        address = party["address"]
        postal_addr = add_subelement(party_elem, "cac:PostalAddress")
        add_subelement(postal_addr, "cbc:StreetName", address["line1"])
        add_subelement(postal_addr, "cbc:CityName", address["city"])
        add_subelement(postal_addr, "cbc:PostalZone", address["postal_code"])
        add_subelement(postal_addr, "cbc:CountrySubentity", address["region"])
        country = add_subelement(postal_addr, "cac:Country")
        add_subelement(country, "cbc:IdentificationCode", address["country"])

    legal_entity = add_subelement(party_elem, "cac:PartyLegalEntity")
    add_subelement(legal_entity, "cbc:RegistrationName", party["name"])


def generate_peppol_order(order: dict[str, Any], output_dir: Path) -> float:
    """Generate Peppol BIS Order 3 (UBL 2.1) file.

    Returns the total amount.
    """
    header = order["header"]
    buyer_gln = compute_gln_check_digit("999990000042")
    seller_gln = compute_gln_check_digit("999990000001")

    nsmap = {None: NAMESPACES[""], "cac": NAMESPACES["cac"], "cbc": NAMESPACES["cbc"]}
    root = etree.Element(f"{{{NAMESPACES['']}}}Order", nsmap=nsmap)

    add_subelement(root, "cbc:CustomizationID", "urn:fdc:peppol.eu:poacc:trns:order:3")
    add_subelement(root, "cbc:ProfileID", "urn:fdc:peppol.eu:poacc:bis:ordering:3")
    add_subelement(root, "cbc:ID", header["po_number"])
    add_subelement(root, "cbc:IssueDate", header["po_date"])

    if header.get("notes"):
        add_subelement(root, "cbc:Note", header["notes"])

    add_subelement(root, "cbc:DocumentCurrencyCode", header["currency"])

    if header.get("buyer_reference"):
        add_subelement(root, "cbc:CustomerReference", header["buyer_reference"])

    add_party(root, "cac:BuyerCustomerParty", order["buyer"], buyer_gln, True)
    add_party(root, "cac:SellerSupplierParty", order["seller"], seller_gln, True)

    delivery = add_subelement(root, "cac:Delivery")
    delivery_location = add_subelement(delivery, "cac:DeliveryLocation")
    add_subelement(delivery_location, "cbc:ID", order["ship_to"]["code_on_document"])

    ship_address = order["ship_to"]["address"]
    addr_elem = add_subelement(delivery_location, "cac:Address")
    add_subelement(addr_elem, "cbc:StreetName", ship_address["line1"])
    add_subelement(addr_elem, "cbc:AdditionalStreetName", ship_address["line2"])
    add_subelement(addr_elem, "cbc:CityName", ship_address["city"])
    add_subelement(addr_elem, "cbc:PostalZone", ship_address["postal_code"])
    add_subelement(addr_elem, "cbc:CountrySubentity", ship_address["region"])
    ship_country = add_subelement(addr_elem, "cac:Country")
    add_subelement(ship_country, "cbc:IdentificationCode", ship_address["country"])

    delivery_period = add_subelement(delivery, "cac:RequestedDeliveryPeriod")
    add_subelement(delivery_period, "cbc:EndDate", header["requested_delivery_date"])

    if header.get("payment_terms_text"):
        payment_terms = add_subelement(root, "cac:PaymentTerms")
        add_subelement(payment_terms, "cbc:Note", header["payment_terms_text"])

    total = 0.0
    line_data: list[tuple[dict[str, Any], dict[str, Any], float, float]] = []

    for line in order["lines"]:
        resolution = line["resolution"]
        factor = resolution["conversion_factor"] or 1
        price_uom = line["price_uom"]
        erp_uom = resolution["erp_uom"]
        unit_price = line["unit_price"]

        if price_uom == erp_uom:
            price = unit_price
        else:
            price = round(unit_price / factor, 4)

        amount = round(resolution["erp_quantity"] * price, 2)
        total += amount
        line_data.append((line, resolution, price, amount))

    monetary_total = add_subelement(root, "cac:AnticipatedMonetaryTotal")
    add_subelement(
        monetary_total,
        "cbc:LineExtensionAmount",
        f"{total:.2f}",
        currencyID=header["currency"],
    )
    add_subelement(
        monetary_total,
        "cbc:PayableAmount",
        f"{total:.2f}",
        currencyID=header["currency"],
    )

    for line, resolution, price, amount in line_data:
        order_line = add_subelement(root, "cac:OrderLine")
        line_item = add_subelement(order_line, "cac:LineItem")
        add_subelement(line_item, "cbc:ID", line["line_no"])
        add_subelement(
            line_item,
            "cbc:Quantity",
            format_number(resolution["erp_quantity"]),
            unitCode=REC20_UOM_MAP[resolution["erp_uom"]],
        )
        add_subelement(
            line_item,
            "cbc:LineExtensionAmount",
            f"{amount:.2f}",
            currencyID=header["currency"],
        )

        price_elem = add_subelement(line_item, "cac:Price")
        add_subelement(
            price_elem,
            "cbc:PriceAmount",
            format_number(price),
            currencyID=header["currency"],
        )
        add_subelement(
            price_elem,
            "cbc:BaseQuantity",
            "1",
            unitCode=REC20_UOM_MAP[resolution["erp_uom"]],
        )

        item = add_subelement(line_item, "cac:Item")
        add_subelement(item, "cbc:Description", line["description"])
        add_subelement(item, "cbc:Name", line["description"][:100])

        buyers_item_id = add_subelement(item, "cac:BuyersItemIdentification")
        add_subelement(buyers_item_id, "cbc:ID", line["buyer_item_code"])

        sellers_item_id = add_subelement(item, "cac:SellersItemIdentification")
        add_subelement(sellers_item_id, "cbc:ID", resolution["sku"])

        if line.get("manufacturer_part_number"):
            mfr_item_id = add_subelement(item, "cac:ManufacturersItemIdentification")
            add_subelement(mfr_item_id, "cbc:ID", line["manufacturer_part_number"])

        if line.get("gtin"):
            std_item_id = add_subelement(item, "cac:StandardItemIdentification")
            add_subelement(std_item_id, "cbc:ID", line["gtin"], schemeID="0160")

    output_path = output_dir / "sample.peppol-order.xml"
    with open(output_path, "wb") as outfile:
        outfile.write(
            etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        )

    return total


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Genera Peppol BIS Order 3 (UBL 2.1) dal VOF.",
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

    total = generate_peppol_order(order, output_dir)
    print(f"ok total {round(total, 2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
