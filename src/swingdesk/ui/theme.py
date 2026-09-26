"""Swing Desk — theme system.

Three themes from the handoff's theme-tokens.json (Obsidian, Paper, Terminal),
three densities, and the orbiting brand-frame light implemented natively in
QPainter as the production plan requires (§15.1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, QTimer, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QPainter, QPen,
                           QFont, QFontDatabase)
from PySide6.QtWidgets import QSizePolicy, QWidget

_TOKENS_PATH = (Path(__file__).resolve().parents[3] / "build" / "assets" / "theme-tokens.json")

_FALLBACK_TOKENS = {
    "obsidian": {"bg": "#08090B", "panel": "#111318", "panelAlt": "#17191F",
                 "input": "#0A0B0E", "border": "#292C33", "text": "#ECE9E2",
                 "muted": "#8D9098", "gold": "#C9A96A", "goldBright": "#E3C88D",
                 "goldFill": "#B49359", "bull": "#71C79A", "bear": "#DF7777"},
    "paper": {"bg": "#F7F3EC", "panel": "#EFEBE3", "panelAlt": "#E6E1D6",
              "input": "#FBF9F4", "border": "#D6CFC1", "text": "#23211E",
              "muted": "#6D685E", "gold": "#9C7A35", "goldBright": "#7D5F22",
              "goldFill": "#A8853D", "bull": "#3D8560", "bear": "#B45555"},
    "terminal": {"bg": "#000000", "panel": "#0B0B0B", "panelAlt": "#161616",
                 "input": "#000000", "border": "#333333", "text": "#FFFFFF",
                 "muted": "#999999", "gold": "#FFFFFF", "goldBright": "#FFFFFF",
                 "goldFill": "#FFFFFF", "bull": "#86D6A9", "bear": "#E58B8B"},
}


def _load_tokens() -> dict:
    try:
        return json.loads(_TOKENS_PATH.read_text())
    except Exception:
        return _FALLBACK_TOKENS


_TOKENS = _load_tokens()


@dataclass
class Theme:
    key: str
    label: str
    bg: str
    panel: str
    panel_alt: str
    input: str
    border: str
    text: str
    muted: str
    gold: str
    gold_bright: str
    gold_fill: str
    gold_text: str
    bull: str
    bear: str
    info: str = "#7CA9C9"

    @property
    def gold_text_auto(self) -> str:
        return "#050505" if self.key != "paper" else "#FBF9F4"


def _theme_from_tokens(key: str, label: str, t: dict) -> Theme:
    return Theme(key=key, label=label, bg=t["bg"], panel=t["panel"], panel_alt=t["panelAlt"],
                 input=t["input"], border=t["border"], text=t["text"], muted=t["muted"],
                 gold=t["gold"], gold_bright=t.get("goldBright", t["gold"]),
                 gold_fill=t.get("goldFill", t["gold"]), gold_text="",
                 bull=t.get("bull", "#71C79A"), bear=t.get("bear", "#DF7777"))


_OBS = _TOKENS.get("obsidian", {})
_PAP = _TOKENS.get("paper", {})
_TRM = _TOKENS.get("terminal", {})

THEMES: dict[str, Theme] = {
    "obsidian": _theme_from_tokens("obsidian", "Obsidian · default", _OBS),
    "paper": _theme_from_tokens("paper", "Paper · daylight", _PAP),
    "terminal": _theme_from_tokens("terminal", "Terminal · monochrome", _TRM),
}

DENSITIES = {
    "comfort": {"pad": 14, "gap": 12, "row": 8, "font_delta": 1},
    "compact": {"pad": 10, "gap": 9, "row": 6, "font_delta": 0},
    "terminal": {"pad": 7, "gap": 6, "row": 4, "font_delta": -1},
}


def serif() -> str:
    for fam in ("Georgia", "Times New Roman", "Liberation Serif", "DejaVu Serif", "serif"):
        if fam in QFontDatabase.families() or fam == "serif":
            return fam
    return "serif"


def mono() -> str:
    for fam in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "monospace"):
        if fam in QFontDatabase.families() or fam == "monospace":
            return fam
    return "monospace"


def build_qss(theme: Theme, density_key: str = "compact") -> str:
    d = DENSITIES[density_key]
    serif_fam = serif()
    return f"""
    QWidget {{ background: {theme.bg}; color: {theme.text};
               font-family: "Segoe UI", "Inter", Arial, sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {theme.bg}; }}

    QLabel#PageTitle {{ font-family: "{serif_fam}"; font-size: 26px; }}
    QLabel#CardTitle {{ font-family: "{serif_fam}"; font-size: 16px; }}
    QLabel#Eyebrow {{ color: {theme.gold}; font-size: 10px; letter-spacing: 2px; }}
    QLabel#Muted, QLabel#Tiny {{ color: {theme.muted}; }}
    QLabel#Tiny {{ font-size: 11px; }}
    QLabel#Mono {{ font-family: "{mono()}"; }}

    QFrame#Card, QFrame#Stat {{ background: {theme.panel}; border: 1px solid {theme.border};
                                 border-radius: 12px; }}
    QFrame#Card {{ padding: {d['pad']}px; }}
    QFrame#Stat {{ padding: {d['row'] + 2}px; }}

    QPushButton {{ background: {theme.panel_alt}; color: {theme.text};
                   border: 1px solid {theme.border}; border-radius: 8px;
                   padding: {d['row']}px 13px; }}
    QPushButton:hover {{ border-color: {theme.gold}; }}
    QPushButton:focus {{ border: 1px solid {theme.gold}; }}
    QPushButton:disabled {{ color: {theme.muted}; border-color: {theme.border}; }}
    QPushButton#Primary {{ background: {theme.gold_fill}; color: {theme.gold_text_auto};
                            border: 1px solid {theme.gold_fill}; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {theme.gold_bright}; }}
    QPushButton#Danger {{ color: {theme.bear}; }}
    QPushButton#NavLink {{ background: transparent; border: none; border-radius: 8px;
                            text-align: left; color: {theme.muted};
                            padding: {d['row']}px 12px; font-size: 13px; }}
    QPushButton#NavLink:hover {{ color: {theme.gold_bright}; background: {theme.panel_alt}; }}
    QPushButton#NavLink[active="true"] {{ color: {theme.gold_bright};
                                           background: {theme.panel_alt};
                                           font-weight: 600; }}

    QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit, QSpinBox {{
        background: {theme.input}; color: {theme.text};
        border: 1px solid {theme.border}; border-radius: 8px;
        padding: {d['row']}px 10px; selection-background-color: {theme.gold_fill}; }}
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
        border-color: {theme.gold}; }}
    QComboBox QAbstractItemView {{ background: {theme.panel}; color: {theme.text};
                                    border: 1px solid {theme.border};
                                    selection-background-color: {theme.gold_fill};
                                    selection-color: {theme.gold_text_auto}; }}

    QTableWidget {{ background: {theme.panel}; border: 1px solid {theme.border};
                    border-radius: 12px; gridline-color: {theme.border};
                    selection-background-color: {theme.panel_alt}; }}
    QHeaderView::section {{ background: {theme.panel_alt}; color: {theme.muted};
                             border: none; border-bottom: 1px solid {theme.border};
                             padding: 7px; font-size: 11px; }}
    QTableWidget::item {{ padding: 6px; }}

    QTabBar::tab {{ background: transparent; color: {theme.muted}; padding: 7px 15px;
                    border: 1px solid transparent; border-radius: 8px; }}
    QTabBar::tab:selected {{ color: {theme.gold_bright}; border-color: {theme.gold};
                              background: {theme.panel_alt}; }}

    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {theme.border}; border-radius: 4px;
                                    min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {theme.gold_fill}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {theme.border}; border-radius: 4px;
                                      min-width: 30px; }}

    QToolTip {{ background: {theme.panel}; color: {theme.text};
                border: 1px solid {theme.gold_fill}; padding: 6px; }}

    QCheckBox {{ spacing: 8px; color: {theme.text}; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {theme.border};
                             border-radius: 4px; background: {theme.input}; }}
    QCheckBox::indicator:checked {{ background: {theme.gold_fill};
                                     border-color: {theme.gold_fill}; }}

    QProgressBar {{ background: {theme.input}; border: 1px solid {theme.border};
                     border-radius: 4px; text-align: center; color: {theme.muted};
                     font-size: 10px; height: 8px; }}
    QProgressBar::chunk {{ background: {theme.gold_fill}; border-radius: 3px; }}
    """


class OrbitBrand(QWidget):
    """The orbiting conic-gradient brand frame, painted natively (§15.1)."""

    def __init__(self, child: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self._inner = child
        self.setAttribute(Qt.WA_StyledBackground, False)
        # A custom-painted QWidget has no useful sizeHint by default.  In the
        # sidebar QVBoxLayout that allowed the brand to collapse to a tiny
        # strip even though its child contained visible labels.
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        child.setParent(self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:  # noqa: N802
        inner = self._inner.sizeHint()
        return QSize(max(180, inner.width() + 10), max(72, inner.height() + 10))

    def start(self, fps: int = 30) -> None:
        self._timer.start(1000 // fps)

    def stop(self) -> None:
        self._timer.stop()

    def _step(self) -> None:
        self._angle = (self._angle + 1.4) % 360.0
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        m = 5
        self._inner.setGeometry(self.rect().adjusted(m, m, -m, -m))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        theme = THEMES.get(getattr(self, "theme_key", "obsidian"), THEMES["obsidian"])
        r = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        grad = QConicalGradient(r.center(), -self._angle)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.62, QColor(0, 0, 0, 0))
        grad.setColorAt(0.82, QColor(theme.gold))
        grad.setColorAt(0.94, QColor("#FFF6DC"))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        pen = QPen(QBrush(grad), 1.6)
        p.setPen(pen)
        p.drawRoundedRect(r, 14, 14)
        p.end()
