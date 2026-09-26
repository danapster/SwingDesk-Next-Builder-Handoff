"""Page: Plans — planner, contract-aware sizing, pre-flight, lifecycle (§15.5-4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QTextEdit,
                               QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core import demo_data, risk
from ...core.models import LIFECYCLE_TRANSITIONS, LifecycleState, Plan
from ...core.store import new_id, now_iso
from ..theme import mono
from ..widgets import Badge, Card, EmptyState, heading, page_wrapper, primary, clear_layout

BOARD_COLUMNS = [LifecycleState.SCANNING, LifecycleState.WATCHING, LifecycleState.THESIS,
                 LifecycleState.WAITING, LifecycleState.TRIGGERED, LifecycleState.OPEN,
                 LifecycleState.MANAGING, LifecycleState.CLOSED, LifecycleState.REVIEW]


class PlansPage(QWidget):
    KEY = "plans"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(w)
        outer.addWidget(scroll)

        self.ctx = ctx
        self.root.addWidget(heading("Planner",
                                    "Plan the trade before you take it. Sizing uses the broker "
                                    "contract; dispatch needs an accepted order_check.",
                                    "Thesis → risk → pre-flight"))

        form_wrap = QWidget()
        fl = QHBoxLayout(form_wrap)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(14)

        # ------------------------------------------------------------ form
        form = Card("Trade setup")
        fl.addWidget(form, 1)
        self.symbol_combo = QComboBox()
        for r in demo_data.universe():
            self.symbol_combo.addItem(f"{r.canonical_name}  ({r.broker_symbol})", r)
        self.symbol_combo.currentIndexChanged.connect(self.on_form_changed)
        self.direction = QComboBox()
        self.direction.addItems(("LONG", "SHORT"))
        self.entry = QDoubleSpinBox()
        self.stop = QDoubleSpinBox()
        self.target = QDoubleSpinBox()
        for spin in (self.entry, self.stop, self.target):
            spin.setDecimals(6)
            spin.setRange(0.0, 10_000_000.0)
            spin.setSingleStep(0.0001)
            spin.valueChanged.connect(self.on_form_changed)
        self.risk_pct = QDoubleSpinBox()
        self.risk_pct.setDecimals(2)
        self.risk_pct.setRange(0.1, 100.0)
        self.risk_pct.setValue(float(ctx.setting("default_risk") or 1.0))
        self.risk_pct.valueChanged.connect(self.on_form_changed)
        self.direction.currentIndexChanged.connect(self.on_form_changed)
        for lab, wid in (("Instrument", self.symbol_combo), ("Direction", self.direction),
                         ("Entry", self.entry), ("Stop loss", self.stop),
                         ("Take profit", self.target),
                         (f"Risk % of {demo_data.account_equity():,.0f} equity", self.risk_pct)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab))
            row.addStretch(1)
            row.addWidget(wid, 1)
            form.layout().addLayout(row)
        self.thesis_text = QTextEdit()
        self.thesis_text.setPlaceholderText(
            "Why this trade? Engine reasons are snapshotted automatically; add your own notes…")
        self.thesis_text.setMaximumHeight(74)
        form.add(QLabel("Thesis"))
        form.add(self.thesis_text)

        btns = QHBoxLayout()
        self.btn_fill = QPushButton("Use engine levels")
        self.btn_fill.clicked.connect(self.fill_from_engines)
        self.btn_preflight = primary("Run pre-flight")
        self.btn_preflight.clicked.connect(self.run_preflight)
        self.btn_save = primary("Save plan")
        self.btn_save.clicked.connect(self.save_plan)
        btns.addWidget(self.btn_fill)
        btns.addStretch(1)
        btns.addWidget(self.btn_preflight)
        btns.addWidget(self.btn_save)
        form.layout().addLayout(btns)

        # --------------------------------------------------------- computed
        self.computed = Card("Computed for you — broker contract math")
        fl.addWidget(self.computed, 1)
        self.root.addWidget(form_wrap)

        # ------------------------------------------------------------ board
        self._check_state = None
        self.board = Card("Lifecycle board")
        self.root.addWidget(self.board)
        self.render_computed()
        self.render_board()
        ctx.events.plans_changed.connect(self.render_board)
        ctx.events.symbol_changed.connect(self.sync_symbol_selection)

    # --------------------------------------------------------------- helpers
    def form_record(self):
        return self.symbol_combo.currentData()

    def sync_symbol_selection(self, rec) -> None:
        i = self.symbol_combo.findData(rec)
        if i >= 0 and i != self.symbol_combo.currentIndex():
            self.symbol_combo.blockSignals(True)
            self.symbol_combo.setCurrentIndex(i)
            self.symbol_combo.blockSignals(False)
            self.on_form_changed()

    def on_form_changed(self) -> None:
        self.render_computed()

    def fill_from_engines(self) -> None:
        rec = self.form_record()
        if rec is None:
            self.ctx.toast("Select an instrument first")
            return
        results = demo_data.engine_results(rec.broker_symbol, "D1")
        zones = [lv for r in results for lv in r.evidence if lv.kind == "zone"]
        anchor = rec.bid
        if zones:
            z = zones[0]
            mid = z.price
            anchor = mid
            span = (z.upper - z.price) if z.upper else abs(z.price * 0.004)
            entry = mid + span * 0.15
            stop = mid - span * 1.1
            target = mid + span * 4.0
        else:
            price = rec.bid
            entry, stop, target = price, price * 0.996, price * 1.014
        direction = "SHORT" if any(r.direction.value == "SHORT" and r.strength > 60
                                   for r in results) else "LONG"
        if direction == "SHORT":
            # `mid` did not exist in the no-zone fallback, causing a crash for
            # short engine votes.  Reflect around the active anchor instead.
            entry, stop, target = (2 * anchor - entry,
                                   2 * anchor - stop,
                                   2 * anchor - target)
        self.direction.setCurrentText(direction)
        self.entry.setValue(round(entry, 6))
        self.stop.setValue(round(stop, 6))
        self.target.setValue(round(target, 6))
        self.render_computed()
        self.ctx.toast("Levels filled from Engine B zone + engine direction votes")

    # ------------------------------------------------------------- computed
    def _levels_match_direction(self, entry: float, stop: float, target: float) -> bool:
        if self.direction.currentText() == "LONG":
            return stop < entry < target
        return target < entry < stop

    def _evaluate_form(self):
        """Return (record, sizing, order_ok, checks) for one planner snapshot."""
        rec = self.form_record()
        if rec is None:
            return None, None, False, ["Select an instrument."]
        entry, stop, target = self.entry.value(), self.stop.value(), self.target.value()
        if not self._levels_match_direction(entry, stop, target):
            return rec, None, False, [
                "Levels must be ordered stop → entry → target for LONG, or target → entry → stop for SHORT."
            ]
        equity = demo_data.account_equity()
        sizing = risk.size_position(entry, stop, target, self.risk_pct.value(),
                                    equity, rec.contract)
        if not sizing.ok:
            return rec, sizing, False, list(sizing.reasons)
        ok, checks = risk.order_check(entry, stop, target, sizing.volume,
                                      rec.contract, equity)
        return rec, sizing, ok, checks

    def render_computed(self) -> None:
        lay = self.computed.layout()
        clear_layout(lay)
        rec, s, ok, checks = self._evaluate_form()
        if rec is None:
            lay.addWidget(QLabel("Select an instrument."))
            return
        if s is None or not s.ok:
            reasons = checks if s is None else list(s.reasons)
            msg = QLabel("⚠ " + " ".join(reasons))
            msg.setWordWrap(True)
            msg.setStyleSheet(f"color:{active_theme().bear};")
            lay.addWidget(msg)
            self._check_state = QLabel("✗ SIZING INVALID — " + " ".join(reasons))
            self._check_state.setStyleSheet(f"color:{active_theme().bear};")
            lay.addWidget(self._check_state)
            return
        grid = QHBoxLayout()
        for label, value in (("Max loss", f"${s.risk_amount:,.2f}"),
                             ("Position size", f"{s.volume:.2f} lots"),
                             ("Actual risk", f"${s.actual_risk:,.2f}"),
                             ("Reward:risk", f"{s.risk_reward:.2f}R"),
                             ("Loss/lot", f"{s.loss_per_lot:,.2f}")):
            from ..widgets import Stat
            st = Stat(label, value)
            grid.addWidget(st)
        lay.addLayout(grid)
        for reason in s.reasons:
            r = QLabel("⚠ " + reason)
            r.setStyleSheet(f"color:{active_theme().gold_bright};")
            r.setWordWrap(True)
            lay.addWidget(r)
        self._check_state = QLabel(
            ("✓ order_check PASSED — " if ok else "✗ order_check REJECTED — ") +
            "; ".join(checks))
        self._check_state.setWordWrap(True)
        self._check_state.setStyleSheet(
            f"color:{active_theme().bull if ok else active_theme().bear};")
        lay.addWidget(self._check_state)
        note = QLabel("Demo paper mode: dispatch is validation-only. Nothing is ever sent to a "
                      "broker without an accepted order_check and explicit confirmation (§10.3).")
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        lay.addWidget(note)

    def run_preflight(self) -> None:
        self.render_computed()
        rec, s, ok, checks = self._evaluate_form()
        if rec is None or s is None or not s.ok:
            self.ctx.toast("Pre-flight blocked: " + (checks[0] if checks else "invalid setup"))
            return
        if ok:
            self.ctx.toast(f"Pre-flight PASSED for {rec.broker_symbol} @ {s.volume:.2f} lots")
        else:
            self.ctx.toast("Pre-flight FAILED — " + (checks[0] if checks else "broker constraints violated"))

    # ----------------------------------------------------------------- plans
    def save_plan(self) -> None:
        rec = self.form_record()
        if rec is None:
            self.ctx.toast("Select an instrument first")
            return
        entry, stop, target = self.entry.value(), self.stop.value(), self.target.value()
        if entry == 0 or stop == 0 or target == 0:
            self.ctx.toast("Entry, stop and target are required")
            return
        if (self.direction.currentText() == "LONG" and not (stop < entry < target)) or \
           (self.direction.currentText() == "SHORT" and not (target < entry < stop)):
            self.ctx.toast("Levels must be ordered stop → entry → target for the direction")
            return
        s = risk.size_position(entry, stop, target, self.risk_pct.value(),
                               demo_data.account_equity(), rec.contract)
        if not s.ok:
            self.ctx.toast("Plan blocked: " + (s.reasons[0] if s.reasons else "invalid sizing"))
            return
        check_ok, checks = risk.order_check(entry, stop, target, s.volume, rec.contract,
                                            demo_data.account_equity())
        if not check_ok:
            self.ctx.toast("Plan blocked: " + (checks[0] if checks else "pre-flight failed"))
            return
        snapshot = json.dumps(
            [{"engine": r.engine_id, "verdict": r.verdict.value, "strength": r.strength,
              "reasons": [x.text for x in r.reasons]}
             for r in demo_data.engine_results(rec.broker_symbol, "D1")], indent=1)
        plan = Plan(
            id=new_id("plan"), broker_symbol=rec.broker_symbol,
            canonical_name=rec.canonical_name, direction=self.direction.currentText(),
            entry=entry, stop=stop, target=target,
            risk_percent=self.risk_pct.value(), volume=s.volume,
            thesis=self.thesis_text.toPlainText().strip(),
            state=LifecycleState.THESIS, created_at=now_iso(), updated_at=now_iso(),
            engine_snapshot=snapshot)
        self.ctx.store.save_plan(plan)
        self.ctx.events.plans_changed.emit()
        self.ctx.toast(f"Plan saved — {plan.canonical_name} {plan.direction} "
                       f"@ {plan.volume:.2f} lots (THESIS)")
        self.thesis_text.clear()

    # ----------------------------------------------------------------- board
    def render_board(self) -> None:
        lay = self.board.layout()
        clear_layout(lay)
        plans = self.ctx.store.plans()
        # Keep the nine lifecycle columns inside their own horizontal viewport.
        # Previously their combined minimum width enlarged the entire page and
        # pushed the planner/computed panels off-screen.
        canvas = QWidget()
        row = QHBoxLayout(canvas)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        for col_state in BOARD_COLUMNS:
            col = QFrame()
            col.setStyleSheet(f"QFrame {{ background:{active_theme().input};"
                              f" border:1px solid {active_theme().border}; border-radius:10px; }}")
            cv = QVBoxLayout(col)
            cv.setContentsMargins(8, 8, 8, 8)
            items = [p for p in plans if p.state == col_state]
            head = QLabel(f"{col_state.value} · {len(items)}")
            head.setStyleSheet(f"color:{active_theme().muted}; font-size:10px;"
                               f" letter-spacing:1px;")
            cv.addWidget(head)
            for p in items:
                card = QFrame()
                card.setStyleSheet(f"QFrame {{ background:{active_theme().panel_alt};"
                                   f" border:1px solid {active_theme().border};"
                                   f" border-radius:8px; }}")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(8, 7, 8, 7)
                cl.setSpacing(4)
                t = QLabel(f"<b>{p.canonical_name}</b> {p.direction}")
                cl.addWidget(t)
                d = QLabel(f"{p.entry:.5g} / SL {p.stop:.5g} / TP {p.target:.5g}")
                d.setStyleSheet(f"font-family:'{mono()}'; font-size:10px;"
                                f" color:{active_theme().muted};")
                cl.addWidget(d)
                if p.realised_r is not None:
                    r = QLabel(f"{p.realised_r:+.2f}R")
                    r.setStyleSheet(f"font-weight:700; color:"
                                    f"{active_theme().bull if p.realised_r > 0 else active_theme().bear};")
                    cl.addWidget(r)
                for nxt in LIFECYCLE_TRANSITIONS[p.state]:
                    b = QPushButton(f"→ {nxt.value}")
                    b.setStyleSheet("padding:3px 8px; font-size:11px;")
                    b.clicked.connect(lambda _=False, pid=p.id, ns=nxt: self.transition(pid, ns))
                    cl.addWidget(b)
                if p.state in (LifecycleState.CLOSED, LifecycleState.REVIEW):
                    jb = QPushButton("Journal")
                    jb.setStyleSheet("padding:3px 8px; font-size:11px;")
                    jb.clicked.connect(lambda _=False, pid=p.id: self.goto_journal(pid))
                    cl.addWidget(jb)
                xb = QPushButton("Delete")
                xb.setStyleSheet("padding:3px 8px; font-size:11px;")
                xb.clicked.connect(lambda _=False, pid=p.id: self.delete_plan(pid))
                cl.addWidget(xb)
                cv.addWidget(card)
            cv.addStretch(1)
            col.setMinimumWidth(168)
            row.addWidget(col)
        canvas.adjustSize()
        board_scroll = QScrollArea()
        board_scroll.setObjectName("LifecycleBoardScroll")
        board_scroll.setFrameShape(QFrame.NoFrame)
        board_scroll.setWidgetResizable(False)
        board_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        board_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        board_scroll.setWidget(canvas)
        board_scroll.setMinimumHeight(max(180, min(canvas.sizeHint().height() + 24, 420)))
        board_scroll.setMaximumHeight(440)
        self.board_scroll = board_scroll
        lay.addWidget(board_scroll)
        if not plans:
            lay.addWidget(EmptyState(
                "No plans yet",
                "Fill the form above (or press “Use engine levels”) and save your first plan. "
                "Plans persist in the local database across restarts.",
                "Use engine levels", self.fill_from_engines))

    def transition(self, plan_id: str, new_state: LifecycleState) -> None:
        plans = {p.id: p for p in self.ctx.store.plans()}
        plan = plans.get(plan_id)
        if plan is None:
            return
        if new_state not in LIFECYCLE_TRANSITIONS[plan.state]:
            self.ctx.toast(f"Illegal transition {plan.state.value} → {new_state.value} blocked")
            return
        if new_state in (LifecycleState.OPEN, LifecycleState.TRIGGERED):
            rec = demo_data.symbol(plan.broker_symbol)
            if rec is None:
                self.ctx.toast("Dispatch blocked: broker contract unavailable")
                return
            sizing = risk.size_position(plan.entry, plan.stop, plan.target,
                                        plan.risk_percent, demo_data.account_equity(),
                                        rec.contract)
            if not sizing.ok:
                self.ctx.toast("Dispatch blocked: " +
                               (sizing.reasons[0] if sizing.reasons else "invalid sizing"))
                return
            order_ok, checks = risk.order_check(plan.entry, plan.stop, plan.target,
                                                plan.volume, rec.contract,
                                                demo_data.account_equity())
            actual_risk = plan.volume * sizing.loss_per_lot
            if actual_risk > sizing.risk_amount + 1e-9:
                order_ok = False
                checks = list(checks) + ["Stored volume exceeds the plan risk cap."]
            if not order_ok:
                self.ctx.toast("Dispatch blocked: " +
                               (checks[0] if checks else "order_check rejected"))
                return
            if not self.ctx.confirm("Confirm dispatch (paper mode)",
                                    f"Send {plan.canonical_name} {plan.direction} "
                                    f"{plan.volume:.2f} lots to broker validation?\n"
                                    "Paper mode: order_check runs, nothing is sent."):
                return
        plan.state = new_state
        plan.updated_at = now_iso()
        if new_state == LifecycleState.CLOSED:
            plan.closed_at = now_iso()
        self.ctx.store.save_plan(plan)
        self.ctx.events.plans_changed.emit()
        self.ctx.toast(f"{plan.canonical_name}: {new_state.value}")

    def goto_journal(self, plan_id: str) -> None:
        self.ctx.navigate("journal")

    def delete_plan(self, plan_id: str) -> None:
        plans = {p.id: p for p in self.ctx.store.plans()}
        plan = plans.get(plan_id)
        if plan and self.ctx.confirm("Delete plan",
                                     f"Delete the {plan.canonical_name} plan permanently?"):
            self.ctx.store.delete_plan(plan_id)
            self.ctx.events.plans_changed.emit()
            self.ctx.toast("Plan deleted")

    def refresh(self) -> None:
        self.render_computed()
        self.render_board()
