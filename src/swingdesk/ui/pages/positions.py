"""Page: Positions — broker mirror with confirmation-gated management (§15.5-5)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.models import LifecycleState
from ...core.store import now_iso
from ..theme import mono
from ..widgets import Badge, Card, heading, page_wrapper, clear_layout


class PositionsPage(QWidget):
    KEY = "positions"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Positions",
            "Positions mirrored with their original thesis attached. Demo adapter — "
            "clearly labelled, never presented as a live broker account.",
            "Execution & management"))

        top = QHBoxLayout()
        self.demo_badge = Badge("DEMO DATA", "gold")
        top.addWidget(QLabel("Source"))
        top.addWidget(self.demo_badge)
        top.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.render_positions)
        self.btn_close_all = QPushButton("Close all (typed confirm)")
        self.btn_close_all.setObjectName("Danger")
        self.btn_close_all.clicked.connect(self.close_all)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_close_all)
        self.root.addLayout(top)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Market", "Side", "Broker symbol", "Volume", "Entry", "Now", "P/L (demo)", ""])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.root.addWidget(self.table, 1)

        info = QHBoxLayout()
        self.risk_card = Card("Portfolio risk")
        self.thesis_card = Card("Thesis monitor")
        info.addWidget(self.risk_card)
        info.addWidget(self.thesis_card)
        self.root.addLayout(info)

        ctx.events.positions_changed.connect(self.render_positions)
        ctx.events.plans_changed.connect(self.render_theses)
        self.render_positions()

    # ---------------------------------------------------------------- render
    def render_positions(self) -> None:
        self.table.setRowCount(len(self.ctx.positions))
        for i, pos in enumerate(self.ctx.positions):
            self.table.setItem(i, 0, QTableWidgetItem(pos.canonical_name))
            side = QTableWidgetItem(pos.direction)
            side.setForeground(_qcolor(active_theme().bull if pos.direction == "LONG"
                                       else active_theme().bear))
            self.table.setItem(i, 1, side)
            self.table.setItem(i, 2, QTableWidgetItem(pos.broker_symbol))
            self.table.setItem(i, 3, QTableWidgetItem(f"{pos.volume:.2f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{pos.entry:.5g}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{pos.current_price:.5g}"))
            pl = QTableWidgetItem(f"{pos.profit:+,.2f}")
            pl.setForeground(_qcolor(active_theme().bull if pos.profit >= 0
                                     else active_theme().bear))
            self.table.setItem(i, 6, pl)
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("padding:4px 10px;")
            close_btn.clicked.connect(lambda _=False, ticket=pos.ticket: self.close_one(ticket))
            self.table.setCellWidget(i, 7, close_btn)
        self.render_risk()
        self.render_theses()

    def render_risk(self) -> None:
        lay = self.risk_card.layout()
        clear_layout(lay)
        open_pl = sum(p.profit for p in self.ctx.positions)
        open_risk = sum(0.5 for _ in self.ctx.positions)  # demo stand-in per position
        for label, value in (("Open positions", str(len(self.ctx.positions))),
                             ("Open P/L (demo)", f"{open_pl:+,.2f}"),
                             ("Equity", f"{10_000 + open_pl:,.2f}")):
            row = QLabel(f"<span style='color:{active_theme().muted}'>{label}</span>&nbsp;&nbsp;"
                         f"<b style='font-family:'{mono()}''>{value}</b>")
            lay.addWidget(row)

    def render_theses(self) -> None:
        lay = self.thesis_card.layout()
        clear_layout(lay)
        linked = 0
        for pos in self.ctx.positions:
            for plan in self.ctx.store.plans():
                if plan.broker_symbol == pos.broker_symbol and \
                   plan.state in (LifecycleState.OPEN, LifecycleState.MANAGING):
                    linked += 1
                    row = QLabel(f"<b>{plan.canonical_name}</b> — thesis {plan.state.value} · "
                                 f"target {plan.target:.5g}")
                    row.setWordWrap(True)
                    lay.addWidget(row)
        note = QLabel(f"{linked} of {len(self.ctx.positions)} positions have an attached thesis."
                      if self.ctx.positions else "No open positions.")
        note.setObjectName("Tiny")
        lay.addWidget(note)

    # --------------------------------------------------------------- actions
    def close_one(self, ticket: int) -> None:
        pos = next((p for p in self.ctx.positions if p.ticket == ticket), None)
        if pos is None:
            return
        if not self.ctx.confirm("Close position (paper)",
                                f"Close {pos.canonical_name} {pos.direction} "
                                f"{pos.volume:.2f} lots @ {pos.current_price:.5g}?"):
            return
        self._close([pos])

    def close_all(self) -> None:
        if not self.ctx.positions:
            self.ctx.toast("Nothing to close")
            return
        if not self.ctx.confirm_typed("Bulk close (paper)",
                                      "Type CLOSE ALL to close every demo position.",
                                      "CLOSE ALL"):
            return
        self._close(list(self.ctx.positions))

    def _close(self, positions) -> None:
        for pos in positions:
            self.ctx.positions = [p for p in self.ctx.positions if p.ticket != pos.ticket]
            for plan in self.ctx.store.plans():
                if plan.broker_symbol == pos.broker_symbol and \
                   plan.state in (LifecycleState.OPEN, LifecycleState.MANAGING):
                    plan.state = LifecycleState.CLOSED
                    plan.updated_at = now_iso()
                    plan.closed_at = now_iso()
                    plan.actual_fill = pos.current_price
                    risk_amt = demo_equity() * plan.risk_percent / 100
                    plan.realised_r = pos.profit / risk_amt if risk_amt else 0.0
                    self.ctx.store.save_plan(plan)
        self.ctx.events.positions_changed.emit()
        self.ctx.events.plans_changed.emit()
        self.ctx.toast(f"Closed {len(positions)} position(s) — linked plans moved to CLOSED")

    def refresh(self) -> None:
        self.render_positions()


def _qcolor(hexs: str):
    from PySide6.QtGui import QColor
    return QColor(hexs)


def demo_equity() -> float:
    from ...core import demo_data
    return demo_data.account_equity()
