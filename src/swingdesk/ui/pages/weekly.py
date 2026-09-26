"""Page: Weekly Board — the Sunday/Monday planning ritual (§15.5-10)."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ...app_globals import active_theme
from ...core import demo_data
from ...core.models import LifecycleState
from ..widgets import Card, heading, page_wrapper, primary, clear_layout


class WeeklyPage(QWidget):
    KEY = "weekly"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = __import__("PySide6.QtWidgets", fromlist=["QVBoxLayout"]).QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Weekly Swing Board",
            "Your Sunday / Monday planning ritual in one compact view.",
            "Week ahead"))

        self.events_card = Card("High-impact events this window")
        self.root.addWidget(self.events_card)
        self.markets_card = Card("Markets to watch — from computed engine verdicts")
        self.root.addWidget(self.markets_card)
        self.counts_card = Card("Plan counts (from your local database)")
        self.root.addWidget(self.counts_card)

        btn = primary("Export board (Markdown)")
        btn.clicked.connect(self.export_board)
        self.root.addWidget(btn)
        ctx.events.plans_changed.connect(self.render)
        self.render()

    def render(self) -> None:
        self._fill(self.events_card, [(f"{e.time_utc:%a %H:%M} UTC", f"{e.title} ({e.impact})")
                                      for e in demo_data.calendar_events()[:5]])
        rows = demo_data.opportunity_rows()[:5]
        self._fill(self.markets_card, [
            (r["record"].canonical_name,
             f"{r['direction']} · {r['why'][:60]}") for r in rows])
        plans = self.ctx.store.plans()
        self._fill(self.counts_card, [
            (state.value, str(sum(1 for p in plans if p.state == state)))
            for state in (LifecycleState.WATCHING, LifecycleState.THESIS,
                          LifecycleState.WAITING, LifecycleState.OPEN,
                          LifecycleState.CLOSED, LifecycleState.REVIEW)])

    @staticmethod
    def _fill(card, pairs) -> None:
        lay = card.layout()
        clear_layout(lay)
        if not pairs:
            lay.addWidget(QLabel("—"))
        for left, right in pairs:
            l = QLabel(f"<span style='color:{active_theme().muted}'>{left}</span>"
                       f"&nbsp;&nbsp;<b>{right}</b>")
            l.setWordWrap(True)
            lay.addWidget(l)

    def export_board(self) -> None:
        lines = ["# Weekly Swing Board", "", "## Events"]
        for e in demo_data.calendar_events()[:5]:
            lines.append(f"- {e.time_utc:%a %H:%M} UTC — {e.title} ({e.impact})")
        lines += ["", "## Markets to watch"]
        for r in demo_data.opportunity_rows()[:5]:
            lines.append(f"- {r['record'].canonical_name} — {r['direction']} · {r['why'][:70]}")
        lines += ["", "## Plan counts"]
        plans = self.ctx.store.plans()
        for state in (LifecycleState.WATCHING, LifecycleState.THESIS, LifecycleState.WAITING,
                      LifecycleState.OPEN, LifecycleState.CLOSED, LifecycleState.REVIEW):
            n = sum(1 for p in plans if p.state == state)
            if n:
                lines.append(f"- {state.value}: {n}")
        path = self.ctx.exports_dir() / "weekly-board.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        self.ctx.toast(f"Weekly board exported → {path}")

    def refresh(self) -> None:
        self.render()
