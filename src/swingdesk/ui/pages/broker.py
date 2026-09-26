"""Page: Broker & Discovery — live MT5 market data and broker contracts."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...app_globals import active_theme
from ...core import demo_data
from ..theme import mono
from ..widgets import Badge, Card, heading, page_wrapper, primary, clear_layout


class BrokerPage(QWidget):
    KEY = "broker"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Broker & Discovery",
            "MetaTrader 5 supplies live symbols, bid/ask, contracts, candles, account equity "
            "and open positions. Order execution remains disabled.",
            "Live market data"))

        conn = Card("Connection")
        self.root.addWidget(conn)
        status_row = QHBoxLayout()
        self.status_badge = Badge("CONNECTING", "gold")
        status_row.addWidget(QLabel("Status"))
        status_row.addWidget(self.status_badge)
        status_row.addStretch(1)
        conn.layout().addLayout(status_row)
        self.status_detail = QLabel("")
        self.status_detail.setWordWrap(True)
        conn.add(self.status_detail)

        actions = QHBoxLayout()
        self.btn_choose = QPushButton("Choose terminal64.exe…")
        self.btn_choose.clicked.connect(self.choose_terminal)
        self.btn_test_mt5 = QPushButton("Connect / reconnect live MT5")
        self.btn_test_mt5.clicked.connect(self.try_real_mt5)
        self.btn_refresh = primary("Refresh discovery")
        self.btn_refresh.clicked.connect(self.refresh_discovery)
        actions.addWidget(self.btn_choose)
        actions.addWidget(self.btn_test_mt5)
        actions.addStretch(1)
        actions.addWidget(self.btn_refresh)
        conn.layout().addLayout(actions)

        self.path_label = QLabel(self._path_text())
        self.path_label.setObjectName("Tiny")
        self.path_label.setWordWrap(True)
        conn.add(self.path_label)

        disc = Card("Discovery")
        self.root.addWidget(disc)
        self.disc_label = QLabel("")
        self.disc_label.setWordWrap(True)
        disc.add(self.disc_label)

        self.contract_card = Card("Selected contract")
        self.root.addWidget(self.contract_card)

        self._render_status()
        self._render_disc()
        self._render_contract()

    def _path_text(self) -> str:
        return (f"Terminal path: {self.ctx.terminal_path}" if self.ctx.terminal_path
                else "Terminal path: auto-detect. Choose terminal64.exe only if MT5 auto-detection "
                     "does not select the broker terminal you want.")

    def _render_status(self) -> None:
        if demo_data.is_live():
            info = demo_data.connection_status()
            self.status_badge.set_kind("bull", "LIVE MT5")
            server = info.get("server") or info.get("company") or "broker terminal"
            self.status_detail.setText(
                f"Connected to {info.get('terminal', 'MetaTrader 5')} · {server} · "
                f"account {info.get('login', '?')} · equity "
                f"{info.get('equity', 0):,.2f} {info.get('currency', '')}. "
                "Prices, contracts, candles, equity and positions are live. "
                "SwingDesk does not send or close broker orders in this build.")
        else:
            self.status_badge.set_kind("gold", "DEMO FALLBACK")
            detail = demo_data.last_error() or "MT5 has not connected."
            self.status_detail.setText(
                f"Live MT5 is unavailable: {detail}. SwingDesk is using the deterministic "
                "demo market-data fallback. Open and log into MT5, then reconnect here.")

    def _render_disc(self) -> None:
        recs = demo_data.universe()
        mw = sum(1 for r in recs if r.visible_in_market_watch)
        tfs = sorted({tf for r in recs for tf in r.timeframes})
        equity = demo_data.account_equity()
        self.disc_label.setText(
            f"Source: <b>{demo_data.source_label()}</b> · Universe: <b>{len(recs)}</b> symbols · "
            f"Market Watch: <b>{mw}</b> visible · timeframes: {' · '.join(tfs) or '—'} · "
            f"account equity: <span style='font-family:{mono()}'>{equity:,.2f}</span><br>"
            "Live mode reads directly from the logged-in MT5 terminal; no demo data is mixed into "
            "missing live symbols or candles.")

    def _render_contract(self) -> None:
        lay = self.contract_card.layout()
        clear_layout(lay)
        recs = demo_data.universe()
        if not recs:
            lay.addWidget(QLabel("No broker symbols discovered. Check the MT5 connection."))
            return
        wanted = self.ctx.active_symbol.broker_symbol if self.ctx.active_symbol else recs[0].broker_symbol
        rec = demo_data.symbol(wanted) or recs[0]
        lay.addWidget(QLabel(f"<b>{rec.canonical_name}</b> · broker symbol "
                             f"<span style='font-family:{mono()}'>{rec.broker_symbol}</span> · "
                             f"{rec.bid:.8g} / {rec.ask:.8g}"))
        c = rec.contract
        for label, value in (
            ("Digits / point", f"{c.digits} · {c.point}"),
            ("Tick size / value", f"{c.tick_size} · {c.tick_value}"),
            ("Volume", f"{c.volume_min} – {c.volume_max} (step {c.volume_step})"),
            ("Stops / freeze", f"{c.stops_level_points} / {c.freeze_level_points} pts"),
            ("Mapping", f"{rec.mapping_source} ({rec.mapping_confidence:.0%})"),
        ):
            row = QLabel(f"<span style='color:{active_theme().muted}'>{label}</span>&nbsp;&nbsp;"
                         f"<b style='font-family:{mono()}'>{value}</b>")
            lay.addWidget(row)

    def choose_terminal(self) -> None:
        path = self.ctx.ask_open_file(
            "Choose your broker's MetaTrader 5 terminal64.exe",
            "MetaTrader 5 (terminal64.exe terminal.exe)")
        if path:
            self.ctx.terminal_path = path
            self.ctx.set_setting("terminal_path", path)
            demo_data.configure_terminal(path)
            self.path_label.setText(self._path_text())
            self.ctx.toast("Terminal path saved — reconnecting MT5")
            self.try_real_mt5()
        else:
            self.ctx.toast("No terminal selected — existing connection unchanged")

    def try_real_mt5(self) -> None:
        if demo_data.connect_live(self.ctx.terminal_path, force=True):
            self.ctx.positions = demo_data.positions()
            self.ctx.events.positions_changed.emit()
            self.ctx.toast("Live MT5 market data connected")
        else:
            self.ctx.toast("MT5 connection failed — demo fallback remains active")
        self._render_status()
        self._render_disc()
        self._render_contract()

    def refresh_discovery(self) -> None:
        demo_data.tick()
        self._render_status()
        self._render_disc()
        self._render_contract()
        self.ctx.toast(f"Discovery refreshed from {demo_data.source_label()}")

    def refresh(self) -> None:
        self._render_status()
        self._render_disc()
        self._render_contract()
