"""Page: Alerts — deterministic rules, delivery, persistent log (§15.5-9)."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.store import now_iso
from ..widgets import Badge, Card, EmptyState, heading, page_wrapper, primary, clear_layout


def price_alert_rule(broker_symbol: str, kind: str, level: float, note: str = ""):
    from ...core.models import AlertRule
    from ...core.store import new_id
    return AlertRule(id=new_id("alert"), broker_symbol=broker_symbol, kind=kind,
                     level=level, note=note, enabled=True, created_at=now_iso())


def time_alert_rule(broker_symbol: str, when_utc: datetime, note: str = ""):
    """Create an event-time alert using the existing persisted numeric level.

    `level` stores a UTC epoch timestamp for kind=time_event, so this remains
    backward-compatible with the v1 SQLite schema.
    """
    from ...core.models import AlertRule
    from ...core.store import new_id
    when = when_utc.astimezone(timezone.utc)
    return AlertRule(id=new_id("alert"), broker_symbol=broker_symbol,
                     kind="time_event", level=when.timestamp(), note=note,
                     enabled=True, created_at=now_iso())


class AlertsPage(QWidget):
    KEY = "alerts"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Alerts",
            "Deterministic conditions with actual state values, desktop delivery, "
            "a persistent log.",
            "Price · zone · time · thesis"))

        form_card = Card("New price alert")
        row = QHBoxLayout()
        self.symbol_combo = QComboBox()
        from ...core import demo_data
        for r in demo_data.universe():
            self.symbol_combo.addItem(f"{r.canonical_name} ({r.broker_symbol})", r.broker_symbol)
        self.cond = QComboBox()
        self.cond.addItem("Crosses above", "price_touch_above")
        self.cond.addItem("Crosses below", "price_touch_below")
        self.level = QDoubleSpinBox()
        self.level.setDecimals(6)
        # QDoubleSpinBox defaults to a maximum of 99.99, which silently
        # corrupted alerts for gold, indices and crypto.
        self.level.setRange(0.0, 10_000_000.0)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Note (optional)")
        self.btn_use_current = QPushButton("Use current price")
        self.btn_use_current.clicked.connect(self.use_current_price)
        self.btn_create = primary("Create alert")
        self.btn_create.clicked.connect(self.create_alert)
        for lab, wid in (("Instrument", self.symbol_combo), ("Condition", self.cond),
                         ("Level", self.level)):
            row.addWidget(QLabel(lab)); row.addWidget(wid)
        row.addWidget(self.btn_use_current)
        row.addWidget(self.note, 1)
        row.addWidget(self.btn_create)
        form_card.layout().addLayout(row)
        self.root.addWidget(form_card)

        self.rules_card = Card("Active rules")
        self.root.addWidget(self.rules_card)
        self.log_card = Card("Alert log")
        self.root.addWidget(self.log_card)
        ctx.events.alerts_changed.connect(self.render)
        self.render()

    # ---------------------------------------------------------------- render
    def render(self) -> None:
        self.render_rules()
        self.render_log()

    def render_rules(self) -> None:
        lay = self.rules_card.layout()
        clear_layout(lay)
        rules = self.ctx.store.alerts()
        if not rules:
            lay.addWidget(EmptyState(
                "No alert rules yet",
                "Create one above, or arm an event-window alert from the Calendar page."))
            return
        for r in rules:
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 7, 10, 7)
            if r.kind == "time_event":
                when = datetime.fromtimestamp(r.level, tz=timezone.utc)
                title = QLabel(
                    f"<b>{r.broker_symbol}</b> at "
                    f"<span style='font-family:monospace'>{when:%Y-%m-%d %H:%M UTC}</span>"
                    + (f" — {r.note}" if r.note else ""))
            else:
                cond = "≥" if r.kind == "price_touch_above" else "≤"
                title = QLabel(f"<b>{r.broker_symbol}</b> {cond} <span style='font-family:monospace'>"
                               f"{r.level:.5g}</span>"
                               + (f" — {r.note}" if r.note else ""))
            status = Badge("FIRED" if r.fired_at else ("ON" if r.enabled else "PAUSED"),
                           "gold" if r.enabled and not r.fired_at else "muted")
            btn_toggle = QPushButton("Pause" if r.enabled else "Resume")
            btn_toggle.setStyleSheet("padding:4px 10px;")
            btn_toggle.clicked.connect(lambda _=False, rid=r.id: self.toggle_rule(rid))
            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet("padding:4px 10px;")
            btn_del.clicked.connect(lambda _=False, rid=r.id: self.delete_rule(rid))
            h.addWidget(title, 1); h.addWidget(status)
            h.addWidget(btn_toggle); h.addWidget(btn_del)
            row.setStyleSheet(f"QFrame {{ background:{active_theme().panel_alt};"
                              f" border:1px solid {active_theme().border}; border-radius:10px; }}")
            lay.addWidget(row)

    def render_log(self) -> None:
        lay = self.log_card.layout()
        clear_layout(lay)
        entries = self.ctx.store.alert_log(30)
        if not entries:
            lay.addWidget(QLabel("No alerts fired yet. The demo price feed runs while the app "
                                 "is open — armed alerts fire on an actual cross."))
            return
        for at, msg in entries:
            l = QLabel(f"<span style='font-family:monospace'>{at}</span> &nbsp; {msg}")
            l.setWordWrap(True)
            lay.addWidget(l)

    # --------------------------------------------------------------- actions
    def use_current_price(self) -> None:
        from ...core import demo_data
        rec = demo_data.symbol(self.symbol_combo.currentData())
        if rec:
            self.level.setValue(round(rec.bid, 6))
            self.ctx.toast(f"Level set to current demo bid {rec.bid:.5g}")

    def create_alert(self) -> None:
        symbol = self.symbol_combo.currentData()
        level = self.level.value()
        if not symbol or level == 0:
            self.ctx.toast("Pick an instrument and a level")
            return
        rule = price_alert_rule(symbol, self.cond.currentData(), level, self.note.text().strip())
        self.ctx.store.save_alert(rule)
        self.ctx.events.alerts_changed.emit()
        self.ctx.toast(f"Alert armed: {symbol} "
                       f"{'≥' if rule.kind == 'price_touch_above' else '≤'} {level:.5g}")

    def toggle_rule(self, rule_id: str) -> None:
        for r in self.ctx.store.alerts():
            if r.id == rule_id:
                r.enabled = not r.enabled
                if r.enabled:
                    r.fired_at = None
                self.ctx.store.save_alert(r)
                break
        self.ctx.events.alerts_changed.emit()

    def delete_rule(self, rule_id: str) -> None:
        self.ctx.store.delete_alert(rule_id)
        self.ctx.events.alerts_changed.emit()
        self.ctx.toast("Alert deleted")

    def refresh(self) -> None:
        self.render()
