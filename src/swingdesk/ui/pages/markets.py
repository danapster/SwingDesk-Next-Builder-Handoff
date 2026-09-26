"""Page: Markets — four explicit scopes, search, bulk enablement (§15.5-2)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core import demo_data
from ...core.models import UniverseScope, Verdict
from ..widgets import heading, page_wrapper, primary


class MarketsPage(QWidget):
    KEY = "markets"

    SCOPE_LABELS = {
        UniverseScope.ALL: "All broker symbols",
        UniverseScope.MARKET_WATCH: "Market Watch",
        UniverseScope.MAPPED: "Mapped",
        UniverseScope.ACTIVE_SETUPS: "Active setups",
    }

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        self.ctx = ctx
        self.root.addWidget(heading(
            "Markets",
            "Discovery, never assumption. Four explicit scopes — never conflated.",
            "MT5 universe · demo adapter"))

        filters = QHBoxLayout()
        self.scope_combo = QComboBox()
        for scope in UniverseScope:
            self.scope_combo.addItem(self.SCOPE_LABELS[scope], scope.value)
        self.scope_combo.currentIndexChanged.connect(self.render_table)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search symbol or name…")
        self.search.textChanged.connect(self.render_table)
        self.class_filter = QComboBox()
        self.class_filter.addItem("All asset classes", "")
        for c in ("FX", "CFD"):
            self.class_filter.addItem(c, c)
        self.class_filter.currentIndexChanged.connect(self.render_table)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_discovery)
        filters.addWidget(QLabel("Scope"))
        filters.addWidget(self.scope_combo)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.class_filter)
        filters.addWidget(self.btn_refresh)
        self.root.addLayout(filters)

        self.count_label = QLabel("")
        self.count_label.setObjectName("Tiny")
        self.count_label.setWordWrap(True)
        self.root.addWidget(self.count_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Broker symbol", "Canonical", "Asset class", "Mapping", "Market Watch"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.open_evidence)
        self.root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.btn_view = QPushButton("View evidence")
        self.btn_view.clicked.connect(self.view_selected)
        self.btn_watch = QPushButton("Toggle Market Watch")
        self.btn_watch.clicked.connect(self.toggle_watch)
        self.btn_plan = primary("Build plan")
        self.btn_plan.clicked.connect(self.build_plan)
        actions.addWidget(self.btn_view)
        actions.addWidget(self.btn_watch)
        actions.addWidget(self.btn_plan)
        actions.addStretch(1)
        self.root.addLayout(actions)
        self.render_table()

    # --------------------------------------------------------------- helpers
    def scoped_symbols(self) -> list:
        scope = UniverseScope(self.scope_combo.currentData())
        recs = demo_data.universe()
        if scope == UniverseScope.MARKET_WATCH:
            recs = [r for r in recs if r.visible_in_market_watch]
        elif scope == UniverseScope.MAPPED:
            recs = [r for r in recs if r.mapping_source == "MT5 metadata"]
        elif scope == UniverseScope.ACTIVE_SETUPS:
            recs = [r for r in recs
                    if any(res.verdict in (Verdict.ACTIVE, Verdict.WATCHING)
                           for res in demo_data.engine_results(r.broker_symbol, "D1"))]
        q = self.search.text().strip().lower()
        if q:
            recs = [r for r in recs if q in r.broker_symbol.lower() or q in r.canonical_name.lower()]
        cls = self.class_filter.currentData()
        if cls:
            recs = [r for r in recs if r.asset_class == cls]
        return recs

    def selected_symbol(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    # ---------------------------------------------------------------- events
    def render_table(self) -> None:
        recs = self.scoped_symbols()
        self.table.setRowCount(len(recs))
        for i, r in enumerate(recs):
            it0 = QTableWidgetItem(r.broker_symbol)
            it0.setData(Qt.UserRole, r)
            self.table.setItem(i, 0, it0)
            self.table.setItem(i, 1, QTableWidgetItem(r.canonical_name))
            self.table.setItem(i, 2, QTableWidgetItem(f"{r.asset_class} · {r.family}"))
            self.table.setItem(i, 3, QTableWidgetItem(r.mapping_source))
            self.table.setItem(i, 4, QTableWidgetItem("✓ visible" if r.visible_in_market_watch else "—"))
        total = len(demo_data.universe())
        scope = UniverseScope(self.scope_combo.currentData())
        mw = sum(1 for r in demo_data.universe() if r.visible_in_market_watch)
        self.count_label.setText(
            f"Scope: {self.SCOPE_LABELS[scope]} — {len(recs)} shown of {total} broker symbols · "
            f"{mw} visible in Market Watch (scopes are never conflated)")

    def refresh_discovery(self) -> None:
        demo_data.tick()
        self.render_table()
        self.ctx.toast("Universe refreshed — scope preserved")

    def view_selected(self) -> None:
        rec = self.selected_symbol()
        if rec is None:
            self.ctx.toast("Select a market first")
            return
        self.ctx.set_active_symbol(rec)
        self.ctx.navigate("evidence")

    def open_evidence(self, item) -> None:
        rec = self.table.item(item.row(), 0).data(Qt.UserRole)
        self.ctx.set_active_symbol(rec)
        self.ctx.navigate("evidence")

    def toggle_watch(self) -> None:
        rec = self.selected_symbol()
        if rec is None:
            self.ctx.toast("Select a market first")
            return
        now_visible = demo_data.set_watch(rec.broker_symbol, not rec.visible_in_market_watch)
        self.render_table()
        self.ctx.toast(f"{rec.broker_symbol} "
                       f"{'added to' if now_visible else 'removed from'} Market Watch")

    def build_plan(self) -> None:
        rec = self.selected_symbol()
        if rec is None:
            self.ctx.toast("Select a market first")
            return
        self.ctx.set_active_symbol(rec)
        self.ctx.navigate("plans")

    def refresh(self) -> None:
        self.render_table()
