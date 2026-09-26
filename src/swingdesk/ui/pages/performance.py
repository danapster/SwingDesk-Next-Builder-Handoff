"""Page: Performance Lab — analytics derived only from stored records (§15.5-7)."""
from __future__ import annotations

from statistics import mean

from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.models import LifecycleState
from ..widgets import Card, EmptyState, Stat, clear_layout, heading, page_wrapper


class PerformancePage(QWidget):
    KEY = "performance"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Performance Lab",
            "Feedback, not prediction. Metrics derive from stored, auditable records only.",
            "Review → better decisions"))

        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_export = QPushButton("Export report (Markdown)")
        self.btn_export.clicked.connect(self.export_report)
        top.addWidget(self.btn_export)
        self.root.addLayout(top)

        self.stats_row = QHBoxLayout()
        self.root.addLayout(self.stats_row)
        self.tables_row = QHBoxLayout()
        self.root.addLayout(self.tables_row, 1)
        ctx.events.plans_changed.connect(self.render)
        self.render()

    def closed_reviewed(self):
        return [p for p in self.ctx.store.plans()
                if p.state in (LifecycleState.CLOSED, LifecycleState.REVIEW)
                and p.realised_r is not None]

    # ---------------------------------------------------------------- render
    def render(self) -> None:
        self._clear(self.stats_row)
        self._clear(self.tables_row)
        plans = self.closed_reviewed()
        if not plans:
            self.stats_row.addWidget(EmptyState(
                "No closed trades to analyse",
                "Performance metrics appear here once plans close with a realised R. "
                "Nothing is fabricated in the meantime (§1.1).",
                "Go to positions", lambda: self.ctx.navigate("positions")))
            return
        wins = [p for p in plans if p.realised_r > 0]
        exp = mean(p.realised_r for p in plans)
        self._stat("Closed trades", str(len(plans)))
        self._stat("Win rate", f"{len(wins) / len(plans):.0%}")
        self._stat("Expectancy", f"{exp:+.2f}R")
        self._stat("Total R", f"{sum(p.realised_r for p in plans):+.2f}R")

        self.tables_row.addWidget(self._group_table("By market", self._by(plans, lambda p: p.canonical_name)))
        self.tables_row.addWidget(self._group_table("By direction", self._by(plans, lambda p: p.direction)))
        self.tables_row.addWidget(self._group_table("By behaviour", self._by(
            plans, lambda p: ", ".join(p.behaviour_flags) if p.behaviour_flags else "clean")))

    @staticmethod
    def _by(plans, key):
        groups: dict[str, list] = {}
        for p in plans:
            groups.setdefault(key(p), []).append(p)
        return groups

    def _stat(self, label, value):
        self.stats_row.addWidget(Stat(label, value))

    def _group_table(self, title, groups) -> QWidget:
        card = Card(title)
        t = QTableWidget(len(groups), 3)
        t.setHorizontalHeaderLabels(["Group", "n", "Avg R"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i, (k, ps) in enumerate(sorted(groups.items())):
            t.setItem(i, 0, QTableWidgetItem(k))
            t.setItem(i, 1, QTableWidgetItem(str(len(ps))))
            t.setItem(i, 2, QTableWidgetItem(f"{mean(p.realised_r for p in ps):+.2f}"))
        card.add(t)
        return card

    @staticmethod
    def _clear(lay):
        clear_layout(lay)

    # --------------------------------------------------------------- actions
    def export_report(self) -> None:
        plans = self.closed_reviewed()
        if not plans:
            self.ctx.toast("No closed trades to report yet")
            return
        wins = [p for p in plans if p.realised_r > 0]
        exp = mean(p.realised_r for p in plans)
        lines = ["# Swing Desk — Performance report",
                 "",
                 f"- Closed trades: {len(plans)}",
                 f"- Win rate: {len(wins) / len(plans):.0%}",
                 f"- Expectancy: {exp:+.2f}R",
                 f"- Total R: {sum(p.realised_r for p in plans):+.2f}R",
                 "",
                 "| Market | Direction | Entry | Realised R | Flags |",
                 "|---|---|---|---|---|"]
        for p in plans:
            lines.append(f"| {p.canonical_name} | {p.direction} | {p.entry:.5g} "
                         f"| {p.realised_r:+.2f}R | {'; '.join(p.behaviour_flags) or '—'} |")
        path = self.ctx.exports_dir() / "performance-report.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        self.ctx.toast(f"Report exported → {path}")

    def refresh(self) -> None:
        self.render()
