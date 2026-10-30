"""App FastAPI: lista ordini, dettaglio, approva e rifiuta."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ventureorder.web.inbox import STATUS_APPROVED, STATUS_REJECTED, InboxOrder, OrderInbox

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

BADGE_CLASS = {
    "AUTO_POST": "badge-auto",
    "REVIEW": "badge-review",
    "REJECT": "badge-reject",
    STATUS_APPROVED: "badge-approved",
    STATUS_REJECTED: "badge-rejected",
}


def _badge_class(status: str) -> str:
    return BADGE_CLASS.get(status, "badge-review")


def _line_confidence(order: InboxOrder, index: int, line: dict[str, Any]) -> float | None:
    evidence = order.vof.get("evidence") or {}
    for pointer in (
        f"/lines/{index}",
        f"/lines/{index}/quantity",
        f"/lines/{index}/unit_price",
    ):
        payload = evidence.get(pointer)
        if isinstance(payload, dict) and payload.get("confidence") is not None:
            return float(payload["confidence"])
    resolution = line.get("resolution") or {}
    score = resolution.get("score")
    if score is not None:
        return float(score)
    return None


def _detail_context(order: InboxOrder, *, message: str | None = None) -> dict[str, Any]:
    header = order.vof.get("header") or {}
    buyer = order.vof.get("buyer") or {}
    lines = []
    for index, line in enumerate(order.vof.get("lines") or []):
        sku = (line.get("resolution") or {}).get("sku") or line.get("seller_item_code")
        lines.append(
            {
                "line_no": line.get("line_no") or index + 1,
                "sku": sku or "—",
                "description": line.get("description") or "—",
                "quantity": line.get("quantity"),
                "uom": line.get("uom") or line.get("uom_raw") or "—",
                "unit_price": line.get("unit_price"),
                "line_amount": line.get("line_amount"),
                "confidence": _line_confidence(order, index, line),
            }
        )
    issues = [
        {
            "code": issue.rule_id,
            "severity": issue.severity.value,
            "message": issue.message,
        }
        for issue in order.result.issues
    ]
    can_act = order.ui_status not in {STATUS_APPROVED, STATUS_REJECTED}
    return {
        "order": order,
        "header": header,
        "buyer": buyer,
        "lines": lines,
        "issues": issues,
        "badge_class": _badge_class(order.ui_status),
        "can_act": can_act,
        "message": message or order.error,
        "flash_ok": order.ui_status == STATUS_APPROVED and order.draft_name,
    }


def create_app(inbox: OrderInbox | None = None) -> FastAPI:
    """Factory ASGI. ``inbox`` è iniettabile nei test."""
    app = FastAPI(title="VentureOrder", version="0.1.0-dev")
    app.state.inbox = inbox if inbox is not None else OrderInbox.for_demo()
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def _inbox() -> OrderInbox:
        store: OrderInbox = app.state.inbox
        return store

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/orders", status_code=302)

    @app.get("/orders", response_class=HTMLResponse)
    def list_orders(request: Request) -> HTMLResponse:
        rows = []
        for item in _inbox().list_orders():
            rows.append(
                {
                    "id": item.id,
                    "customer": item.customer_name,
                    "po_number": item.po_number,
                    "po_date": item.po_date,
                    "total": item.total,
                    "line_count": item.line_count,
                    "status": item.ui_status,
                    "badge_class": _badge_class(item.ui_status),
                    "is_duplicate": item.is_duplicate,
                    "draft_name": item.draft_name,
                }
            )
        return TEMPLATES.TemplateResponse(
            request,
            "orders.html",
            {"rows": rows, "count": len(rows)},
        )

    @app.get("/orders/{order_id}", response_class=HTMLResponse)
    def order_detail(request: Request, order_id: str) -> HTMLResponse:
        order = _inbox().get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        return TEMPLATES.TemplateResponse(request, "order_detail.html", _detail_context(order))

    @app.post("/orders/{order_id}/approve")
    def approve_order(order_id: str) -> RedirectResponse:
        store = _inbox()
        if store.get(order_id) is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        store.approve(order_id)
        return RedirectResponse(f"/orders/{order_id}", status_code=303)

    @app.post("/orders/{order_id}/reject")
    def reject_order(order_id: str) -> RedirectResponse:
        store = _inbox()
        if store.get(order_id) is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        store.reject(order_id)
        return RedirectResponse(f"/orders/{order_id}", status_code=303)

    return app


app = create_app
