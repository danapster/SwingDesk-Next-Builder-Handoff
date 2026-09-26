"""Page: Calendar & Macro — timezone-aware events, dual clocks (§15.5-8)."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.timeutil import zone
from ...core import demo_data
from ...core.store import new_id, now_iso
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

        self.root.addWidget(heading(
            "Calendar & Macro",
            "Events mapped to instruments discovered at your broker. Cached, timezone-aware, "
            "never blocking analysis.",
            "Timezone-aware context"))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["UTC", "Event", "Impact", "Zone", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.root.addWidget(self.table)

        clocks = QHBoxLayout()
        self.clock_labels: dict[str, QLabel] = {}
        for name, zone in CLOCK_ZONES:
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
            z = QLabel(zone)
            z.setObjectName("Tiny")
            v.addWidget(small); v.addWidget(time); v.addWidget(z)
            self.clock_labels[zone] = time
            clocks.addWidget(box)
        self.root.addLayout(clocks)

        self.macro_card = Card("Macro panel")
        self.root.addWidget(self.macro_card)
        self._render_macro()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_clocks)
        self._timer.start(1000)
        self._tick_clocks()
        self.render_events()

    def _render_macro(self) -> None:
        lay = self.macro_card.layout()
        clear_layout(lay)
        lay.addWidget(EmptyState(
            "Macro provider not connected",
            "Central-bank stance and rate differentials appear here after you connect a "
            "user-supplied provider. Unknown is shown as unknown — never invented.",
            "Open settings", lambda: self.ctx.navigate("settings")))

    def render_events(self) -> None:
        events = demo_data.calendar_events()
        now = datetime.now(timezone.utc)
        self.table.setRowCount(len(events))
        for i, e in enumerate(events):
            self.table.setItem(i, 0, QTableWidgetItem(f"{e.time_utc:%a %d %b %H:%M}"))
            self.table.setItem(i, 1, QTableWidgetItem(
                f"{e.title}  ·  affects {', '.join(e.affects)}"))
            impact = Badge(e.impact, "bear" if e.impact == "HIGH" else "gold")
            self.table.setCellWidget(i, 2, impact)
            self.table.setItem(i, 3, QTableWidgetItem(e.zone))
            btn = QPushButton("Alert me")
            btn.setStyleSheet("padding:4px 10px;")
            btn.clicked.connect(lambda _=False, ev=e: self.create_event_alert(ev))
            self.table.setCellWidget(i, 4, btn)

    def create_event_alert(self, event) -> None:
        from ..pages.alerts import time_alert_rule
        # Persist the actual event timestamp, not an unrelated synthetic price
        # threshold.  The main timer fires this rule when UTC reaches the event.
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

    def _tick_clocks(self) -> None:
        now = datetime.now(timezone.utc)
        for zone_name, lab in self.clock_labels.items():
            local = now.astimezone(zone(zone_name))
            lab.setText(f"{local:%H:%M:%S}")

    def refresh(self) -> None:
        self.render_events()
        self._render_macro()
