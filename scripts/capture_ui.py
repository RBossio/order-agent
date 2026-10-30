"""Cattura screenshot Playwright della console (/orders e un dettaglio REVIEW)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ARTIFACT_DIR = Path("/opt/cursor/artifacts")
ORDERS_PNG = ARTIFACT_DIR / "ui-orders.png"
DETAIL_PNG = ARTIFACT_DIR / "ui-order-detail.png"


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(f"{url}/orders", wait_until="networkidle")
        page.wait_for_selector("table.orders")
        time.sleep(0.4)
        page.screenshot(path=str(ORDERS_PNG), full_page=True)
        review = page.locator('tr[data-status="REVIEW"] a').first
        review.click()
        page.wait_for_selector("table.orders")
        page.wait_for_selector("text=Regole violate")
        time.sleep(0.4)
        page.screenshot(path=str(DETAIL_PNG), full_page=True)
        browser.close()
    print(f"salvati {ORDERS_PNG} e {DETAIL_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
