"""Swing Desk — shared UI widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from .theme import mono, serif


class Card(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(14, 12, 14, 12)
        self._lay.setSpacing(9)
        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            self._lay.addWidget(t)

    def layout(self) -> QVBoxLayout:
        return self._lay

    def add(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def add_stretch(self) -> None:
        self._lay.addStretch(1)


def clear_layout(layout) -> None:
    """Recursively remove widgets/layouts from a Qt layout.

    Several live cards are rebuilt on every tick/form change.  Removing only
    direct widgets leaves nested QHBox/QVBox layouts (and their controls)
    attached, which caused duplicated planner stats/buttons over time.
    """
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout)
            child_layout.deleteLater()
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class Stat(QFrame):
    def __init__(self, label: str, value: str, note: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Stat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        lab = QLabel(label.upper())
        lab.setObjectName("Muted")
        lab.setStyleSheet("font-size:10px; letter-spacing:1px;")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-family:'{mono()}'; font-size:20px; font-weight:600;")
        lay.addWidget(lab)
        lay.addWidget(self.value_label)
        self.note_label = QLabel(note)
        self.note_label.setObjectName("Tiny")
        lay.addWidget(self.note_label)

    def set_value(self, v: str) -> None:
        self.value_label.setText(v)


class Badge(QLabel):
    STYLES = {
        "bull": ("bull",), "bear": ("bear",), "gold": ("gold",), "info": ("info",),
        "muted": ("muted",),
    }

    def __init__(self, text: str, kind: str = "muted", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        from .theme import THEMES
        t = THEMES["obsidian"]
        # colors are resolved at runtime from the active theme via dynamic property
        self._kind = kind
        self._text = text
        self.setProperty("kind", kind)
        self.setAlignment(Qt.AlignCenter)
        self.set_refresh()

    def set_refresh(self) -> None:
        from ..app_globals import active_theme
        t = active_theme()
        colors = {"bull": (t.bull, t.panel), "bear": (t.bear, t.panel),
                  "gold": (t.gold_bright, t.panel), "info": (t.info, t.panel),
                  "muted": (t.muted, t.panel)}
        fg, bg = colors.get(self._kind, (t.muted, t.panel))
        self.setText(self._text)
        self.setStyleSheet(
            f"color:{fg}; background:{bg}; border:1px solid {fg}; border-radius:10px;"
            f"padding:2px 8px; font-size:10px; letter-spacing:1px;")

    def set_kind(self, kind: str, text: str | None = None) -> None:
        self._kind = kind
        if text is not None:
            self._text = text
        self.set_refresh()


class EmptyState(QFrame):
    """Spec §15.6 — every page needs a real empty state with a next action."""

    def __init__(self, message: str, detail: str = "", action_text: str = "",
                 on_action=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("border:1px dashed; border-radius:12px; padding:22px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        msg = QLabel(message)
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        if detail:
            d = QLabel(detail)
            d.setObjectName("Tiny")
            d.setAlignment(Qt.AlignCenter)
            d.setWordWrap(True)
            lay.addWidget(d)
        if action_text and on_action:
            btn = QPushButton(action_text)
            btn.setObjectName("Primary")
            btn.clicked.connect(on_action)
            wrap = QHBoxLayout()
            wrap.addStretch(1); wrap.addWidget(btn); wrap.addStretch(1)
            lay.addLayout(wrap)


class Toast(QWidget):
    """In-app toast notification (§14 alert delivery)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def pop(self, message: str, ms: int = 2600) -> None:
        from .theme import THEMES
        from ..app_globals import active_theme
        t = active_theme()
        self.label.setText(message)
        self.label.setStyleSheet(
            f"background:{t.gold_fill}; color:{t.gold_text_auto};"
            f"border-radius:8px; padding:9px 15px; font-weight:600;")
        self.adjustSize()
        self.resize(max(self.width(), self.label.width() + 8), self.label.height() + 4)
        if self.parentWidget():
            pw = self.parentWidget().size()
            self.move(pw.width() - self.width() - 22, pw.height() - self.height() - 22)
        self.show()
        self.raise_()
        self._timer.start(ms)


def heading(page_title: str, subtitle: str, eyebrow: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    left = QVBoxLayout()
    eb = QLabel(eyebrow.upper())
    eb.setObjectName("Eyebrow")
    t = QLabel(page_title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("Muted")
    left.addWidget(eb); left.addWidget(t); left.addWidget(s)
    lay.addLayout(left)
    lay.addStretch(1)
    return w


def page_wrapper() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(14)
    return w, lay


def primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Primary")
    return b


def danger(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Danger")
    return b
