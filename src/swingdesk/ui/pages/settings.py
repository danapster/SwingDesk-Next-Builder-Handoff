"""Page: Settings — deliberately small personalization surface (§15.5-12)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ...ui.theme import DENSITIES, THEMES
from ..widgets import Card, heading, page_wrapper, primary


class SettingsPage(QWidget):
    KEY = "settings"

    def __init__(self, ctx) -> None:
        super().__init__()
        w, self.root = page_wrapper()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)
        self.ctx = ctx

        self.root.addWidget(heading(
            "Settings",
            "A deliberately small personalization surface. Everything is stored locally.",
            "Theme · density · policy"))

        # appearance
        appearance = Card("Appearance")
        self.root.addWidget(appearance)
        self.theme_combo = QComboBox()
        for key, t in THEMES.items():
            self.theme_combo.addItem(t.label, key)
        self.theme_combo.setCurrentText(THEMES[ctx.setting("theme")].label
                                        if ctx.setting("theme") in THEMES else THEMES["obsidian"].label)
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.density_combo = QComboBox()
        for key, d in DENSITIES.items():
            self.density_combo.addItem(key.capitalize(), key)
        self.density_combo.setCurrentIndex(
            list(DENSITIES).index(ctx.setting("density")) if ctx.setting("density") in DENSITIES else 1)
        self.density_combo.currentIndexChanged.connect(self.change_density)
        self.orbit_check = QCheckBox("Brand orbit animation")
        self.orbit_check.setChecked(ctx.setting("orbit_animation") != "0")
        self.orbit_check.toggled.connect(self.toggle_orbit)
        for lab, wid in (("Theme", self.theme_combo), ("Density", self.density_combo)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lab))
            row.addStretch(1)
            row.addWidget(wid, 1)
            appearance.layout().addLayout(row)
        appearance.layout().addWidget(self.orbit_check)

        # risk & time
        risk_card = Card("Risk & time")
        self.root.addWidget(risk_card)
        self.default_risk = QDoubleSpinBox()
        self.default_risk.setDecimals(2)
        self.default_risk.setRange(0.1, 100.0)
        self.default_risk.setValue(float(ctx.setting("default_risk") or 1.0))
        self.start_page = QComboBox()
        from . import LABELS
        for key, label in LABELS.items():
            self.start_page.addItem(label, key)
        self.start_page.setCurrentIndex(
            max(0, list(LABELS).index(ctx.setting("start_page")))
            if ctx.setting("start_page") in LABELS else 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Default risk %"))
        row.addStretch(1)
        row.addWidget(self.default_risk, 1)
        risk_card.layout().addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Start page"))
        row.addStretch(1)
        row.addWidget(self.start_page, 1)
        risk_card.layout().addLayout(row)

        # macro policy
        macro = Card("Macro policy provider")
        self.root.addWidget(macro)
        provider = QLabel(
            "<b>Trading Economics</b> · policy-rate snapshot for USD, EUR, GBP, JPY, "
            "CHF, CAD, AUD, NZD and ZAR. The Calendar & Macro page reads only the "
            "local policy_rates.json cache.")
        provider.setWordWrap(True)
        macro.add(provider)
        self.macro_status = QLabel("")
        self.macro_status.setObjectName("Tiny")
        self.macro_status.setWordWrap(True)
        macro.add(self.macro_status)
        hint = QLabel(
            "API key setup (PowerShell, once): "
            "[Environment]::SetEnvironmentVariable('SWINGDESK_TE_API_KEY','YOUR_KEY','User') "
            "then restart SwingDesk.")
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        macro.add(hint)
        self.btn_macro_refresh = QPushButton("Test & refresh policy rates")
        self.btn_macro_refresh.clicked.connect(self.refresh_macro_policy)
        macro.add(self.btn_macro_refresh)
        self._render_macro_status()

        # diagnostics
        diag = Card("Diagnostics")
        self.root.addWidget(diag)
        from ...core.store import data_dir
        diag.add(QLabel(f"Local data: {data_dir()}"))
        self.btn_diagnostics = QPushButton("Export diagnostics")
        self.btn_diagnostics.clicked.connect(self.export_diagnostics)
        diag.add(self.btn_diagnostics)

        self.btn_save = primary("Save settings")
        self.btn_save.clicked.connect(self.save_settings)
        self.root.addWidget(self.btn_save)
        self.root.addStretch(1)

    # ---------------------------------------------------------------- actions
    def change_theme(self) -> None:
        key = self.theme_combo.currentData()
        self.ctx.apply_theme(key)

    def change_density(self) -> None:
        key = self.density_combo.currentData()
        self.ctx.apply_density(key)

    def toggle_orbit(self, on: bool) -> None:
        self.ctx.set_setting("orbit_animation", "1" if on else "0")
        if self.ctx.window is not None:
            self.ctx.window.set_orbit_enabled(on)

    def save_settings(self) -> None:
        self.ctx.set_setting("theme", self.theme_combo.currentData())
        self.ctx.set_setting("density", self.density_combo.currentData())
        self.ctx.set_setting("default_risk", f"{self.default_risk.value():.2f}")
        self.ctx.set_setting("start_page", self.start_page.currentData())
        self.ctx.set_setting("orbit_animation", "1" if self.orbit_check.isChecked() else "0")
        self.ctx.toast("Settings saved locally")

    def _render_macro_status(self) -> None:
        from ...core.macro_policy import shared_macro_policy_cache
        status = shared_macro_policy_cache().status()
        key = "detected" if status.api_key_configured else "NOT DETECTED"
        downloaded = status.last_download or "never"
        error = f" · last error: {status.last_error}" if status.last_error else ""
        self.macro_status.setText(
            f"API key: {key} · local cache: {status.path} · "
            f"{status.rate_count} rates · last download: {downloaded}{error}")

    def refresh_macro_policy(self) -> None:
        from ...core.macro_policy import shared_macro_policy_cache
        cache = shared_macro_policy_cache()
        if not cache.status().api_key_configured:
            self.ctx.toast(
                "Set SWINGDESK_TE_API_KEY as a Windows user environment variable, "
                "restart SwingDesk, then try again")
            self._render_macro_status()
            return
        _changed, message = cache.refresh(force=True)
        self._render_macro_status()
        self.ctx.toast(message)

    def export_diagnostics(self) -> None:
        import json
        from ...core import demo_data
        from ...core.store import data_dir
        info = {
            "app": "Swing Desk", "mode": demo_data.source_label(),
            "universe_symbols": len(demo_data.universe()),
            "mt5": demo_data.connection_status(),
            "calendar_cache": str(demo_data.calendar_cache_status().path),
            "macro_policy_cache": __import__(
                "swingdesk.core.macro_policy", fromlist=["shared_macro_policy_cache"]
            ).shared_macro_policy_cache().status().__dict__,
            "database": str(self.ctx.store.path),
            "data_dir": str(data_dir()),
            "settings": {k: self.ctx.setting(k) for k in
                         ("theme", "density", "default_risk", "start_page",
                          "orbit_animation", "terminal_path")},
        }
        path = self.ctx.exports_dir() / "diagnostics.json"
        path.write_text(json.dumps(info, indent=2), encoding="utf-8")
        self.ctx.toast(f"Diagnostics exported → {path}")

    def refresh(self) -> None:
        self._render_macro_status()
