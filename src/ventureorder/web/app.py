"""App FastAPI: lista ordini, dettaglio, approva e rifiuta."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ventureorder.web.inbox import STATUS_APPROVED, STATUS_REJECTED, InboxOrder, OrderInbox

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))
CSRF_COOKIE = "vo_csrf"
DEMO_BANNER = "DEMO: dati sintetici, Odoo simulato"

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
    """Confidenza d'estrazione da evidence; nessuna invenzione se manca."""
    evidence = order.vof.get("evidence") or {}
    for pointer in (
        f"/lines/{index}",
        f"/lines/{index}/quantity",
        f"/lines/{index}/unit_price",
    ):
        payload = evidence.get(pointer)
        if isinstance(payload, dict) and payload.get("confidence") is not None:
            return float(payload["confidence"])
    return None


def _csrf_token(request: Request) -> str:
    existing = request.cookies.get(CSRF_COOKIE)
    if existing:
        return existing
    return secrets.token_urlsafe(32)


def _require_csrf(request: Request, token: str) -> None:
    expected = request.cookies.get(CSRF_COOKIE, "")
    if not expected or not token or len(expected) != len(token):
        raise HTTPException(status_code=403, detail="CSRF token non valido")
    if not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="CSRF token non valido")


def _render(request: Request, name: str, context: dict[str, Any]) -> HTMLResponse:
    token = _csrf_token(request)
    payload = {"demo_banner": DEMO_BANNER, "csrf_token": token, **context}
    response = TEMPLATES.TemplateResponse(request, name, payload)
    if CSRF_COOKIE not in request.cookies:
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response


def _detail_context(order: InboxOrder, *, message: str | None = None) -> dict[str, Any]:
    header = order.vof.get("header") or {}
    buyer = order.vof.get("buyer") or {}
    lines = []
    for index, line in enumerate(order.vof.get("lines") or []):
        resolution = line.get("resolution") or {}
        sku = resolution.get("sku") or line.get("seller_item_code") or line.get("buyer_item_code")
        lines.append(
            {
                "line_no": line.get("line_no") or index + 1,
                "sku": sku or "n/d",
                "recognized": bool(resolution.get("sku") or resolution.get("erp_product_id")),
                "description": line.get("description") or "n/d",
                "quantity": line.get("quantity"),
                "uom": line.get("uom") or line.get("uom_raw") or "n/d",
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
    app = FastAPI(
        title="VentureOrder",
        version="0.1.0-dev",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
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
                    "customer_resolved": item.customer_resolved,
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
        return _render(request, "orders.html", {"rows": rows, "count": len(rows)})

    @app.get("/orders/{order_id}", response_class=HTMLResponse)
    def order_detail(request: Request, order_id: str) -> HTMLResponse:
        order = _inbox().get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        return _render(request, "order_detail.html", _detail_context(order))

    @app.post("/orders/{order_id}/approve")
    def approve_order(
        request: Request,
        order_id: str,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        _require_csrf(request, csrf_token)
        store = _inbox()
        if store.get(order_id) is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        store.approve(order_id)
        return RedirectResponse(f"/orders/{order_id}", status_code=303)

    @app.post("/orders/{order_id}/reject")
    def reject_order(
        request: Request,
        order_id: str,
        csrf_token: str = Form(""),
    ) -> RedirectResponse:
        _require_csrf(request, csrf_token)
        store = _inbox()
        if store.get(order_id) is None:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        store.reject(order_id)
        return RedirectResponse(f"/orders/{order_id}", status_code=303)

    return app


app = create_app
