"""Page: Journal — closed plans, plan-vs-actual, behaviour flags (§15.5-6)."""
from __future__ import annotations

import csv

from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core.models import LifecycleState
from ...core.store import now_iso
from ..theme import mono
from ..widgets import Badge, Card, EmptyState, heading, page_wrapper, primary, clear_layout

FLAGS = ("Followed plan", "Exited early", "Moved SL", "Over-risked", "Skipped valid setup")


class JournalPage(QWidget):
    KEY = "journal"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Journal",
            "Original thesis, engine snapshot and plan-vs-execution delta.",
            "Review what actually happened"))

        top = QHBoxLayout()
        self.btn_export = QPushButton("Export journal (CSV)")
        self.btn_export.clicked.connect(self.export_csv)
        top.addStretch(1)
        top.addWidget(self.btn_export)
        self.root.addLayout(top)

        self.list_card = Card("Closed plans")
        self.root.addWidget(self.list_card)
        self.review_card = Card("Complete a review")
        self.root.addWidget(self.review_card)
        ctx.events.plans_changed.connect(self.render)
        self.render()

    # ---------------------------------------------------------------- render
    def closed_plans(self):
        return [p for p in self.ctx.store.plans()
                if p.state in (LifecycleState.CLOSED, LifecycleState.REVIEW)]

    def render(self) -> None:
        self.render_list()
        self.render_review()

    def render_list(self) -> None:
        lay = self.list_card.layout()
        clear_layout(lay)
        plans = self.closed_plans()
        if not plans:
            lay.addWidget(EmptyState(
                "Nothing closed yet",
                "Close a plan on the lifecycle board (or close a linked position) and it "
                "appears here with its plan-vs-actual delta.",
                "Go to plans", lambda: self.ctx.navigate("plans")))
            return
        for p in plans:
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 7, 10, 7)
            title = QLabel(f"<b>{p.canonical_name}</b> {p.direction} · {p.created_at[:10]}")
            delta = p.actual_fill - p.entry if p.actual_fill else None
            detail = QLabel(
                f"Planned entry {p.entry:.5g}" +
                (f" · filled {p.actual_fill:.5g} ({delta:+.5g})" if p.actual_fill else " · no fill") +
                (f" · realised {p.realised_r:+.2f}R" if p.realised_r is not None else ""))
            detail.setObjectName("Tiny")
            badge = Badge(p.state.value, "bull" if p.state == LifecycleState.REVIEW else "gold")
            flags = QLabel(", ".join(p.behaviour_flags) if p.behaviour_flags else "no flags")
            flags.setObjectName("Tiny")
            h.addWidget(title); h.addWidget(detail, 1); h.addWidget(flags); h.addWidget(badge)
            row.setStyleSheet(f"QFrame {{ background:{active_theme().panel_alt};"
                              f" border:1px solid {active_theme().border}; border-radius:10px; }}")
            lay.addWidget(row)

    def render_review(self) -> None:
        lay = self.review_card.layout()
        clear_layout(lay)
        plans = [p for p in self.closed_plans() if not p.review_completed]
        if not plans:
            lay.addWidget(QLabel("All closed plans have been reviewed. Good discipline."))
            return
        row = QHBoxLayout()
        self.plan_combo = QComboBox()
        for p in plans:
            self.plan_combo.addItem(f"{p.canonical_name} · {p.direction} · {p.created_at[:10]}", p.id)
        row.addWidget(self.plan_combo, 1)
        lay.addLayout(row)
        self.flag_boxes = {}
        frow = QHBoxLayout()
        for f in FLAGS:
            from PySide6.QtWidgets import QCheckBox
            cb = QCheckBox(f)
            self.flag_boxes[f] = cb
            frow.addWidget(cb)
        lay.addLayout(frow)
        self.note = QTextEdit()
        self.note.setPlaceholderText("What actually happened? What would you repeat?")
        self.note.setMaximumHeight(70)
        lay.addWidget(self.note)
        btn = primary("Complete review")
        btn.clicked.connect(self.complete_review)
        lay.addWidget(btn)

    # --------------------------------------------------------------- actions
    def complete_review(self) -> None:
        plan_id = self.plan_combo.currentData()
        plans = {p.id: p for p in self.ctx.store.plans()}
        plan = plans.get(plan_id)
        if plan is None:
            self.ctx.toast("Select a plan to review")
            return
        plan.behaviour_flags = [f for f, cb in self.flag_boxes.items() if cb.isChecked()]
        plan.review_note = self.note.toPlainText().strip()
        plan.review_completed = True
        plan.state = LifecycleState.REVIEW
        plan.updated_at = now_iso()
        self.ctx.store.save_plan(plan)
        self.ctx.events.plans_changed.emit()
        self.ctx.toast(f"Review completed — {plan.canonical_name}")

    def export_csv(self) -> None:
        plans = self.closed_plans()
        if not plans:
            self.ctx.toast("Nothing to export yet")
            return
        path = self.ctx.exports_dir() / "journal.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["canonical", "broker_symbol", "direction", "state",
                             "entry", "stop", "target", "volume", "risk_percent",
                             "actual_fill", "realised_r", "flags", "review", "created_at"])
            for p in plans:
                writer.writerow([p.canonical_name, p.broker_symbol, p.direction,
                                 p.state.value, p.entry, p.stop, p.target, p.volume,
                                 p.risk_percent, p.actual_fill, p.realised_r,
                                 ";".join(p.behaviour_flags), p.review_note, p.created_at])
        self.ctx.toast(f"Journal exported → {path}")

    def refresh(self) -> None:
        self.render()
