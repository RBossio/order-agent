"""Campi di input del matcher: cosa può leggere e cosa è vietato.

Il riconoscitore **non** usa mai gli identificativi attesi dell'anagrafica
già risolti sull'ordine. Quelli servono solo come ground truth in evaluation.

Campi **ammessi** (documento estratto, come arriverebbe da un PO):

Cliente
    ``buyer.tax_id``              P.IVA / CF / EIN
    ``buyer.name``                Ragione sociale sul documento
    ``buyer.address``             Indirizzo di fatturazione
    ``buyer.contact.email``       Email di contatto
    ``source.from_address``       Mittente (dominio)
    ``bill_to.address``           Fallback indirizzo

Articolo (per riga)
    ``buyer_item_code``           Codice articolo del cliente
    ``seller_item_code``          Codice stampato come SKU distributore
    ``gtin``                      GTIN/EAN
    ``manufacturer_part_number``  MPN (non usato nella cascata attuale)
    ``description``               Descrizione riga
    ``uom`` / ``uom_raw``         Unità di misura
    ``quantity``                  Quantità (conversione UoM)
    ``pack``                      Confezione (segnale fuzzy UoM)

Campi **vietati** (ID attesi / già risolti — leakage):

    ``buyer.resolved``            erp_partner_id / erp_partner_ref
    ``buyer.code_on_document``    nel sintetico è il ``customer_id`` (es. C-NOVA)
    ``buyer.customer_id``
    ``buyer.erp_partner_id`` / ``buyer.erp_partner_ref``
    ``lines[].resolution``        sku / erp_product_id
    ``lines[].sku`` / ``product_id`` / ``erp_product_id``
    ``_synthetic_metadata``
"""

from __future__ import annotations

from typing import Any, Final

CUSTOMER_INPUT_FIELDS: Final[tuple[str, ...]] = (
    "buyer.tax_id",
    "buyer.name",
    "buyer.address",
    "buyer.contact.email",
    "source.from_address",
    "bill_to.address",
)

ITEM_INPUT_FIELDS: Final[tuple[str, ...]] = (
    "lines[].buyer_item_code",
    "lines[].seller_item_code",
    "lines[].gtin",
    "lines[].manufacturer_part_number",
    "lines[].description",
    "lines[].uom",
    "lines[].uom_raw",
    "lines[].quantity",
    "lines[].pack",
)

FORBIDDEN_ID_FIELDS: Final[tuple[str, ...]] = (
    "buyer.resolved",
    "buyer.code_on_document",
    "buyer.customer_id",
    "buyer.erp_partner_id",
    "buyer.erp_partner_ref",
    "lines[].resolution",
    "lines[].sku",
    "lines[].product_id",
    "lines[].erp_product_id",
    "_synthetic_metadata",
)

_BUYER_FORBIDDEN = frozenset(
    {
        "resolved",
        "code_on_document",
        "customer_id",
        "erp_partner_id",
        "erp_partner_ref",
    }
)
_LINE_FORBIDDEN = frozenset(
    {
        "resolution",
        "sku",
        "product_id",
        "erp_product_id",
        "erp_uom",
        "erp_quantity",
        "conversion_factor",
    }
)
_PARTY_KEEP = frozenset({"name", "tax_id", "address", "contact", "gln", "peppol_endpoint"})
_LINE_KEEP = frozenset(
    {
        "line_no",
        "buyer_item_code",
        "seller_item_code",
        "gtin",
        "manufacturer_part_number",
        "manufacturer_name",
        "description",
        "uom",
        "uom_raw",
        "quantity",
        "pack",
        "unit_price",
        "price_uom",
        "price_basis_qty",
        "line_amount",
    }
)
_CONTACT_KEEP = frozenset({"name", "email", "phone"})
_SOURCE_KEEP = frozenset({"from_address", "channel", "subject"})


def sanitize_extracted_order(vof: dict[str, Any]) -> dict[str, Any]:
    """Copia l'ordine tenendo solo i campi di input del matcher.

    Elimina ID attesi (``resolved``, ``code_on_document``, ``sku``, …)
    così evaluation e matching non possono leggerli.
    """
    out: dict[str, Any] = {}
    source_raw = vof.get("source")
    source: dict[str, Any] = source_raw if isinstance(source_raw, dict) else {}
    out["source"] = {key: source.get(key) for key in _SOURCE_KEEP}

    buyer_raw = vof.get("buyer")
    buyer: dict[str, Any] = buyer_raw if isinstance(buyer_raw, dict) else {}
    out["buyer"] = _copy_party(buyer)

    bill_to_raw = vof.get("bill_to")
    if isinstance(bill_to_raw, dict):
        out["bill_to"] = _copy_party(bill_to_raw)

    lines_out: list[dict[str, Any]] = []
    for line in vof.get("lines") or []:
        if not isinstance(line, dict):
            continue
        copied = {key: line.get(key) for key in _LINE_KEEP if key in line}
        lines_out.append(copied)
    out["lines"] = lines_out
    return out


def strip_forbidden_from_buyer(buyer: dict[str, Any]) -> dict[str, Any]:
    """Toglie gli ID attesi da un dict buyer (vista per il matcher)."""
    return {key: value for key, value in buyer.items() if key not in _BUYER_FORBIDDEN}


def strip_forbidden_from_line(line: dict[str, Any]) -> dict[str, Any]:
    """Toglie ``resolution`` / sku / product_id da una riga."""
    return {key: value for key, value in line.items() if key not in _LINE_FORBIDDEN}


def _copy_party(party: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key in _PARTY_KEEP:
        if key not in party:
            continue
        if key == "contact" and isinstance(party.get("contact"), dict):
            contact = party["contact"]
            copied["contact"] = {ck: contact.get(ck) for ck in _CONTACT_KEEP if ck in contact}
        else:
            copied[key] = party.get(key)
    return copied
