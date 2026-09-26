"""Swing Desk — application context and event hub.

Every page receives an AppContext. Pages never reach into the main window
directly; they navigate, toast and confirm through this object, which keeps
them testable with pytest-qt (the context can be driven headlessly).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .core import demo_data
from .core.models import Position, SymbolRecord
from .core.store import Store


class EventHub(QObject):
    symbol_changed = Signal(object)      # SymbolRecord
    plans_changed = Signal()
    alerts_changed = Signal()
    positions_changed = Signal()
    data_ticked = Signal()
    theme_changed = Signal(str)


DEFAULTS = {
    "theme": "obsidian",
    "density": "compact",
    "default_risk": "1.0",
    "start_page": "radar",
    "orbit_animation": "1",
    "terminal_path": "",
}


class AppContext:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.events = EventHub()
        self.window = None            # set by MainWindow
        self.active_symbol: SymbolRecord | None = None
        self.positions: list[Position] = demo_data.positions()
        self.terminal_path: str = store.get_setting("terminal_path", "")
        self.last_scan_iso: str = ""

    # ---------------------------------------------------------- navigation
    def navigate(self, page_key: str, **kwargs) -> None:
        if self.window is not None:
            self.window.navigate(page_key, **kwargs)

    def toast(self, message: str) -> None:
        if self.window is not None:
            self.window.toast(message)

    # --------------------------------------------------------- interactions
    def confirm(self, title: str, text: str) -> bool:
        """Confirmation gate. Overridable for tests."""
        if self.window is not None and hasattr(self.window, "run_confirm"):
            return self.window.run_confirm(title, text)
        return False

    def confirm_typed(self, title: str, text: str, expected: str) -> bool:
        if self.window is not None and hasattr(self.window, "run_confirm_typed"):
            return self.window.run_confirm_typed(title, text, expected)
        return False

    def ask_open_file(self, caption: str, patterns: str) -> str:
        if self.window is not None and hasattr(self.window, "run_open_file"):
            return self.window.run_open_file(caption, patterns)
        return ""

    # ------------------------------------------------------------- settings
    def setting(self, key: str) -> str:
        return self.store.get_setting(key, DEFAULTS.get(key, ""))

    def set_setting(self, key: str, value: str) -> None:
        self.store.set_setting(key, value)

    def apply_theme(self, key: str) -> None:
        if self.window is not None:
            self.window.apply_theme(key)

    def apply_density(self, key: str) -> None:
        if self.window is not None:
            self.window.apply_density(key)

    # ------------------------------------------------------------- symbols
    def set_active_symbol(self, rec: SymbolRecord) -> None:
        self.active_symbol = rec
        self.events.symbol_changed.emit(rec)

    def current_price(self, broker_symbol: str) -> float:
        rec = demo_data.symbol(broker_symbol)
        return rec.bid if rec else 0.0

    # ------------------------------------------------------------ exports
    def exports_dir(self) -> Path:
        d = self.store.path.parent / "exports"
        d.mkdir(exist_ok=True)
        return d
