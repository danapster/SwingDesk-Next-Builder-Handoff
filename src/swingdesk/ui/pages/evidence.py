"""Page: Evidence — selected-market chart, layers, evidence stack (§15.5-3)."""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core import demo_data
from ...core.models import EvidenceLevel, Verdict
from ..chart import CandleChart
from ..widgets import Badge, Card, heading, page_wrapper, primary, clear_layout

LAYER_SOURCES = {
    "Structure": ("A.structure",),
    "Liquidity": ("C.liquidity",),
    "S&D": ("B.supply_demand",),
    "FVG": ("D.fvg",),
    "Order blocks": ("E.order_block",),
    "Targets": ("F.ote", "G.crt", "I.divergence"),
}
ALL_TFS = ("M15", "H1", "H4", "D1", "W1")


class EvidencePage(QWidget):
    KEY = "evidence"

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
        self.timeframe = "D1"
        self.layer_state = {k: True for k in LAYER_SOURCES}

        self.root.addWidget(heading(
            "Evidence",
            "Chart as evidence. Canonical name shown, broker symbol retained for execution.",
            "Instrument evidence"))

        # selector row — chart is bound to this selection, never a default (§20)
        sel = QHBoxLayout()
        self.symbol_combo = QComboBox()
        self.symbol_combo.currentIndexChanged.connect(self.on_symbol_changed)
        sel.addWidget(QLabel("Market"))
        sel.addWidget(self.symbol_combo, 1)
        self.btn_fit = QPushButton("Fit chart")
        self.btn_fit.clicked.connect(self.chart_fit)
        self.btn_snapshot = QPushButton("Export chart (PNG)")
        self.btn_snapshot.clicked.connect(self.export_chart)
        self.btn_thesis = primary("Create thesis")
        self.btn_thesis.clicked.connect(self.create_thesis)
        sel.addWidget(self.btn_fit)
        sel.addWidget(self.btn_snapshot)
        sel.addWidget(self.btn_thesis)
        self.root.addLayout(sel)

        # timeframe buttons
        tfrow = QHBoxLayout()
        tfrow.addWidget(QLabel("Timeframe"))
        self._tf_group = QButtonGroup(self)
        self._tf_group.setExclusive(True)
        for tf in ALL_TFS:
            b = QPushButton(tf)
            b.setCheckable(True)
            b.setChecked(tf == self.timeframe)
            b.clicked.connect(lambda _=False, t=tf: self.set_timeframe(t))
            self._tf_group.addButton(b)
            tfrow.addWidget(b)
        tfrow.addStretch(1)
        self.freshness = QLabel("")
        self.freshness.setObjectName("Tiny")
        tfrow.addWidget(self.freshness)
        self.root.addLayout(tfrow)

        # chart + layer toggles
        chartrow = QHBoxLayout()
        self.chart = CandleChart()
        chartrow.addWidget(self.chart, 1)
        layerbox = QWidget()
        llay = QVBoxLayout(layerbox)
        llay.setContentsMargins(8, 8, 8, 8)
        llay.setSpacing(7)
        llay.addWidget(QLabel("Layers"))
        self.layer_checks: dict[str, QCheckBox] = {}
        for name in LAYER_SOURCES:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.toggled.connect(lambda _=False, n=name: self.toggle_layer(n))
            self.layer_checks[name] = cb
            llay.addWidget(cb)
        llay.addStretch(1)
        layerbox.setMaximumWidth(170)
        chartrow.addWidget(layerbox)
        self.root.addLayout(chartrow, 1)

        # evidence stack
        self.stack_card = Card("Evidence stack — why is this here?")
        self.root.addWidget(self.stack_card)

        self.status_row = QLabel("")
        self.status_row.setWordWrap(True)
        self.root.addWidget(self.status_row)

        self.btn_thesis = primary("Create thesis")
        self.btn_thesis.clicked.connect(self.create_thesis)

        ctx.events.symbol_changed.connect(lambda _r: self.load_symbol_combo())
        self.load_symbol_combo()

    # ------------------------------------------------------------------ data
    def current_record(self):
        idx = self.symbol_combo.currentIndex()
        if idx < 0:
            return self.ctx.active_symbol or demo_data.universe()[0]
        return self.symbol_combo.itemData(idx)

    def load_symbol_combo(self) -> None:
        recs = demo_data.universe()
        self.symbol_combo.blockSignals(True)
        self.symbol_combo.clear()
        for r in recs:
            self.symbol_combo.addItem(f"{r.canonical_name}  ({r.broker_symbol})", r)
        if self.ctx.active_symbol:
            i = self.symbol_combo.findData(self.ctx.active_symbol)
            if i >= 0:
                self.symbol_combo.setCurrentIndex(i)
        self.symbol_combo.blockSignals(False)
        self.reload_chart()

    def on_symbol_changed(self) -> None:
        rec = self.current_record()
        if rec is not None:
            self.ctx.set_active_symbol(rec)
        self.reload_chart()

    def set_timeframe(self, tf: str) -> None:
        if tf not in ALL_TFS:
            return
        self.timeframe = tf
        for b in self._tf_group.buttons():
            b.setChecked(b.text() == tf)
        self.reload_chart()

    def toggle_layer(self, name: str) -> None:
        self.layer_state[name] = self.layer_checks[name].isChecked()
        self.reload_chart()

    def active_layers(self) -> list[EvidenceLevel]:
        rec = self.current_record()
        results = demo_data.engine_results(rec.broker_symbol, self.timeframe)
        ids: list[str] = []
        for name, engine_ids in LAYER_SOURCES.items():
            if self.layer_state.get(name, True):
                ids.extend(engine_ids)
        out: list[EvidenceLevel] = []
        for r in results:
            if r.engine_id in ids:
                out.extend(r.evidence)
        return out

    def reload_chart(self) -> None:
        rec = self.current_record()
        if rec is None:
            return
        bars = demo_data.bars(rec.broker_symbol, self.timeframe)
        self.chart.set_data(rec.canonical_name, self.timeframe, bars, self.active_layers())
        self.freshness.setText(
            f"{len(bars)} bars · refreshed just now · {rec.broker_symbol} @ "
            f"{rec.bid:.5g} / {rec.ask:.5g} (demo)")
        self.render_stack()

    # ----------------------------------------------------------------- views
    def render_stack(self) -> None:
        lay = self.stack_card.layout()
        clear_layout(lay)
        rec = self.current_record()
        results = demo_data.engine_results(rec.broker_symbol, self.timeframe)
        shown = 0
        for r in results:
            if r.verdict == Verdict.NOT_PRESENT and not r.reasons:
                continue
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 7, 10, 7)
            name = QLabel(f"<b>{r.engine_id}</b><br><span style='color:{active_theme().muted};"
                          f"font-size:11px'>{' · '.join(rs.text for rs in r.reasons[:2])}</span>")
            name.setWordWrap(True)
            verdict_kind = {"ACTIVE": "bull", "WATCHING": "gold", "INVALID": "bear"}.get(
                r.verdict.value, "muted")
            badge = Badge(f"{r.verdict.value} {int(r.strength)}", verdict_kind)
            direction = QLabel(r.direction.value)
            direction.setObjectName("Tiny")
            h.addWidget(name, 1); h.addWidget(direction); h.addWidget(badge)
            row.setStyleSheet(f"QFrame {{ background:{active_theme().panel_alt};"
                              f" border:1px solid {active_theme().border}; border-radius:10px; }}")
            lay.addWidget(row)
            shown += 1
        note = QLabel("Every card is produced by an engine from real bars; the UI never "
                      "recalculates an engine concept (§11.2). Computed just now.")
        note.setObjectName("Tiny")
        lay.addWidget(note)
        self.status_row.setText(
            f"<b style='color:{active_theme().gold_bright}'>STATUS: EVIDENCE ONLY</b> — "
            "no order is sent from the evidence view. Create a thesis to plan it.")

    # ---------------------------------------------------------------- buttons
    def chart_fit(self) -> None:
        self.chart.fit()
        self.ctx.toast("Chart reset to fit")

    def export_chart(self) -> None:
        pix = self.chart.grab()
        path = self.ctx.exports_dir() / f"chart-{self.current_record().broker_symbol.replace('.', '_')}-{self.timeframe}.png"
        pix.save(str(path))
        self.ctx.toast(f"Chart exported → {path.name}")

    def create_thesis(self) -> None:
        rec = self.current_record()
        self.ctx.set_active_symbol(rec)
        self.ctx.navigate("plans")

    def refresh(self) -> None:
        self.load_symbol_combo()
