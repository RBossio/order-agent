"""Test di integrazione del connettore contro Odoo in Docker.

Saltato automaticamente se Odoo non è raggiungibile o i dati seed
MRO non sono presenti. Non gira in CI (marker ``integration``).
"""

from __future__ import annotations

import os
import uuid

import pytest

from ventureorder.connectors.odoo import (
    OdooSaleOrderConnector,
    client_from_env,
    is_odoo_available,
)

pytestmark = pytest.mark.integration


def _odoo_ready() -> bool:
    if not is_odoo_available(timeout=3.0):
        return False
    password = (
        os.environ.get("ODOO_PASSWORD")
        or os.environ.get("ODOO_API_KEY")
        or os.environ.get("ODOO_ADMIN_PASSWORD")
    )
    return bool(password)


odoo_skip = pytest.mark.skipif(
    not _odoo_ready(),
    reason="Odoo non disponibile o credenziali mancanti (ODOO_PASSWORD / ODOO_ADMIN_PASSWORD)",
)


def _synthetic_vof(partner_id: int, product_id: int, uom_id: int | None, sku: str) -> dict:
    order_id = str(uuid.uuid4())
    resolution: dict = {
        "sku": sku,
        "erp_product_id": product_id,
        "erp_quantity": 2,
    }
    if uom_id is not None:
        resolution["erp_uom_id"] = uom_id
    return {
        "schema_version": "1.0",
        "order_id": order_id,
        "tenant_id": "delta-industrial-supply",
        "document_type": "ORIGINAL",
        "status": "READY_TO_POST",
        "source": {
            "channel": "API",
            "received_at": "2026-10-30T08:00:00Z",
            "documents": [
                {
                    "document_id": "itg-1",
                    "kind": "XLSX",
                    "sha256": "b" * 64,
                }
            ],
        },
        "buyer": {
            "name": "Acme Company (SYNTHETIC)",
            "resolved": {"erp_partner_id": partner_id, "erp_partner_ref": "C-ACME"},
        },
        "header": {
            "po_number": f"VO-ITG-{order_id[:8]}",
            "po_date": "2026-10-30",
            "currency": "USD",
            "notes": "Ordine sintetico di integrazione VentureOrder.",
        },
        "lines": [
            {
                "line_no": 1,
                "description": "Riga integrazione sintetica",
                "quantity": 2,
                "uom_raw": "EA",
                "unit_price": 1.25,
                "resolution": resolution,
            }
        ],
    }


@odoo_skip
def test_post_draft_against_real_odoo() -> None:
    """Crea una bozza reale, la rielabora senza duplicati, poi la cancella."""
    client = client_from_env()
    partners = client.search_read(
        "res.partner",
        [("ref", "=", "C-ACME")],
        ["id", "name", "ref"],
        limit=1,
    )
    products = client.search_read(
        "product.product",
        [("default_code", "=", "ADH-EPX-000")],
        ["id", "default_code", "uom_id"],
        limit=1,
    )
    if not partners or not products:
        pytest.skip("Seed MRO assente: servono cliente C-ACME e SKU ADH-EPX-000")

    partner_id = int(partners[0]["id"])
    product = products[0]
    product_id = int(product["id"])
    uom = product.get("uom_id")
    uom_id = int(uom[0]) if isinstance(uom, list | tuple) else (int(uom) if uom else None)

    order = _synthetic_vof(partner_id, product_id, uom_id, "ADH-EPX-000")
    connector = OdooSaleOrderConnector(
        client,
        max_attempts=3,
        backoff_seconds=(0.5, 1.0, 2.0),
        jitter=False,
    )

    created_id = None
    try:
        first = connector.post_draft(order)
        created_id = first.odoo_id
        assert first.state == "draft"
        assert first.reused is False
        assert first.partner_id == partner_id
        assert first.origin == f"VO:{order['order_id']}"
        assert len(first.line_ids) >= 1

        second = connector.post_draft(order)
        assert second.odoo_id == first.odoo_id
        assert second.reused is True
        assert second.state == "draft"

        duplicates = client.search_count(
            "sale.order",
            [("origin", "=", first.origin)],
        )
        assert duplicates == 1
    finally:
        if created_id is not None:
            client.unlink("sale.order", [created_id])
