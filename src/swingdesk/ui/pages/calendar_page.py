"""Page: Calendar & Macro — local Forex Factory JSON cache + dual clocks."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.timeutil import zone
from ...core import demo_data
from ..theme import mono
from ..widgets import Badge, Card, EmptyState, heading, page_wrapper, clear_layout

CLOCK_ZONES = (("New York", "America/New_York"), ("London", "Europe/London"),
               ("Johannesburg", "Africa/Johannesburg"), ("Frankfurt", "Europe/Berlin"))


class CalendarPage(QWidget):
    KEY = "calendar"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx
        self._calendar_digest = ""

        self.root.addWidget(heading(
            "Calendar & Macro",
            "Forex Factory is downloaded into a local weekly JSON cache. The UI reads only "
            "that local file; online checks update it only after valid content changes.",
            "Local-first economic calendar"))

        cache_row = QHBoxLayout()
        self.cache_status = QLabel("")
        self.cache_status.setObjectName("Tiny")
        self.cache_status.setWordWrap(True)
        self.btn_cache_refresh = QPushButton("Refresh Forex Factory cache")
        self.btn_cache_refresh.clicked.connect(self.force_calendar_refresh)
        cache_row.addWidget(self.cache_status, 1)
        cache_row.addWidget(self.btn_cache_refresh)
        self.root.addLayout(cache_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["UTC", "Event", "Impact", "Source", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.root.addWidget(self.table)

        clocks = QHBoxLayout()
        self.clock_labels: dict[str, QLabel] = {}
        for name, zone_name in CLOCK_ZONES:
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(12, 10, 12, 10)
            v.setSpacing(2)
            box.setStyleSheet(f"QWidget {{ background:{active_theme().input};"
                              f" border:1px solid {active_theme().border}; border-radius:10px; }}")
            small = QLabel(name)
            small.setObjectName("Tiny")
            time = QLabel("—")
            time.setStyleSheet(f"font-family:'{mono()}'; font-size:19px; font-weight:600;")
            z = QLabel(zone_name)
            z.setObjectName("Tiny")
            v.addWidget(small); v.addWidget(time); v.addWidget(z)
            self.clock_labels[zone_name] = time
            clocks.addWidget(box)
        self.root.addLayout(clocks)

        self.macro_card = Card("Macro panel")
        self.root.addWidget(self.macro_card)
        self._render_macro()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_clocks)
        self._timer.start(1000)
        self._tick_clocks()

        # Network refresh lives in the data/cache layer. This timer only notices
        # a changed local file digest and repaints the table.
        self._cache_timer = QTimer(self)
        self._cache_timer.timeout.connect(self._refresh_if_cache_changed)
        self._cache_timer.start(60_000)
        self.render_events()

    def _render_macro(self) -> None:
        lay = self.macro_card.layout()
        clear_layout(lay)
        lay.addWidget(EmptyState(
            "Macro policy provider not connected",
            "The Forex Factory event calendar is active. Central-bank stance and rate "
            "differentials remain unknown until a separate policy provider is connected.",
            "Open settings", lambda: self.ctx.navigate("settings")))

    def _render_cache_status(self) -> None:
        status = demo_data.calendar_cache_status()
        self._calendar_digest = status.content_sha256
        downloaded = status.last_download or "never"
        err = f" · last error: {status.last_error}" if status.last_error else ""
        self.cache_status.setText(
            f"Local JSON: {status.path} · {status.event_count} events · "
            f"last download: {downloaded} · online checks no more than hourly · "
            f"forced weekly refresh after Monday 00:00 SAST{err}")

    def render_events(self) -> None:
        events = demo_data.calendar_events()
        self.table.setRowCount(len(events))
        for i, e in enumerate(events):
            self.table.setItem(i, 0, QTableWidgetItem(f"{e.time_utc:%a %d %b %H:%M}"))
            affects = ", ".join(e.affects) if e.affects else e.currency
            self.table.setItem(i, 1, QTableWidgetItem(
                f"{e.currency} · {e.title}  ·  affects {affects}"))
            impact_kind = "bear" if e.impact == "HIGH" else "gold" if e.impact == "MEDIUM" else "muted"
            self.table.setCellWidget(i, 2, Badge(e.impact, impact_kind))
            self.table.setItem(i, 3, QTableWidgetItem(e.zone))
            btn = QPushButton("Alert me")
            btn.setStyleSheet("padding:4px 10px;")
            btn.clicked.connect(lambda _=False, ev=e: self.create_event_alert(ev))
            self.table.setCellWidget(i, 4, btn)
        self._render_cache_status()

    def create_event_alert(self, event) -> None:
        from ..pages.alerts import time_alert_rule
        rec = next((r for r in demo_data.universe()
                    if r.canonical_name in event.affects), None)
        if rec is None:
            self.ctx.toast("No matching discovered instrument")
            return
        rule = time_alert_rule(rec.broker_symbol, event.time_utc,
                               f"Event: {event.title}")
        self.ctx.store.save_alert(rule)
        self.ctx.events.alerts_changed.emit()
        self.ctx.toast(f"Alert armed for {event.title} at {event.time_utc:%H:%M UTC}")

    def force_calendar_refresh(self) -> None:
        _changed, message = demo_data.refresh_calendar(force=True)
        self.render_events()
        self.ctx.toast(message)

    def _refresh_if_cache_changed(self) -> None:
        status = demo_data.calendar_cache_status()
        if status.content_sha256 and status.content_sha256 != self._calendar_digest:
            self.render_events()
        else:
            self._render_cache_status()

    def _tick_clocks(self) -> None:
        now = datetime.now(timezone.utc)
        for zone_name, lab in self.clock_labels.items():
            local = now.astimezone(zone(zone_name))
            lab.setText(f"{local:%H:%M:%S}")

    def refresh(self) -> None:
        self.render_events()
        self._render_macro()
