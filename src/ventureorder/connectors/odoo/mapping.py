"""Mappatura pura VOF → valori ``sale.order`` / ``sale.order.line``.

Le funzioni non parlano con Odoo: ricevono id già risolti e producono
i dizionari da passare a ``create``. Così i test unitari restano offline.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any

ORIGIN_PREFIX = "VO:"


def origin_from_order_id(order_id: str) -> str:
    """Chiave di idempotenza scritta in ``sale.order.origin``."""
    value = (order_id or "").strip()
    if not value:
        raise ValueError("order_id obbligatorio per la chiave di idempotenza")
    return f"{ORIGIN_PREFIX}{value}"


def client_order_ref_from_header(header: Mapping[str, Any]) -> str:
    """Riferimento cliente: numero PO, con suffisso revisione se > 0."""
    po = str(header.get("po_number") or "").strip()
    if not po:
        raise ValueError("header.po_number obbligatorio")
    revision = int(header.get("po_revision") or 0)
    if revision > 0:
        return f"{po}-R{revision}"
    return po


def format_date_order(po_date: str | None, received_at: str | None) -> str | None:
    """Datetime UTC ``YYYY-MM-DD HH:MM:SS`` per ``date_order``."""
    if not po_date:
        return None
    time_part = "00:00:00"
    if received_at:
        normalized = received_at.replace("T", " ").replace("Z", "")
        if len(normalized) >= 19 and normalized[10] == " ":
            time_part = normalized[11:19]
    return f"{po_date} {time_part}"


def format_commitment_date(requested_delivery_date: str | None) -> str | None:
    """Datetime a mezzogiorno UTC per evitare slittamenti di fuso."""
    if not requested_delivery_date:
        return None
    return f"{requested_delivery_date} 12:00:00"


def format_note(header: Mapping[str, Any]) -> str | None:
    """Note HTML della testata (note, riferimento buyer, vettore)."""
    parts: list[str] = []
    notes = header.get("notes")
    if notes:
        parts.append(html.escape(str(notes)))
    extras: list[str] = []
    buyer_ref = header.get("buyer_reference")
    if buyer_ref:
        extras.append(f"Ref: {html.escape(str(buyer_ref))}")
    ship_via = header.get("ship_via")
    if ship_via:
        extras.append(f"Ship via: {html.escape(str(ship_via))}")
    if extras:
        parts.append(" · ".join(extras))
    if not parts:
        return None
    return "".join(f"<p>{part}</p>" for part in parts)


def uom_field_name(major_version: int) -> str:
    """Odoo 19 rinomina ``product_uom`` → ``product_uom_id``."""
    return "product_uom_id" if major_version >= 19 else "product_uom"


def line_quantity(line: Mapping[str, Any]) -> float:
    """Quantità già convertita se presente, altrimenti quella del PO."""
    resolution = line.get("resolution") or {}
    qty = resolution.get("erp_quantity")
    if qty is None:
        qty = line.get("quantity")
    if qty is None:
        raise ValueError("quantità mancante sulla riga")
    return float(qty)


def line_price_unit(line: Mapping[str, Any]) -> float | None:
    """Prezzo unitario da scrivere su ``price_unit``, già allineato all'UoM ERP.

    - se ``price_uom`` coincide con l'UoM ERP si usa ``unit_price``;
    - se c'è un ``conversion_factor`` e il prezzo è nell'UoM del PO,
      si divide (es. 89,50 / CS → 8,95 / BX con fattore 10);
    - ``price_basis_qty`` (es. "per 100") scala ulteriormente il prezzo.
    """
    unit_price = line.get("unit_price")
    if unit_price is None:
        return None
    price = float(unit_price)
    resolution = line.get("resolution") or {}
    price_uom = line.get("price_uom")
    erp_uom = resolution.get("erp_uom")
    factor = resolution.get("conversion_factor")
    if price_uom and erp_uom and price_uom != erp_uom and factor and float(factor) != 1:
        price = price / float(factor)
    elif (
        (not price_uom or not erp_uom or price_uom != erp_uom)
        and factor
        and float(factor) != 1
        and resolution.get("erp_quantity") is not None
        and line.get("quantity")
        and float(resolution["erp_quantity"]) != float(line["quantity"])
    ):
        price = price / float(factor)
    basis = line.get("price_basis_qty")
    if basis and float(basis) != 1:
        price = price / float(basis)
    return price


def line_name(line: Mapping[str, Any]) -> str:
    """Descrizione riga + codice articolo del cliente, come da architettura."""
    description = str(line.get("description") or "").strip() or "Riga ordine"
    buyer_code = line.get("buyer_item_code")
    if buyer_code:
        return f"{description}\nCod. cliente: {buyer_code}"
    return description


def build_line_vals(
    line: Mapping[str, Any],
    *,
    product_id: int,
    uom_id: int | None,
    major_version: int,
    use_po_price: bool = True,
) -> dict[str, Any]:
    """Valori di una ``sale.order.line`` (comando ``[0, 0, vals]``)."""
    line_no = int(line.get("line_no") or 1)
    vals: dict[str, Any] = {
        "sequence": line_no * 10,
        "product_id": product_id,
        "product_uom_qty": line_quantity(line),
        "name": line_name(line),
    }
    if uom_id is not None:
        vals[uom_field_name(major_version)] = uom_id
    if use_po_price:
        price = line_price_unit(line)
        if price is not None:
            vals["price_unit"] = price
    discount = line.get("discount_pct")
    if discount is not None:
        vals["discount"] = float(discount)
    return vals


def build_order_vals(
    order: Mapping[str, Any],
    *,
    partner_id: int,
    invoice_partner_id: int | None,
    shipping_partner_id: int | None,
    order_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Valori della testata ``sale.order`` con righe atomiche."""
    header = order.get("header") or {}
    source = order.get("source") or {}
    vals: dict[str, Any] = {
        "partner_id": partner_id,
        "client_order_ref": client_order_ref_from_header(header),
        "origin": origin_from_order_id(str(order.get("order_id") or "")),
        "order_line": [[0, 0, line] for line in order_lines],
    }
    if invoice_partner_id:
        vals["partner_invoice_id"] = invoice_partner_id
    if shipping_partner_id:
        vals["partner_shipping_id"] = shipping_partner_id
    date_order = format_date_order(header.get("po_date"), source.get("received_at"))
    if date_order:
        vals["date_order"] = date_order
    commitment = format_commitment_date(header.get("requested_delivery_date"))
    if commitment:
        vals["commitment_date"] = commitment
    note = format_note(header)
    if note:
        vals["note"] = note
    return vals
