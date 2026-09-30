"""Page: Plans — planner, contract-aware sizing, pre-flight, lifecycle (§15.5-4)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QTextEdit,
                               QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core import demo_data, engines, risk
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
        self._rec_cache: dict[str, tuple[float, object]] = {}
        self._rec_ttl = 1.0
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
            # Store a stable broker identifier, not the record itself. The live
            # provider rebuilds SymbolRecord on every tick, so comparing whole
            # records (findData on the dataclass) silently failed to match.
            self.symbol_combo.addItem(f"{r.canonical_name}  ({r.broker_symbol})",
                                      r.broker_symbol)
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
        self.btn_send = primary("Order_Send")
        self.btn_save.clicked.connect(self.save_plan)
        self.btn_send.clicked.connect(self.send_order)
        btns.addWidget(self.btn_fill)
        btns.addStretch(1)
        btns.addWidget(self.btn_preflight)
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_send)
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
        """Resolve the selected broker symbol to a live record.

        Keyed on broker_symbol rather than a stored record so a fresh tick from
        MT5 (new bid/ask) still resolves to the same instrument. Results are
        briefly cached because render_computed() runs on every keystroke and
        spinbox drag, and each live lookup is a terminal round-trip.
        """
        symbol = self.symbol_combo.currentData()
        if not symbol:
            return None
        now = time.monotonic()
        cached = self._rec_cache.get(symbol)
        if cached and now - cached[0] < self._rec_ttl:
            return cached[1]
        rec = demo_data.symbol(symbol)
        if rec is not None:
            self._rec_cache[symbol] = (now, rec)
        return rec

    def sync_symbol_selection(self, rec) -> None:
        if rec is None:
            return
        i = self.symbol_combo.findData(rec.broker_symbol)
        if i >= 0 and i != self.symbol_combo.currentIndex():
            self.symbol_combo.blockSignals(True)
            self.symbol_combo.setCurrentIndex(i)
            self.symbol_combo.blockSignals(False)
            self.on_form_changed()

    def on_form_changed(self) -> None:
        self.render_computed()

    def fill_from_engines(self) -> None:
        """Derive levels from the price the order will actually fill at.

        The levels used to be drawn around a D1 zone midpoint, which is a
        historical price: by the time the order was sent the market had often
        moved past it, leaving the target on the wrong side of the market and
        sizing the position off a distance it would never fill across.
        """
        rec = self.form_record()
        if rec is None:
            self.ctx.toast("Select an instrument first")
            return
        results = demo_data.engine_results(rec.broker_symbol, "H1")
        direction = "SHORT" if any(r.direction.value == "SHORT" and r.strength > 60
                                   for r in results) else "LONG"

        # A market buy fills at the ask and a sell at the bid; anchoring to the
        # wrong side puts the stop inside the spread on every single order.
        market = rec.ask if direction == "LONG" else rec.bid
        if market <= 0:
            market = rec.bid or rec.ask
        if market <= 0:
            self.ctx.toast("No live price for this instrument — MT5 is not quoting it")
            return

        bars = demo_data.bars(rec.broker_symbol, "H1", 200)
        sweep_price, sweep_kind = engines.last_sweep(bars)
        atr_value = engines.atr(bars) if bars else 0.0
        levels = risk.derive_levels(market, direction, rec.contract,
                                    sweep_price, sweep_kind, atr_value,
                                    family=rec.family)

        self.direction.setCurrentText(direction)
        self.entry.setValue(levels.entry)
        self.stop.setValue(levels.stop)
        self.target.setValue(levels.target)
        self.render_computed()
        self.ctx.toast(f"Levels from live {rec.broker_symbol} {market:.5g} — {levels.basis}")
        for note in levels.notes:
            self.ctx.toast(note)

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
        note = QLabel("Order_Send places a real market order on the connected MT5 account. "
                      "It is blocked unless order_check passes, the broker accepts the stops, "
                      "and you type SEND to confirm. The fill is verified against the account "
                      "before it is reported as sent (§10.3).")
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

    def send_order(self) -> None:
        rec, s, ok, checks = self._evaluate_form()
        if rec is None or s is None or not s.ok:
            self.ctx.toast("Order_Send blocked: " + (checks[0] if checks else "invalid setup"))
            return
        if not ok:
            self.ctx.toast("Order_Send blocked: " + (checks[0] if checks else "broker constraints violated"))
            return

        # Never dispatch while the terminal is down: the point of this button is
        # a real order, and a silent paper-mode success hides that.
        status = demo_data.connection_status()
        if not status.get("connected"):
            self.ctx.toast("Order_Send blocked: MT5 is not connected. "
                           "Open MT5, sign in to a trading account, then retry.")
            return

        direction = self.direction.currentText()
        volume = s.volume
        entry, stop, target = self.entry.value(), self.stop.value(), self.target.value()
        ticket = 0
        if not self.ctx.confirm_typed("Send real order to MT5",
                                      f"LIVE ORDER — {rec.broker_symbol} {direction} "
                                      f"{volume:.2f} lots\n"
                                      f"Entry {entry:.5g} · SL {stop:.5g} · TP {target:.5g}\n"
                                      f"Account: {status.get('login', '?')} @ {status.get('server', '?')}\n\n"
                                      f"Type SEND to place this order at the market.",
                                      "SEND"):
            return

        self.btn_send.setEnabled(False)
        self.btn_send.setText("Sending…")
        try:
            result = demo_data.order_send(
                rec.broker_symbol, direction, volume,
                stop=stop, target=target, planned_entry=entry,
                magic=int(self.ctx.setting("order_magic") or 20260101),
                deviation_points=int(self.ctx.setting("order_deviation") or 20),
                comment="SwingDesk")
        except Exception as exc:
            self.ctx.toast(f"Order_Send error: {type(exc).__name__}: {exc}")
            return
        finally:
            self.btn_send.setEnabled(True)
            self.btn_send.setText("Order_Send")

        if not result.ok:
            self.ctx.toast(f"Order REJECTED — {result.message}")
            return
        ticket = result.ticket
        slip = ""
        if result.price and entry:
            slip = f" (fill {result.price:.5g}, plan {entry:.5g})"
        if not result.verified:
            self.ctx.toast(f"Order sent but NOT confirmed listed — {result.message}")
            return
        self.ctx.toast(f"Order FILLED — {rec.broker_symbol} {direction} {volume:.2f} lots "
                       f"ticket {ticket}{slip}")
        self._record_dispatch(rec, direction, volume, stop, target, result)

    def _record_dispatch(self, rec, direction: str, volume: float,
                         stop: float, target: float, result) -> None:
        """Persist the dispatch as an OPEN plan so the fill is auditable."""
        plan = Plan(
            id=new_id("plan"), broker_symbol=rec.broker_symbol,
            canonical_name=rec.canonical_name, direction=direction,
            entry=result.planned_entry or result.price, stop=stop, target=target,
            risk_percent=self.risk_pct.value(), volume=volume,
            thesis=self.thesis_text.toPlainText().strip(),
            state=LifecycleState.OPEN, created_at=now_iso(), updated_at=now_iso(),
            actual_fill=result.price,
            behaviour_flags=[f"mt5_ticket:{result.ticket}",
                             f"mt5_retcode:{result.retcode}"])
        self.ctx.store.save_plan(plan)
        self.ctx.events.plans_changed.emit()
        self.ctx.events.positions_changed.emit()

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
            if actual_risk > sizing.risk_amount * risk.MAX_RISK_OVERAGE_FACTOR + 1e-9:
                order_ok = False
                checks = list(checks) + ["Stored volume exceeds the plan risk cap."]
            if not order_ok:
                self.ctx.toast("Dispatch blocked: " +
                               (checks[0] if checks else "order_check rejected"))
                return
            if not self.ctx.confirm("Advance plan to " + new_state.value,
                                    f"Mark {plan.canonical_name} {plan.direction} "
                                    f"{plan.volume:.2f} lots as {new_state.value}?\n"
                                    "Use Order_Send on the planner to place an actual order."):
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
