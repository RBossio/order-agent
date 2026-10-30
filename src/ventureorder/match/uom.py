"""Conversione UoM della riga verso l'unità di vendita del prodotto (§6.4)."""

from __future__ import annotations

from typing import Any

from ventureorder.rules.access import as_float, normalize_uom
from ventureorder.rules.reference import ProductRecord, ReferenceDataProvider


def convert_line_uom(
    provider: ReferenceDataProvider | None,
    product: ProductRecord,
    line: dict[str, Any],
) -> tuple[float | None, float | None, str]:
    """Converte quantità e UoM dell'ordine in quelle di vendita del prodotto.

    Restituisce ``(erp_quantity, conversion_factor, erp_uom)``.
    Il fattore è ``unità ERP per 1 unità d'ordine`` (qty × factor = qty ERP),
    letto da ``products.json`` tramite ``get_uom_conversion``.
    """
    sale = normalize_uom(product.sale_uom) or product.sale_uom
    qty = as_float(line.get("quantity"))
    line_uom = normalize_uom(line.get("uom")) or normalize_uom(line.get("uom_raw"))
    if qty is None:
        return None, None, sale
    if not line_uom or line_uom == sale:
        return qty, 1.0, sale
    factor: float | None = None
    if provider is not None:
        factor = provider.get_uom_conversion(line_uom, sale, product.sku)
    if factor is None:
        return qty, None, sale
    return qty * factor, factor, sale
