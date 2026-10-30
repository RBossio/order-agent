"""Test unitari del connettore Odoo (client finto, nessun server richiesto)."""

from __future__ import annotations

import json
import xmlrpc.client
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ventureorder.connectors.odoo import (
    CustomerNotFoundError,
    DuplicatePurchaseOrderError,
    FakeOdooClient,
    Json2OdooClient,
    JsonRpcOdooClient,
    OdooAuthError,
    OdooDataError,
    OdooSaleOrderConnector,
    OdooTransientError,
    ProductNotFoundError,
    XmlRpcOdooClient,
    create_client,
)
from ventureorder.connectors.odoo.mapping import (
    build_line_vals,
    client_order_ref_from_header,
    format_commitment_date,
    format_date_order,
    format_note,
    line_price_unit,
    origin_from_order_id,
    uom_field_name,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = REPO_ROOT / "schema" / "example-mro.json"


def _minimal_vof(**overrides: Any) -> dict[str, Any]:
    """VOF sintetico minimo, pronto per la pubblicazione."""
    order: dict[str, Any] = {
        "schema_version": "1.0",
        "order_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "delta-industrial-supply",
        "document_type": "ORIGINAL",
        "status": "READY_TO_POST",
        "source": {
            "channel": "API",
            "received_at": "2026-11-03T14:22:05Z",
            "documents": [
                {
                    "document_id": "d1",
                    "kind": "XLSX",
                    "sha256": "a" * 64,
                }
            ],
        },
        "buyer": {
            "name": "Acme Manufacturing Inc. (SYNTHETIC)",
            "resolved": {"erp_partner_id": 42, "erp_partner_ref": "C-ACME"},
        },
        "header": {
            "po_number": "4500012345",
            "po_date": "2026-11-03",
            "currency": "USD",
            "requested_delivery_date": "2026-11-10",
            "buyer_reference": "Maint. Dept / WO-7781",
            "ship_via": "Best Way Ground",
            "notes": "Deliver Mon-Fri 7am-3pm.",
        },
        "lines": [
            {
                "line_no": 1,
                "description": "HEX CAP SCREW 1/2-13 X 2 GR5 ZINC",
                "quantity": 4,
                "uom_raw": "BX",
                "uom": "BX",
                "unit_price": 18.75,
                "price_uom": "BX",
                "buyer_item_code": "ACM-HW-00412",
                "resolution": {
                    "sku": "FST-HCS-12-13X2-G5Z-B50",
                    "erp_product_id": 1012,
                    "erp_uom": "BX",
                    "erp_uom_id": 31,
                    "erp_quantity": 4,
                    "conversion_factor": 1,
                },
            }
        ],
    }
    order.update(overrides)
    return order


def _seeded_client() -> FakeOdooClient:
    client = FakeOdooClient(major_version=19)
    client.seed_partner(id=42, ref="C-ACME")
    client.seed_partner(id=43, name="Acme Billing", parent_id=42)
    client.seed_partner(id=44, name="Acme Plant 2", parent_id=42)
    client.seed_product(id=1012, default_code="FST-HCS-12-13X2-G5Z-B50", uom_id=31)
    client.seed_product(id=2207, default_code="PPE-GLV-NIT6-L-BLU", uom_id=31)
    return client


def _connector(client: FakeOdooClient) -> OdooSaleOrderConnector:
    return OdooSaleOrderConnector(
        client,
        max_attempts=3,
        backoff_seconds=(0.0, 0.0, 0.0),
        jitter=False,
        sleep=lambda _seconds: None,
    )


class TestMapping:
    """Funzioni pure VOF → sale.order."""

    def test_origin_and_client_order_ref(self) -> None:
        assert origin_from_order_id("abc") == "VO:abc"
        assert client_order_ref_from_header({"po_number": "4500012345"}) == "4500012345"
        assert client_order_ref_from_header({"po_number": "4500012345", "po_revision": 2}) == (
            "4500012345-R2"
        )

    def test_dates_and_note(self) -> None:
        assert format_date_order("2026-11-03", "2026-11-03T14:22:05Z") == "2026-11-03 14:22:05"
        assert format_commitment_date("2026-11-10") == "2026-11-10 12:00:00"
        note = format_note(
            {
                "notes": "Deliver <dock>",
                "buyer_reference": "WO-1",
                "ship_via": "Ground",
            }
        )
        assert note is not None
        assert "&lt;dock&gt;" in note
        assert "WO-1" in note
        assert "Ground" in note

    def test_uom_field_depends_on_version(self) -> None:
        assert uom_field_name(19) == "product_uom_id"
        assert uom_field_name(18) == "product_uom"

    def test_price_conversion_cs_to_bx(self) -> None:
        line = {
            "quantity": 3,
            "unit_price": 89.5,
            "price_uom": "CS",
            "resolution": {
                "erp_uom": "BX",
                "erp_quantity": 30,
                "conversion_factor": 10,
            },
        }
        assert line_price_unit(line) == 8.95

    def test_price_same_uom_keeps_unit_price(self) -> None:
        line = {
            "quantity": 2,
            "unit_price": 3.1,
            "price_uom": "EA",
            "resolution": {
                "erp_uom": "EA",
                "erp_quantity": 24,
                "conversion_factor": 12,
            },
        }
        assert line_price_unit(line) == 3.1

    def test_line_vals_include_product_qty_uom_price(self) -> None:
        line = _minimal_vof()["lines"][0]
        vals = build_line_vals(line, product_id=1012, uom_id=31, major_version=19)
        assert vals["product_id"] == 1012
        assert vals["product_uom_qty"] == 4
        assert vals["product_uom_id"] == 31
        assert vals["price_unit"] == 18.75
        assert vals["sequence"] == 10
        assert "Cod. cliente: ACM-HW-00412" in vals["name"]


class TestPostDraft:
    """Creazione bozza, idempotenza ed errori chiari."""

    def test_creates_draft_with_lines(self) -> None:
        client = _seeded_client()
        posted = _connector(client).post_draft(_minimal_vof())

        assert posted.reused is False
        assert posted.state == "draft"
        assert posted.origin == "VO:11111111-1111-1111-1111-111111111111"
        assert posted.client_order_ref == "4500012345"
        assert posted.partner_id == 42
        assert len(posted.line_ids) == 1

        created = client.created_orders()
        assert len(created) == 1
        assert created[0]["state"] == "draft"
        line = client.records["sale.order.line"][posted.line_ids[0]]
        assert line["product_id"] == 1012
        assert line["product_uom_qty"] == 4
        assert line["product_uom_id"] == 31
        assert line["price_unit"] == 18.75

        confirm_calls = [c for c in client.calls if c[1] == "action_confirm"]
        assert confirm_calls == []

    def test_never_sets_state_sale_or_confirms(self) -> None:
        client = _seeded_client()
        _connector(client).post_draft(_minimal_vof())
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1
        values = create_calls[0][2]
        assert "state" not in values
        assert all(c[1] != "action_confirm" for c in client.calls)

    def test_idempotent_by_origin(self) -> None:
        client = _seeded_client()
        connector = _connector(client)
        first = connector.post_draft(_minimal_vof())
        second = connector.post_draft(_minimal_vof())

        assert second.reused is True
        assert second.odoo_id == first.odoo_id
        assert len(client.created_orders()) == 1

    def test_idempotent_by_po_and_customer(self) -> None:
        client = _seeded_client()
        connector = _connector(client)
        first = connector.post_draft(_minimal_vof())
        other = _minimal_vof(order_id="22222222-2222-2222-2222-222222222222")

        with pytest.raises(DuplicatePurchaseOrderError) as exc_info:
            connector.post_draft(other)

        err = exc_info.value
        assert err.odoo_id == first.odoo_id
        assert err.origin == first.origin
        assert err.client_order_ref == "4500012345"
        assert "DUP-01" in str(err)
        assert len(client.created_orders()) == 1
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1

    def test_duplicate_po_different_origin_is_rejected(self) -> None:
        client = _seeded_client()
        client.records["sale.order"][77] = {
            "id": 77,
            "name": "S00077",
            "state": "sale",
            "origin": "VO:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "client_order_ref": "4500012345",
            "partner_id": 42,
            "amount_untaxed": 10.0,
            "order_line": [],
        }

        with pytest.raises(DuplicatePurchaseOrderError) as exc_info:
            _connector(client).post_draft(_minimal_vof())

        err = exc_info.value
        assert err.odoo_id == 77
        assert err.name == "S00077"
        assert err.origin == "VO:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert err.client_order_ref == "4500012345"
        assert [rec["id"] for rec in client.created_orders()] == [77]
        assert [c for c in client.calls if c[1] == "create"] == []

    def test_crash_after_create_does_not_duplicate(self) -> None:
        client = _seeded_client()
        client.fail_after_create = OdooTransientError("crash dopo create")
        connector = _connector(client)

        posted = connector.post_draft(_minimal_vof())

        assert posted.reused is True
        assert len(client.created_orders()) == 1
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1

    def test_reconcile_search_transient_error_is_retried(self) -> None:
        client = _seeded_client()
        client.fail_after_create = OdooTransientError("crash dopo create")
        client.search_read_transient_after_create = 1
        posted = _connector(client).post_draft(_minimal_vof())

        assert posted.reused is True
        assert posted.origin == "VO:11111111-1111-1111-1111-111111111111"
        assert len(client.created_orders()) == 1
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1

    def test_transient_error_retries_then_succeeds(self) -> None:
        client = _seeded_client()
        client.transient_failures_before_success = 2
        posted = _connector(client).post_draft(_minimal_vof())
        assert posted.reused is False
        assert posted.state == "draft"
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 3

    def test_auth_error_is_not_retried(self) -> None:
        client = _seeded_client()
        client.create_error = OdooAuthError("chiave API scaduta")
        with pytest.raises(OdooAuthError, match="chiave API"):
            _connector(client).post_draft(_minimal_vof())
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1

    def test_validation_error_is_not_retried(self) -> None:
        client = _seeded_client()
        client.create_error = OdooDataError("prodotto non vendibile")
        with pytest.raises(OdooDataError, match="non vendibile"):
            _connector(client).post_draft(_minimal_vof())
        create_calls = [c for c in client.calls if c[1] == "create"]
        assert len(create_calls) == 1

    def test_customer_missing_resolved(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["buyer"] = {"name": "Ignoto (SYNTHETIC)", "resolved": None}
        with pytest.raises(CustomerNotFoundError, match="non risolto"):
            _connector(client).post_draft(order)
        assert client.created_orders() == []

    def test_customer_id_does_not_exist(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["buyer"]["resolved"] = {"erp_partner_id": 9999}
        with pytest.raises(CustomerNotFoundError, match="id=9999"):
            _connector(client).post_draft(order)

    def test_customer_resolved_by_ref(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["buyer"]["resolved"] = {"erp_partner_ref": "C-ACME"}
        posted = _connector(client).post_draft(order)
        assert posted.partner_id == 42

    def test_product_missing(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["lines"][0]["resolution"] = {"erp_product_id": 404, "sku": "NO-SUCH"}
        with pytest.raises(ProductNotFoundError, match="id=404"):
            _connector(client).post_draft(order)
        assert client.created_orders() == []

    def test_product_resolved_by_sku(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["lines"][0]["resolution"] = {"sku": "FST-HCS-12-13X2-G5Z-B50"}
        posted = _connector(client).post_draft(order)
        line = client.records["sale.order.line"][posted.line_ids[0]]
        assert line["product_id"] == 1012

    def test_odoo18_uses_product_uom(self) -> None:
        client = _seeded_client()
        client._major_version = 18
        posted = _connector(client).post_draft(_minimal_vof())
        line = client.records["sale.order.line"][posted.line_ids[0]]
        assert "product_uom" in line
        assert "product_uom_id" not in line

    def test_example_mro_posts_all_resolved_lines(self) -> None:
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        client = FakeOdooClient(major_version=19)
        client.seed_partner(id=42, ref="C-ACME")
        client.seed_partner(id=43, name="Billing")
        client.seed_partner(id=44, name="Shipping")
        for line in example["lines"]:
            resolution = line["resolution"]
            client.seed_product(
                id=resolution["erp_product_id"],
                default_code=resolution["sku"],
                uom_id=resolution["erp_uom_id"],
            )

        posted = _connector(client).post_draft(example)
        assert posted.state == "draft"
        assert len(posted.line_ids) == 5
        created = client.created_orders()[0]
        assert created["partner_invoice_id"] == 43
        assert created["partner_shipping_id"] == 44
        assert created["client_order_ref"] == "4500012345"
        assert created["origin"] == f"VO:{example['order_id']}"

        lines = [client.records["sale.order.line"][i] for i in posted.line_ids]
        assert [ln["product_id"] for ln in lines] == [1012, 2207, 3110, 3301, 2350]
        assert [ln["product_uom_qty"] for ln in lines] == [4, 30, 6, 2, 24]
        assert lines[1]["price_unit"] == 8.95
        assert lines[4]["price_unit"] == 3.1

    def test_to_erp_ref(self) -> None:
        client = _seeded_client()
        posted = _connector(client).post_draft(_minimal_vof())
        ref = posted.to_erp_ref(posted_at="2026-11-03T14:22:41Z")
        assert ref["system"] == "ODOO"
        assert ref["external_id"] == str(posted.odoo_id)
        assert ref["name"] == posted.name
        assert ref["posted_at"] == "2026-11-03T14:22:41Z"

    def test_missing_po_number(self) -> None:
        client = _seeded_client()
        order = _minimal_vof()
        order["header"] = {"po_date": "2026-11-03", "currency": "USD"}
        with pytest.raises(OdooDataError, match="po_number"):
            _connector(client).post_draft(order)

    def test_missing_lines(self) -> None:
        client = _seeded_client()
        with pytest.raises(OdooDataError, match="senza righe"):
            _connector(client).post_draft(_minimal_vof(lines=[]))


class TestJsonRpcTransport:
    """Il client JSON-RPC costruisce il payload atteso da Odoo."""

    def test_version_payload(self) -> None:
        captured: dict[str, Any] = {}

        def fake_post(url: str, payload: dict[str, Any], **_kwargs: Any) -> tuple[int, Any]:
            captured["url"] = url
            captured["payload"] = payload
            return 200, {"jsonrpc": "2.0", "id": 1, "result": {"server_version": "19.0-20261015"}}

        client = JsonRpcOdooClient("http://localhost:8069", "vo_demo", "admin", "secret")
        with patch("ventureorder.connectors.odoo.rpc._post_json", fake_post):
            assert client.major_version == 19
        assert captured["url"] == "http://localhost:8069/jsonrpc"
        assert captured["payload"]["params"]["service"] == "common"
        assert captured["payload"]["params"]["method"] == "version"

    def test_create_uses_execute_kw(self) -> None:
        calls: list[dict[str, Any]] = []

        def fake_post(_url: str, payload: dict[str, Any], **_kwargs: Any) -> tuple[int, Any]:
            method = payload["params"]["method"]
            calls.append(payload)
            if method == "authenticate":
                return 200, {"jsonrpc": "2.0", "id": 1, "result": 7}
            return 200, {"jsonrpc": "2.0", "id": 2, "result": 55}

        client = JsonRpcOdooClient("http://odoo.example", "vo_demo", "bot", "key")
        with patch("ventureorder.connectors.odoo.rpc._post_json", fake_post):
            new_id = client.create("sale.order", {"partner_id": 42})
        assert new_id == 55
        execute = next(p for p in calls if p["params"]["method"] == "execute_kw")
        args = execute["params"]["args"]
        assert args[0] == "vo_demo"
        assert args[3] == "sale.order"
        assert args[4] == "create"
        assert args[5] == [{"partner_id": 42}]

    def test_jsonrpc_error_access_denied(self) -> None:
        def fake_post(_url: str, _payload: dict[str, Any], **_kwargs: Any) -> tuple[int, Any]:
            return 200, {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "message": "Odoo Server Error",
                    "data": {"name": "odoo.exceptions.AccessDenied", "message": "Access Denied"},
                },
            }

        client = JsonRpcOdooClient("http://localhost:8069", "vo_demo", "admin", "x")
        with patch("ventureorder.connectors.odoo.rpc._post_json", fake_post):
            with pytest.raises(OdooAuthError, match="Access Denied"):
                client.version()

    def test_json2_create_body(self) -> None:
        captured: dict[str, Any] = {}

        def fake_post(url: str, payload: dict[str, Any], **kwargs: Any) -> tuple[int, Any]:
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = kwargs.get("headers")
            return 200, [88]

        client = Json2OdooClient("http://localhost:8069", "vo_demo", "api-key")
        with patch("ventureorder.connectors.odoo.rpc._post_json", fake_post):
            assert client.create("sale.order", {"partner_id": 1}) == 88
        assert captured["url"] == "http://localhost:8069/json/2/sale.order/create"
        assert captured["payload"] == {"vals_list": [{"partner_id": 1}]}
        assert captured["headers"]["Authorization"] == "bearer api-key"

    def test_factory_jsonrpc_and_fake(self) -> None:
        rpc = create_client("http://localhost:8069", "vo_demo", "a", "b", transport="jsonrpc")
        assert isinstance(rpc, JsonRpcOdooClient)
        fake = create_client("http://x", "db", "u", "p", transport="fake")
        assert isinstance(fake, FakeOdooClient)

    def test_factory_xmlrpc_passes_timeout(self) -> None:
        client = create_client(
            "http://localhost:8069",
            "vo_demo",
            "a",
            "b",
            transport="xmlrpc",
            timeout=12.5,
        )
        assert isinstance(client, XmlRpcOdooClient)
        assert client.timeout == 12.5
        common_transport = client.common._ServerProxy__transport
        models_transport = client.models._ServerProxy__transport
        assert common_transport.timeout == 12.5
        assert models_transport.timeout == 12.5
        assert isinstance(common_transport, xmlrpc.client.Transport)
        assert not isinstance(common_transport, xmlrpc.client.SafeTransport)

    def test_xmlrpc_https_uses_safe_transport_with_timeout(self) -> None:
        client = XmlRpcOdooClient("https://odoo.example", "vo_demo", "a", "b", timeout=7.0)
        transport = client.common._ServerProxy__transport
        assert transport.timeout == 7.0
        assert isinstance(transport, xmlrpc.client.SafeTransport)

    def test_factory_unknown_transport(self) -> None:
        with pytest.raises(ValueError, match="sconosciuto"):
            create_client("http://x", "db", "u", "p", transport="sap")
