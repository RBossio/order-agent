"""Avvio locale: ``python -m ventureorder.web``."""

from __future__ import annotations

import uvicorn

from ventureorder.web.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app, factory=True, host="0.0.0.0", port=8000)
