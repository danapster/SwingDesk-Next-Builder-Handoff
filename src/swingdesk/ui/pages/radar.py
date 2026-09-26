"""Page: Radar — ranked opportunities, active thesis, scorecard (§15.5-1)."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core import demo_data
from ...core.models import LifecycleState, Verdict
from ..theme import mono
from ..widgets import Badge, Card, EmptyState, Stat, heading, page_wrapper, primary, clear_layout


class RadarPage(QWidget):
    KEY = "radar"

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        w, lay = page_wrapper()
        self.setLayout(QVBoxLayout())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.inner = w
        scroll.setWidget(w)
        self.layout().addWidget(scroll)

        self.root = lay
        self.root.addWidget(heading("Swing Radar",
                                    "The clearest paths first. Every status is backed by visible evidence.",
                                    "Market → thesis → plan → review"))
        actions = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh scan")
        self.btn_refresh.clicked.connect(self.refresh_scan)
        self.btn_new_thesis = primary("New thesis")
        self.btn_new_thesis.clicked.connect(lambda: self.ctx.navigate("plans"))
        self.scan_label = QLabel("")
        self.scan_label.setObjectName("Tiny")
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_new_thesis)
        actions.addStretch(1)
        actions.addWidget(self.scan_label)
        self.root.addLayout(actions)

        self.opp_card = Card("Market opportunities")
        self.root.addWidget(self.opp_card)

        self.thesis_card = Card()
        self.root.addWidget(self.thesis_card)

        stats = QHBoxLayout()
        self.stat_scanned = Stat("Markets scanned", "—", "active data source")
        self.stat_thesis = Stat("Active theses", "—", "waiting, not forcing")
        self.stat_event = Stat("Next event", "—", "dual-clock calendar")
        self.stat_window = Stat("Session", "—", "live clock")
        for s in (self.stat_scanned, self.stat_thesis, self.stat_event, self.stat_window):
            stats.addWidget(s)
        self.root.addLayout(stats)

        self.score_card = Card("Swing scorecard — top opportunity")
        self.root.addWidget(self.score_card)
        self.checklist_card = Card("You are here")
        self.root.addWidget(self.checklist_card)
        self.root.addStretch(1)
        self.refresh()

    # ---------------------------------------------------------------- build
    def refresh(self) -> None:
        self.refresh_scan(silent=True)
        self._render_thesis()
        self._render_stats()

    def refresh_scan(self, silent: bool = False) -> None:
        self.ctx.last_scan_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._scan_count = getattr(self, "_scan_count", 0) + 1
        self.scan_label.setText(f"Scan #{self._scan_count} · "
                                f"{self.ctx.last_scan_iso} UTC · {demo_data.source_label()}")
        self._render_opportunities()
        if not silent:
            self.ctx.toast(f"Discovery refreshed ({demo_data.source_label()})")
        self._render_scorecard()

    def _render_opportunities(self) -> None:
        lay = self.opp_card.layout()
        clear_layout(lay)
        rows = demo_data.opportunity_rows()
        if not rows:
            self.opp_card.add(EmptyState("No evaluated opportunities",
                                          "Engines found nothing worth acting on."))
            return
        for row in rows[:8]:
            rec = row["record"]
            pill = QFrame()
            pill.setProperty("class", "pill")
            pill.setStyleSheet(
                f"QFrame {{ background:{active_theme().panel_alt}; border:1px solid "
                f"{active_theme().border}; border-radius:11px; }}")
            h = QHBoxLayout(pill)
            h.setContentsMargins(12, 8, 12, 8)
            sym = QLabel(rec.base_currency[:2].upper())
            sym.setFixedSize(34, 30)
            sym.setAlignment(Qt.AlignCenter)
            sym.setStyleSheet(f"border:1px solid {active_theme().border}; border-radius:8px;"
                              f"color:{active_theme().gold_bright}; font:bold 11px '{mono()}';")
            name = QLabel(f"<b>{rec.canonical_name}</b><br><span style='color:{active_theme().muted};"
                          f"font-size:11px'>{rec.broker_symbol} · D1/H4</span>")
            badge = Badge(row["direction"], "bull" if row["direction"] == "LONG" else "bear")
            why = QLabel(row["why"])
            why.setObjectName("Tiny")
            why.setWordWrap(True)
            em = QLabel("WATCH" if row["strength"] < 0.62 else "READY")
            em.setStyleSheet(f"font-weight:700; color:{active_theme().gold_bright};")
            h.addWidget(sym); h.addWidget(name); h.addWidget(badge)
            h.addWidget(why, 1); h.addWidget(em)
            btn = QPushButton("Evidence")
            btn.clicked.connect(lambda _=False, r=rec: self.open_evidence(r))
            h.addWidget(btn)
            lay.addWidget(pill)
        count = QLabel(f"{len(rows)} opportunities from {len(demo_data.universe())} symbols · "
                       "ranked by structure, location, liquidity, zone and timing evidence — not an opaque score.")
        count.setObjectName("Tiny")
        lay.addWidget(count)

    def open_evidence(self, rec) -> None:
        self.ctx.set_active_symbol(rec)
        self.ctx.navigate("evidence")

    def _active_thesis_plan(self):
        plans = self.ctx.store.plans()
        for st in (LifecycleState.THESIS, LifecycleState.WAITING, LifecycleState.TRIGGERED):
            for p in plans:
                if p.state == st:
                    return p
        return None

    def _render_thesis(self) -> None:
        lay = self.thesis_card.layout()
        clear_layout(lay)
        plan = self._active_thesis_plan()
        if plan is None:
            eb = QLabel("ACTIVE THESIS")
            eb.setObjectName("Eyebrow")
            lay.addWidget(eb)
            lay.addWidget(EmptyState(
                "No active thesis",
                "Pick an opportunity above and build a plan — your idea is valid when the "
                "evidence says so, and your timing arrives when the Wait Engine says so.",
                "Open planner", lambda: self.ctx.navigate("plans")))
            return
        eb = QLabel(f"ACTIVE THESIS · {plan.canonical_name}")
        eb.setObjectName("Eyebrow")
        lay.addWidget(eb)
        title = QLabel(plan.thesis[:90] or f"{plan.direction} plan")
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        lay.addWidget(title)
        wait = QLabel("Your idea is valid. Your timing isn't here yet.")
        wait.setStyleSheet(f"border-left:2px solid {active_theme().gold}; padding-left:12px;"
                           f"color:{active_theme().text}; margin:6px 0;")
        lay.addWidget(wait)
        for label, value in (("Entry area", f"{plan.entry:.5g}"),
                             ("Invalidation", f"{plan.stop:.5g}"),
                             ("Target", f"{plan.target:.5g}"),
                             ("Volume", f"{plan.volume:.2f} lots"),
                             ("State", plan.state.value)):
            row = QLabel(f"<span style='color:{active_theme().muted}'>{label}</span>"
                         f"&nbsp;&nbsp;<b style='font-family:{mono()}'>{value}</b>")
            lay.addWidget(row)
        btn = primary("Open planner")
        btn.clicked.connect(lambda: self.ctx.navigate("plans"))
        lay.addWidget(btn)

    def _render_stats(self) -> None:
        plans = self.ctx.store.plans()
        self.stat_thesis.set_value(f"{sum(1 for p in plans if p.state in (LifecycleState.THESIS, LifecycleState.WAITING)) + sum(1 for p in plans if p.state == LifecycleState.TRIGGERED):02d}")
        events = demo_data.calendar_events()
        now = datetime.now(timezone.utc)
        future = [e for e in events if e.time_utc > now]
        if future:
            e = future[0]
            self.stat_event.set_value(f"{e.title.split()[0]} · {e.time_utc:%a %H:%M}")
        else:
            self.stat_event.set_value("—")
        self.stat_scanned.set_value(str(len(demo_data.universe())))

    def _render_scorecard(self) -> None:
        lay = self.score_card.layout()
        clear_layout(lay)
        rows = demo_data.opportunity_rows()
        if not rows:
            lay.addWidget(QLabel("Nothing to score yet."))
            return
        top = rows[0]
        head = QLabel(f"{top['record'].canonical_name} · computed from engine verdicts")
        head.setObjectName("Tiny")
        lay.addWidget(head)
        grid = QGridLayout()
        for i, (group, val) in enumerate(top["scorecard"].items()):
            lab = QLabel(group)
            bar = QFrame()
            bar.setFixedHeight(8)
            bar.setStyleSheet(f"background:{active_theme().input}; border:1px solid "
                              f"{active_theme().border}; border-radius:4px;")
            vlab = QLabel("?" if val is None else str(val))
            vlab.setStyleSheet(f"font-family:'{mono()}';")
            if val is not None:
                inner = QFrame(bar)
                inner.setGeometry(0, 0, int(bar.width() * val / 100), 8)
            grid.addWidget(lab, i, 0)
            grid.addWidget(bar, i, 1)
            grid.addWidget(vlab, i, 2)
        lay.addLayout(grid)
        note = QLabel("MACRO requires a connected provider and stays unknown rather than invented (§1.1).")
        note.setObjectName("Tiny")
        lay.addWidget(note)
