"""Page: Broker & Discovery — connection, terminal chooser, contracts (§15.5-11)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ...app_globals import active_theme
from ...core import demo_data
from ...core.models import UniverseScope
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
            "MT5 supplies the universe, contracts, sessions and validation rules. "
            "Discovery, never assumption.",
            "Connection"))

        # connection card
        conn = Card("Connection")
        self.root.addWidget(conn)
        status_row = QHBoxLayout()
        self.status_badge = Badge("DEMO ADAPTER", "gold")
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
        self.btn_refresh = primary("Refresh discovery")
        self.btn_refresh.clicked.connect(self.refresh_discovery)
        self.btn_test_mt5 = QPushButton("Try real MT5 (Windows)")
        self.btn_test_mt5.clicked.connect(self.try_real_mt5)
        actions.addWidget(self.btn_choose)
        actions.addWidget(self.btn_test_mt5)
        actions.addStretch(1)
        actions.addWidget(self.btn_refresh)
        conn.layout().addLayout(actions)
        self.path_label = QLabel(self._path_text())
        self.path_label.setObjectName("Tiny")
        self.path_label.setWordWrap(True)
        conn.add(self.path_label)

        # discovery card
        disc = Card("Discovery")
        self.root.addWidget(disc)
        self.disc_label = QLabel("")
        self.disc_label.setWordWrap(True)
        disc.add(self.disc_label)

        # contract card
        self.contract_card = Card("Selected contract")
        self.root.addWidget(self.contract_card)

        self._render_disc()
        self._render_contract()

    # ---------------------------------------------------------------- helpers
    def _path_text(self) -> str:
        return (f"Terminal path: {self.ctx.terminal_path}" if self.ctx.terminal_path
                else "Terminal path: not set — the MT5 bridge is optional; the app stays "
                     "fully usable in local/demo mode (§1.1 graceful degradation).")

    def _render_disc(self) -> None:
        recs = demo_data.universe()
        mw = sum(1 for r in recs if r.visible_in_market_watch)
        tfs = sorted({tf for r in recs for tf in r.timeframes})
        self.disc_label.setText(
            f"Universe: <b>{len(recs)}</b> symbols · Market Watch: <b>{mw}</b> visible · "
            f"timeframes: {' · '.join(tfs)} · account equity (demo): "
            f"<span style='font-family:{mono()}'>{demo_data.account_equity():,.0f}</span><br>"
            "Scopes are separate and visible everywhere the universe is shown.")

    def _render_contract(self) -> None:
        lay = self.contract_card.layout()
        clear_layout(lay)
        rec = self.ctx.active_symbol or demo_data.universe()[0]
        lay.addWidget(QLabel(f"<b>{rec.canonical_name}</b> · broker symbol "
                             f"<span style='font-family:{mono()}'>{rec.broker_symbol}</span>"))
        c = rec.contract
        for label, value in (("Digits / point", f"{c.digits} · {c.point}"),
                             ("Tick size / value", f"{c.tick_size} · {c.tick_value}"),
                             ("Volume", f"{c.volume_min} – {c.volume_max} (step {c.volume_step})"),
                             ("Stops / freeze", f"{c.stops_level_points} / {c.freeze_level_points} pts"),
                             ("Mapping", f"{rec.mapping_source} ({rec.mapping_confidence:.0%})")):
            row = QLabel(f"<span style='color:{active_theme().muted}'>{label}</span>&nbsp;&nbsp;"
                         f"<b style='font-family:{mono()}'>{value}</b>")
            lay.addWidget(row)

    # ---------------------------------------------------------------- actions
    def choose_terminal(self) -> None:
        path = self.ctx.ask_open_file("Choose your broker's MetaTrader 5 terminal64.exe",
                                      "MetaTrader 5 (terminal64.exe terminal.exe)")
        if path:
            self.ctx.terminal_path = path
            self.ctx.set_setting("terminal_path", path)
            self.path_label.setText(self._path_text())
            self.ctx.toast("Terminal path saved")
        else:
            self.ctx.toast("No terminal selected — local mode continues")

    def refresh_discovery(self) -> None:
        self._render_disc()
        self._render_contract()
        self.ctx.toast("Discovery refreshed from demo adapter")

    def try_real_mt5(self) -> None:
        """Probe a real MT5 terminal without changing the active data adapter.

        Until the bridge is implemented, a successful probe proves terminal
        reachability only.  Market data throughout Swing Desk remains the
        deterministic demo adapter and the UI must say so explicitly.
        """
        try:
            import MetaTrader5 as mt5  # type: ignore
        except Exception as exc:  # not installed, or not Windows
            self.status_badge.set_kind("muted", "MT5 UNAVAILABLE")
            self.status_detail.setText(
                f"The MetaTrader5 package is not available here ({type(exc).__name__}). "
                "Precise action: install the package on your Windows machine "
                "(pip install MetaTrader5) and open your broker's MT5 terminal and log in. "
                "Until then Swing Desk runs in local/demo mode — planning, journal and "
                "performance features remain fully available.")
            self.ctx.toast("MT5 package unavailable — staying in demo mode")
            return
        # Package exists: attempt initialize (this is the real integration point).
        initialized = False
        try:
            ok = mt5.initialize(self.ctx.terminal_path or None)
            initialized = bool(ok)
            if ok:
                info = mt5.terminal_info()
                acc = mt5.account_info()
                self.status_badge.set_kind("gold", "MT5 PROBE OK · DEMO ACTIVE")
                self.status_detail.setText(
                    f"Terminal reachable: {getattr(info, 'name', 'terminal')} · "
                    f"account {getattr(acc, 'login', '?')} · "
                    f"balance {getattr(acc, 'balance', 0):,.2f} {getattr(acc, 'currency', '')}. "
                    "This is a connectivity probe only: Swing Desk is still using DEMO data "
                    "for prices, discovery, contracts and positions until the MT5 bridge is wired.")
                self.ctx.toast("MT5 terminal reachable — Swing Desk remains in demo mode")
            else:
                self.status_badge.set_kind("bear", "NOT LOGGED IN")
                self.status_detail.setText(
                    "MT5 package present but initialize() failed. Precise action: open your "
                    "broker's MT5 terminal and log in, then retry the MT5 probe. "
                    "Swing Desk remains in demo mode.")
        except Exception as exc:
            self.status_badge.set_kind("bear", "ERROR")
            self.status_detail.setText(
                f"MT5 initialize raised {type(exc).__name__}: {exc}. Swing Desk remains in demo mode.")
        finally:
            if initialized:
                try:
                    mt5.shutdown()
                except Exception:
                    pass

    def refresh(self) -> None:
        self._render_disc()
        self._render_contract()
