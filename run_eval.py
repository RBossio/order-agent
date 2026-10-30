#!/usr/bin/env python3
"""Wrapper: valutazione riproducibile. Preferire ``make eval``."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract.eval_run import main

if __name__ == "__main__":
    sys.exit(main())
