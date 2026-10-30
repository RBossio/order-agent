"""Test della console FastAPI (pipeline reale, CSRF, senza dati inventati)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from extract.catalog import CatalogMatcher
from ventureorder.rules import DecisionRoute
from ventureorder.rules.reference import DatagenReferenceDataProvider
from ventureorder.web.app import CSRF_COOKIE, DEMO_BANNER, create_app
from ventureorder.web.inbox import STATUS_APPROVED, STATUS_REJECTED, OrderInbox
from ventureorder.web.pipeline import (
    DEMO_ALLOWLISTED_REFS,
    apply_match_if_available,
    build_reference_provider,
)

BANNER = "DEMO: dati sintetici, Odoo simulato"


def _client(inbox: OrderInbox | None = None) -> tuple[TestClient, OrderInbox]:
    store = inbox if inbox is not None else OrderInbox.for_demo()
    client = TestClient(create_app(store))
    return client, store


def _csrf(client: TestClient) -> str:
    token = client.cookies.get(CSRF_COOKIE)
    if not token:
        client.get("/orders")
        token = client.cookies.get(CSRF_COOKIE)
    assert token
    return str(token)


class TestHonestPipeline:
    def test_demo_allowlist_is_separate_from_production(self) -> None:
        demo = build_reference_provider()
        customers = demo.iter_customers()
        assert customers
        atlas = demo.get_customer_by_ref("C-ATLAS")
        assert atlas is not None
        assert atlas.allowlisted
        assert atlas.approved_orders_without_corrections >= 20
        assert DEMO_ALLOWLISTED_REFS == frozenset({"C-ATLAS"})
        others = [c for c in customers if c.erp_partner_ref != "C-ATLAS"]
        assert others
        assert all(not customer.allowlisted for customer in others)
        assert all(customer.approved_orders_without_corrections < 20 for customer in others)

        production = DatagenReferenceDataProvider.from_datagen()
        assert all(not customer.allowlisted for customer in production.iter_customers())

        matcher = CatalogMatcher(allowlist_synthetic=False)
        catalog_customers = matcher._iter_customers()
        assert catalog_customers
        assert all(not customer.allowlisted for customer in catalog_customers)
        assert all(
            customer.approved_orders_without_corrections < 20
            for customer in catalog_customers
        )

    def test_unknown_buyer_stays_unresolved(self) -> None:
        vof = {
            "buyer": {"name": "Zeta Unknown GmbH"},
            "lines": [{"line_no": 1, "description": "x"}],
        }
        matched = apply_match_if_available(vof, build_reference_provider())
        assert not (matched.get("buyer") or {}).get("resolved")
        resolution = ((matched.get("lines") or [{}])[0].get("resolution") or {})
        assert not resolution.get("sku")

    def test_match_resolves_known_customer(self) -> None:
        vof = {
            "source": {"from_address": "purchasing@acme.example"},
            "buyer": {"name": "Acme Company (SYNTHETIC)", "tax_id": "12-8713396"},
            "lines": [{"line_no": 1, "description": "unknown widget"}],
        }
        matched = apply_match_if_available(vof, build_reference_provider())
        resolved = (matched.get("buyer") or {}).get("resolved") or {}
        assert resolved.get("erp_partner_ref") == "C-ACME"

    def test_demo_orders_include_auto_post_candidates_and_review_reason(self) -> None:
        inbox = OrderInbox.for_demo()
        orders = inbox.list_orders()
        assert len(orders) == 10
        statuses = {item.ui_status for item in orders}
        assert "REVIEW" in statuses
        assert "REJECT" in statuses
        assert "AUTO_POST" in statuses
        auto = [item for item in orders if item.ui_status == "AUTO_POST"]
        assert auto
        atlas = next(
            item
            for item in auto
            if ((item.vof.get("buyer") or {}).get("resolved") or {}).get("erp_partner_ref")
            == "C-ATLAS"
        )
        assert atlas.result.score >= 0.97
        assert not atlas.result.issues
        assert atlas.po_number == "NMC-01026"
        assert any(not item.customer_resolved for item in orders)
        assert any(item.is_duplicate for item in orders)
        duplicate = next(item for item in orders if item.is_duplicate)
        assert duplicate.result.decision == DecisionRoute.REJECT
        assert any(issue.rule_id == "DUP-02" for issue in duplicate.result.issues)
        review_count = sum(1 for item in orders if item.ui_status == "REVIEW")
        assert review_count >= 7
        assert any(
            (line.get("resolution") or {}).get("candidates")
            for item in orders
            for line in (item.vof.get("lines") or [])
        )
        gated = next(item for item in orders if item.review_gate_reason)
        assert "cliente non in allowlist" in gated.review_gate_reason
        assert "storico insufficiente" in gated.review_gate_reason


class TestOrdersPages:
    def test_list_shows_synthetic_orders_banner_and_badges(self) -> None:
        client, inbox = _client()
        orders = inbox.list_orders()
        response = client.get("/orders")
        assert response.status_code == 200
        html = response.text
        assert BANNER in html
        assert DEMO_BANNER == BANNER
        assert 'class="demo-banner"' in html
        assert html.index("demo-banner") < html.index("topbar")
        assert "unpkg" not in html
        assert "htmx" not in html.lower()
        assert "Ordini in arrivo" in html
        assert "Cliente" in html
        assert "N. PO" in html
        assert "non riconosciuto" in html
        assert "REVIEW" in html
        assert "REJECT" in html
        assert "duplicato" in html
        assert "AUTO_POST" in html
        assert 'class="badge badge-auto"' in html
        assert 'class="badge badge-review"' in html
        assert 'class="badge badge-reject"' in html
        assert "cliente non in allowlist" in html
        assert "storico insufficiente" in html
        first = orders[0]
        assert first.po_number in html
        if first.customer_name != "n/d":
            assert first.customer_name in html

    def test_home_redirects_to_orders(self) -> None:
        client, _inbox = _client()
        response = client.get("/", follow_redirects=False)
        assert response.status_code in {302, 307}
        assert response.headers["location"].endswith("/orders")

    def test_detail_shows_header_lines_issues_and_nd(self) -> None:
        client, inbox = _client()
        review = next(
            item
            for item in inbox.list_orders()
            if item.ui_status == "REVIEW" and not item.customer_resolved
        )
        response = client.get(f"/orders/{review.id}")
        assert response.status_code == 200
        html = response.text
        assert BANNER in html
        assert "unpkg" not in html
        assert "htmx" not in html.lower()
        assert review.po_number in html
        assert "Testata estratta" in html
        assert "Righe estratte" in html
        assert "SKU" in html
        assert "Regole violate" in html
        assert "Approva" in html
        assert "Rifiuta" in html
        assert "non riconosciuto" in html
        assert "99%" not in html
        assert 'name="csrf_token"' in html
        assert review.result.issues
        assert review.result.issues[0].rule_id in html
        assert "CUS-01" in html or "ITM-01" in html
        assert "Motivo" in html
        conf_cells = re.findall(
            r"<td class=\"num\">(n/d|\d+%)</td>\s*</tr>",
            html,
        )
        assert conf_cells
        assert "99%" not in conf_cells

    def test_detail_shows_fuzzy_candidates(self) -> None:
        client, inbox = _client()
        target = next(
            item
            for item in inbox.list_orders()
            if any(
                (line.get("resolution") or {}).get("candidates")
                for line in (item.vof.get("lines") or [])
            )
        )
        response = client.get(f"/orders/{target.id}")
        assert response.status_code == 200
        html = response.text
        assert "candidati:" in html
        line = next(
            row
            for row in (target.vof.get("lines") or [])
            if (row.get("resolution") or {}).get("candidates")
        )
        sku = ((line.get("resolution") or {}).get("candidates") or [{}])[0].get("sku")
        assert sku
        assert sku in html

    def test_detail_shows_review_reason_without_violations(self) -> None:
        client, inbox = _client()
        gated = next(item for item in inbox.list_orders() if item.review_gate_reason)
        response = client.get(f"/orders/{gated.id}")
        assert response.status_code == 200
        html = response.text
        assert gated.review_gate_reason in html
        assert "cliente non in allowlist" in html or "storico insufficiente" in html
        assert "Motivo" in html
        assert "Nessuna regola violata." in html

    def test_docs_and_openapi_are_disabled(self) -> None:
        client, _inbox = _client()
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


class TestApproveReject:
    def test_approve_without_csrf_is_forbidden(self) -> None:
        client, inbox = _client()
        target = next(item for item in inbox.list_orders() if item.ui_status == "REVIEW")
        response = client.post(f"/orders/{target.id}/approve", follow_redirects=False)
        assert response.status_code == 403
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status == "REVIEW"
        assert updated.draft_name is None

    def test_approve_resolved_creates_a_draft(self) -> None:
        client, inbox = _client()
        before = len(inbox.odoo.created_orders())
        target = next(
            item
            for item in inbox.list_orders()
            if item.customer_resolved
            and not item.is_duplicate
            and item.ui_status == "REVIEW"
            and all(
                (line.get("resolution") or {}).get("sku")
                or (line.get("resolution") or {}).get("erp_product_id")
                or line.get("seller_item_code")
                for line in (item.vof.get("lines") or [])
            )
        )
        token = _csrf(client)
        response = client.post(
            f"/orders/{target.id}/approve",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert response.status_code == 200
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status == STATUS_APPROVED
        assert updated.draft_name
        assert updated.error is None
        assert len(inbox.odoo.created_orders()) == before + 1
        assert "Bozza Odoo creata" in response.text

    def test_approve_unresolved_does_not_invent_a_draft(self) -> None:
        client, inbox = _client()
        before = len(inbox.odoo.created_orders())
        target = next(
            item
            for item in inbox.list_orders()
            if item.ui_status == "REVIEW"
            and not item.is_duplicate
            and not item.customer_resolved
        )
        token = _csrf(client)
        response = client.post(
            f"/orders/{target.id}/approve",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert response.status_code == 200
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status != STATUS_APPROVED
        assert updated.draft_name is None
        assert updated.error
        assert "Cliente non risolto" in updated.error
        assert "S000" not in (updated.draft_name or "")
        assert len(inbox.odoo.created_orders()) == before
        assert "Bozza Odoo creata" not in response.text

    def test_reject_marks_rejected(self) -> None:
        client, inbox = _client()
        before = len(inbox.odoo.created_orders())
        target = next(item for item in inbox.list_orders() if item.ui_status == "REVIEW")
        token = _csrf(client)
        response = client.post(
            f"/orders/{target.id}/reject",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert response.status_code == 200
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status == STATUS_REJECTED
        assert "RIFIUTATO" in response.text
        assert BANNER in response.text
        assert len(inbox.odoo.created_orders()) == before

    def test_duplicate_does_not_create_draft(self) -> None:
        client, inbox = _client()
        duplicate = next(item for item in inbox.list_orders() if item.is_duplicate)
        assert duplicate.result.decision == DecisionRoute.REJECT
        before = len(inbox.odoo.created_orders())
        token = _csrf(client)
        response = client.post(
            f"/orders/{duplicate.id}/approve",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert response.status_code == 200
        updated = inbox.get(duplicate.id)
        assert updated is not None
        assert updated.ui_status == "REJECT"
        assert updated.draft_name is None
        assert "non viene creata" in (updated.error or "")
        assert len(inbox.odoo.created_orders()) == before
        assert "S000" not in response.text or updated.draft_name is None
