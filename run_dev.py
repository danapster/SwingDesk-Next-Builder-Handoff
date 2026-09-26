#!/usr/bin/env python3
"""Swing Desk — cross-platform dev launcher.

Usage:
    python run_dev.py              normal GUI
    python run_dev.py --self-test  headless smoke test
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from swingdesk.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
