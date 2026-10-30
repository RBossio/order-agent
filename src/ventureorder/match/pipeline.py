"""Applica il riconoscimento cliente/articoli a un VOF e lo collega alle regole."""

from __future__ import annotations

from typing import Any

from ventureorder.match.customer import CustomerMatcher
from ventureorder.match.fields import sanitize_extracted_order
from ventureorder.match.items import ItemMatcher
from ventureorder.rules.access import resolved
from ventureorder.rules.reference import ReferenceDataProvider


def apply_matches(
    vof: dict[str, Any],
    provider: ReferenceDataProvider,
    *,
    overwrite: bool = False,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Popola ``buyer.resolved`` e ``lines[].resolution`` sul VOF (in place).

    Le regole CUS/ITM e lo score minimo del motore leggono queste confidenze.
    Con ``overwrite=False`` non si sovrascrivono risoluzioni già presenti
    (i test del motore iniettano ``resolved`` a mano).
    """
    customer_matcher = CustomerMatcher(provider, thresholds)
    item_matcher = ItemMatcher(provider, thresholds)
    # Il matcher vede solo i campi di input; i risultati si scrivono sul VOF originale.
    view = sanitize_extracted_order(vof)

    buyer = vof.setdefault("buyer", {})
    if not isinstance(buyer, dict):
        buyer = {}
        vof["buyer"] = buyer
    existing = resolved(buyer)
    if overwrite or not _has_partner(existing):
        match = customer_matcher.resolve(view)
        buyer["resolved"] = match.to_vof()

    customer_ref = None
    info = resolved(buyer)
    if info.get("erp_partner_ref"):
        customer_ref = str(info["erp_partner_ref"])

    lines = vof.get("lines")
    if not isinstance(lines, list):
        return vof
    view_lines = {
        line.get("line_no"): line for line in (view.get("lines") or []) if isinstance(line, dict)
    }
    for line in lines:
        if not isinstance(line, dict):
            continue
        resolution = line.get("resolution")
        if not overwrite and _has_sku(resolution if isinstance(resolution, dict) else None):
            continue
        sanitized = view_lines.get(line.get("line_no")) or {}
        order_id = str(vof.get("order_id") or "") or None
        item_match = item_matcher.resolve(sanitized, customer_ref, order_id=order_id)
        line["resolution"] = item_match.to_vof()
    return vof


def _has_partner(info: dict[str, Any]) -> bool:
    return bool(info.get("erp_partner_id") or info.get("erp_partner_ref"))


def _has_sku(resolution: dict[str, Any] | None) -> bool:
    if not resolution:
        return False
    return bool(resolution.get("sku") or resolution.get("erp_product_id"))
