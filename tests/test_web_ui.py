"""Test della console FastAPI (TestClient, FakeOdooClient, dati sintetici)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ventureorder.rules import DecisionRoute
from ventureorder.web.app import create_app
from ventureorder.web.inbox import STATUS_APPROVED, STATUS_REJECTED, OrderInbox


def _client(inbox: OrderInbox | None = None) -> tuple[TestClient, OrderInbox]:
    store = inbox if inbox is not None else OrderInbox.for_demo()
    client = TestClient(create_app(store))
    return client, store


class TestOrdersPages:
    def test_list_shows_synthetic_orders_and_badges(self) -> None:
        client, inbox = _client()
        orders = inbox.list_orders()
        assert len(orders) == 10
        statuses = {item.ui_status for item in orders}
        assert "AUTO_POST" in statuses
        assert "REVIEW" in statuses
        assert "REJECT" in statuses
        assert any(item.is_duplicate for item in orders)

        response = client.get("/orders")
        assert response.status_code == 200
        html = response.text
        assert "Ordini in arrivo" in html
        assert "Cliente" in html
        assert "N. PO" in html
        first = orders[0]
        assert first.customer_name in html
        assert first.po_number in html
        assert "AUTO_POST" in html
        assert "REVIEW" in html
        assert "REJECT" in html
        assert "duplicato" in html
        assert 'class="badge badge-auto"' in html
        assert 'class="badge badge-review"' in html
        assert 'class="badge badge-reject"' in html

    def test_home_redirects_to_orders(self) -> None:
        client, _inbox = _client()
        response = client.get("/", follow_redirects=False)
        assert response.status_code in {302, 307}
        assert response.headers["location"].endswith("/orders")

    def test_detail_shows_header_lines_and_issues(self) -> None:
        client, inbox = _client()
        review = next(item for item in inbox.list_orders() if item.ui_status == "REVIEW")
        response = client.get(f"/orders/{review.id}")
        assert response.status_code == 200
        html = response.text
        assert review.po_number in html
        assert "Testata estratta" in html
        assert "Righe estratte" in html
        assert "SKU" in html
        assert "Regole violate" in html
        assert "Approva" in html
        assert "Rifiuta" in html
        assert review.result.issues
        assert review.result.issues[0].rule_id in html


class TestApproveReject:
    def test_approve_creates_draft(self) -> None:
        client, inbox = _client()
        before = len(inbox.odoo.created_orders())
        target = next(
            item
            for item in inbox.list_orders()
            if item.ui_status == "AUTO_POST" and not item.is_duplicate
        )
        response = client.post(f"/orders/{target.id}/approve", follow_redirects=True)
        assert response.status_code == 200
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status == STATUS_APPROVED
        assert updated.draft_name
        assert "S" in updated.draft_name
        assert updated.draft_name in response.text
        assert "Bozza Odoo creata" in response.text
        assert 'class="badge badge-approved"' in response.text
        assert len(inbox.odoo.created_orders()) == before + 1

    def test_reject_marks_rejected(self) -> None:
        client, inbox = _client()
        before = len(inbox.odoo.created_orders())
        target = next(item for item in inbox.list_orders() if item.ui_status == "REVIEW")
        response = client.post(f"/orders/{target.id}/reject", follow_redirects=True)
        assert response.status_code == 200
        updated = inbox.get(target.id)
        assert updated is not None
        assert updated.ui_status == STATUS_REJECTED
        assert "RIFIUTATO" in response.text
        assert len(inbox.odoo.created_orders()) == before

    def test_duplicate_does_not_create_draft(self) -> None:
        client, inbox = _client()
        duplicate = next(item for item in inbox.list_orders() if item.is_duplicate)
        assert duplicate.result.decision == DecisionRoute.REJECT
        before = len(inbox.odoo.created_orders())
        response = client.post(f"/orders/{duplicate.id}/approve", follow_redirects=True)
        assert response.status_code == 200
        updated = inbox.get(duplicate.id)
        assert updated is not None
        assert updated.ui_status == "REJECT"
        assert updated.draft_name is None
        assert "non viene creata" in (updated.error or "")
        assert len(inbox.odoo.created_orders()) == before
        assert "S000" not in response.text or updated.draft_name is None
