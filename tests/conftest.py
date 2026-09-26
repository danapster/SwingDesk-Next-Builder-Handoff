"""Shared fixtures: a real Qt app with an isolated temp database."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from swingdesk.app import MainWindow  # noqa: E402
from swingdesk.context import AppContext  # noqa: E402
from swingdesk.core.store import Store  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def make_app(qapp, tmp_path, monkeypatch):
    """Factory building a MainWindow with a fresh temp store (auto-confirm dialogs)."""
    created = []

    def _make(store: Store | None = None) -> MainWindow:
        store = store or Store(tmp_path / f"swingdesk-{len(created)}.db")
        ctx = AppContext(store)
        win = MainWindow(ctx)
        win.run_confirm = lambda title, text: True
        win.run_confirm_typed = lambda title, text, expected: True
        win.run_open_file = lambda caption, patterns: str(tmp_path / "terminal64.exe")
        created.append(win)
        return win

    yield _make
    for w in created:
        w.close()
        w.deleteLater()
    qapp.processEvents()
