"""Swing Desk — main window: sidebar router, header, toasts, timers.

Spec §15.4: a real QStackedWidget router. Each nav button has a connected
signal, switches to a constructed page, updates the active style and passes
pytest-qt click tests. No inert navigation controls.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from .context import AppContext
from .core import demo_data
from .core.timeutil import zone
from .core.models import Verdict
from .core.store import Store
from .ui.pages import ALL_PAGES
from .ui.theme import DENSITIES, THEMES, OrbitBrand, build_qss, mono, serif
from .ui.widgets import Toast
from . import app_globals


class SidebarButton(QPushButton):
    def __init__(self, key: str, label: str, badge: str = "") -> None:
        super().__init__(f"{label}   {badge}" if badge else label)
        self.setObjectName("NavLink")
        self.page_key = key
        self.setCheckable(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.setWindowTitle("Swing Desk — live MT5 decision workspace")
        self.resize(1440, 880)
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, SidebarButton] = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------------------------------------------------- sidebar
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(248)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(16, 18, 16, 16)
        sv.setSpacing(16)

        brand_inner = QWidget()
        bv = QHBoxLayout(brand_inner)
        bv.setContentsMargins(11, 11, 11, 11)
        bv.setSpacing(10)
        mark = QLabel("SD")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet("border:1px solid rgba(201,169,106,.45); border-radius:10px;"
                           "color:#E3C88D; font-weight:700; font-size:15px;")
        name = QLabel("Swing Desk")
        name.setStyleSheet(f"font-family:'{serif()}'; font-size:18px;")
        sub = QLabel("Market. Thesis. Plan. Review.")
        sub.setStyleSheet("font-size:10px; color:#8D9098;")
        nv = QVBoxLayout()
        nv.setSpacing(2)
        nv.addWidget(name)
        nv.addWidget(sub)
        bv.addWidget(mark)
        bv.addLayout(nv)
        self.brand = OrbitBrand(brand_inner)
        self.brand.setStyleSheet("background:transparent;")
        sv.addWidget(self.brand)

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QScrollArea.NoFrame)
        nav_holder = QWidget()
        nv2 = QVBoxLayout(nav_holder)
        nv2.setContentsMargins(0, 0, 0, 0)
        nv2.setSpacing(2)
        for key, (label, _cls) in ALL_PAGES.items():
            b = SidebarButton(key, label, self._nav_badge(key))
            b.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_buttons[key] = b
            nv2.addWidget(b)
        nv2.addStretch(1)
        nav_scroll.setWidget(nav_holder)
        sv.addWidget(nav_scroll, 1)

        # connection + clocks footer
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#C9A96A; font-size:12px;")
        self.status_text = QLabel(demo_data.source_label())
        self.status_text.setStyleSheet("font-size:11px; color:#8D9098;")
        srow = QHBoxLayout()
        srow.addWidget(self.status_dot)
        srow.addWidget(self.status_text)
        sv.addLayout(srow)
        self._sync_data_source_status()
        self.clock_label = QLabel("—")
        self.clock_label.setStyleSheet(f"font-family:'{mono()}'; font-size:11px; color:#8D9098;")
        self.clock_label.setWordWrap(True)
        sv.addWidget(self.clock_label)
        side.setStyleSheet(
            "QWidget#Sidebar { background:#0A0B0E; border-right:1px solid #292C33; }"
            "QScrollArea { background:transparent; }")
        root.addWidget(side)

        # ------------------------------------------------------------ pages
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        for key, (_label, cls) in ALL_PAGES.items():
            page = cls(ctx)
            self.pages[key] = page
            self.stack.addWidget(page)

        # ------------------------------------------------------------- toast
        self.toast_widget = Toast(self)

        # ------------------------------------------------------------ timers
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()

        self._data_timer = QTimer(self)
        self._data_timer.timeout.connect(self._tick_data)
        self._data_timer.start(3000)

        # ---------------------------------------------------------- shortcuts
        for i, key in enumerate(ALL_PAGES.keys(), start=1):
            if i <= 9:
                sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
                sc.activated.connect(lambda k=key: self.navigate(k))

        self.apply_theme(ctx.setting("theme") or "obsidian")
        self.apply_density(ctx.setting("density") or "compact")
        self.set_orbit_enabled(ctx.setting("orbit_animation") != "0")
        start = ctx.setting("start_page")
        self.navigate(start if start in ALL_PAGES else "radar")

    def _sync_data_source_status(self) -> None:
        if demo_data.is_live():
            info = demo_data.connection_status()
            server = info.get("server") or info.get("company") or "connected"
            self.status_dot.setStyleSheet("color:#6FCF97; font-size:12px;")
            self.status_text.setText(f"LIVE MT5 · {server}")
        else:
            self.status_dot.setStyleSheet("color:#C9A96A; font-size:12px;")
            self.status_text.setText("DEMO FALLBACK · MT5 offline")

    # ------------------------------------------------------------ navigation
    def _nav_badge(self, key: str) -> str:
        try:
            if key == "markets":
                return str(len(demo_data.universe()))
            if key == "alerts":
                return str(len(self.ctx.store.alerts()))
            if key == "plans":
                return str(len(self.ctx.store.plans()))
        except Exception:
            pass
        return ""

    def navigate(self, key: str, **_kwargs) -> None:
        if key not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[key])
        for k, b in self.nav_buttons.items():
            b.setProperty("active", k == key)
            b.style().unpolish(b)
            b.style().polish(b)
        if key == "alerts":
            b = self.nav_buttons["alerts"]
            b.setText("Alerts" + (f"   {len(self.ctx.store.alerts())}"
                                  if self.ctx.store.alerts() else ""))
        page = self.pages[key]
        if hasattr(page, "refresh"):
            page.refresh()

    # ------------------------------------------------------------- theming
    _applied_qss_key: tuple[str, str] | None = None  # class-level cache of last applied QSS

    def apply_theme(self, key: str) -> None:
        theme = THEMES.get(key, THEMES["obsidian"])
        density = self.ctx.setting("density") or "compact"
        app_globals.set_active_theme(key)
        self.ctx.set_setting("theme", key)
        # Idempotent: re-polishing the entire application for an identical
        # stylesheet is pure cost (and grows with live widgets).
        qss_key = (key, density)
        if MainWindow._applied_qss_key != qss_key:
            qss = build_qss(theme, density)
            # sidebar keeps near-black in every theme (Edge Ledger direction)
            qss += ("QWidget#Sidebar { background:#0A0B0E; border-right:1px solid #292C33; }"
                    "QScrollArea { background:transparent; }")
            QApplication.instance().setStyleSheet(qss)
            MainWindow._applied_qss_key = qss_key
        self.brand.theme_key = key
        self.brand.update()
        self.ctx.events.theme_changed.emit(key)

    def apply_density(self, key: str) -> None:
        density = key if key in DENSITIES else "compact"
        self.ctx.set_setting("density", density)
        self.apply_theme(self.ctx.setting("theme") or "obsidian")

    def set_orbit_enabled(self, on: bool) -> None:
        self.brand.start() if on else self.brand.stop()

    # ---------------------------------------------------------- interactions
    def toast(self, message: str) -> None:
        self.toast_widget.pop(message)

    def run_confirm(self, title: str, text: str) -> bool:
        ret = QMessageBox.question(self, title, text)
        return ret == QMessageBox.Yes

    def run_confirm_typed(self, title: str, text: str, expected: str) -> bool:
        dlg = QMessageBox(self)
        dlg.setWindowTitle(title)
        dlg.setText(text)
        edit = QLineEdit(dlg)
        edit.setPlaceholderText(f"Type {expected}")
        dlg.layout().addWidget(edit, 1, 1)
        dlg.addButton("Confirm", QMessageBox.YesRole)
        dlg.addButton("Cancel", QMessageBox.RejectRole)
        dlg.exec()
        return edit.text().strip().upper() == expected.upper()

    def run_open_file(self, caption: str, patterns: str) -> str:
        path, _ = QFileDialog.getOpenFileName(self, caption, "",
                                              f"{patterns};;All files (*)")
        return path

    # --------------------------------------------------------------- timers
    def _tick_clock(self) -> None:
        now = datetime.now(timezone.utc)
        def clk(z): return now.astimezone(zone(z)).strftime("%H:%M")
        self.clock_label.setText(
            f"NY {clk('America/New_York')}  ·  "
            f"LON {clk('Europe/London')}  ·  "
            f"SAST {clk('Africa/Johannesburg')}")

    def _tick_data(self) -> None:
        """Refresh the active data source and evaluate deterministic alerts."""
        demo_data.tick()
        self._sync_data_source_status()
        for rule in self.ctx.store.alerts():
            if not rule.enabled or rule.fired_at:
                continue
            now = datetime.now(timezone.utc)
            if rule.kind == "time_event":
                triggered = now.timestamp() >= rule.level
                price = None
            else:
                price = self.ctx.current_price(rule.broker_symbol)
                if price == 0:
                    continue
                triggered = ((rule.kind == "price_touch_above" and price >= rule.level) or
                             (rule.kind == "price_touch_below" and price <= rule.level))
            if triggered:
                rule.fired_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self.ctx.store.save_alert(rule)
                if rule.kind == "time_event":
                    msg = (f"{rule.broker_symbol} event time reached"
                           + (f" — {rule.note}" if rule.note else ""))
                else:
                    msg = (f"{rule.broker_symbol} "
                           f"{'crossed above' if rule.kind == 'price_touch_above' else 'crossed below'} "
                           f"{rule.level:.5g} (now {price:.5g})"
                           + (f" — {rule.note}" if rule.note else ""))
                self.ctx.store.log_alert(msg)
                self.toast(msg)
                self.ctx.events.alerts_changed.emit()
        self.ctx.events.data_ticked.emit()

    # ---------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802
        self._clock_timer.stop()
        self._data_timer.stop()
        self.brand.stop()
        demo_data.shutdown()
        super().closeEvent(event)


def create_app(store: Store | None = None) -> tuple[QApplication, MainWindow]:
    """Build the application. Separated from main() for pytest-qt."""
    app = QApplication.instance() or QApplication([])
    ctx = AppContext(store or Store())
    win = MainWindow(ctx)
    return app, win
