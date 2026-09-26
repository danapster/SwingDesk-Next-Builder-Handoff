"""Swing Desk — native candlestick chart (QPainter).

Spec §11: smooth pan/zoom, crosshair, OHLC tooltip, fit/reset, evidence
layers drawn from engine payloads, freshness timestamp. Rendering only the
visible window keeps it fast.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QMouseEvent, QPainter, QPen)
from PySide6.QtWidgets import QWidget

from ..app_globals import active_theme
from ..core.models import Bar, EvidenceLevel
from .theme import mono


class CandleChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars: list[Bar] = []
        self._layers: list[EvidenceLevel] = []
        self._symbol_label = ""
        self._timeframe = ""
        self._freshness: datetime | None = None
        self._first = 0                      # index of first visible bar
        self._count = 120                    # number of visible bars
        self._cross: QPointF | None = None
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self._pad_left, self._pad_right = 8.0, 86.0
        self._pad_top, self._pad_bottom = 14.0, 26.0

    # ------------------------------------------------------------- data api
    def set_data(self, symbol_label: str, timeframe: str, bars: list[Bar],
                 layers: list[EvidenceLevel] | None = None) -> None:
        self._symbol_label = symbol_label
        self._timeframe = timeframe
        self._bars = bars
        self._layers = layers or []
        self._freshness = datetime.now(timezone.utc)
        self._first = max(0, len(bars) - self._count)
        self.update()

    def fit(self) -> None:
        self._count = min(160, max(20, len(self._bars)))
        self._first = max(0, len(self._bars) - self._count)
        self.update()

    def watermark(self) -> str:
        from ..core import demo_data
        return f"{demo_data.source_label()} · {self._symbol_label} · {self._timeframe}"

    # -------------------------------------------------------------- helpers
    def _visible(self) -> list[Bar]:
        if not self._bars:
            return []
        self._first = max(0, min(self._first, len(self._bars) - 5))
        return self._bars[self._first:self._first + max(10, self._count)]

    def _x(self, i: int, n: int, w: float) -> float:
        span = w - self._pad_left - self._pad_right
        return self._pad_left + (i + 0.5) * span / max(1, n)

    def _price_range(self, vis: list[Bar]) -> tuple[float, float]:
        lo = min(b.low for b in vis) if vis else 0.0
        hi = max(b.high for b in vis) if vis else 1.0
        padv = (hi - lo) * 0.06 or hi * 0.001
        for lv in self._layers:
            if lv.kind == "zone" and lv.upper is not None:
                lo, hi = min(lo, lv.price - (lv.upper - lv.price)), max(hi, lv.upper)
            else:
                lo, hi = min(lo, lv.price), max(hi, lv.price)
        return lo - padv, hi + padv

    def _y(self, price: float, lo: float, hi: float, h: float) -> float:
        span = (hi - lo) or 1.0
        return self._pad_top + (h - self._pad_top - self._pad_bottom) * (1 - (price - lo) / span)

    # --------------------------------------------------------------- events
    def wheelEvent(self, e) -> None:  # noqa: N802
        if not self._bars:
            return
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        new_count = int(max(20, min(len(self._bars), self._count * factor)))
        anchor = (self._first + self._count / 2) / len(self._bars)
        self._count = new_count
        self._first = int(anchor * len(self._bars) - new_count / 2)
        self._first = max(0, min(self._first, len(self._bars) - new_count))
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self._drag_x = e.position().x()
        self._dragging = True

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self._cross = e.position()
        if getattr(self, "_dragging", False) and self._bars:
            dx = e.position().x() - self._drag_x
            n = max(10, self._count)
            span = max(1.0, self.width() - self._pad_left - self._pad_right)
            shift = int(dx / span * n)
            if shift:
                self._first = max(0, min(len(self._bars) - 10, self._first - shift))
                self._drag_x = e.position().x()
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._dragging = False

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._cross = None
        self.update()

    # ---------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802
        t = active_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(QColor(t.input))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

        if not self._bars:
            p.setPen(QColor(t.muted))
            p.drawText(self.rect(), Qt.AlignCenter, "No bars for this selection")
            p.end()
            return

        vis = self._visible()
        n = len(vis)
        lo, hi = self._price_range(vis)
        font = QFont(mono(), 8)
        p.setFont(font)

        # horizontal gridlines + price axis
        for k in range(6):
            price = lo + (hi - lo) * k / 5
            y = self._y(price, lo, hi, h)
            p.setPen(QPen(QColor(t.border), 1, Qt.DotLine))
            p.drawLine(QPointF(self._pad_left, y), QPointF(w - self._pad_right + 2, y))
            p.setPen(QPen(QColor(t.muted)))
            p.drawText(QPointF(w - self._pad_right + 8, y + 3), f"{price:.5g}")

        # evidence layers (from engine payloads only)
        for lv in self._layers:
            col = QColor(t.bull) if "DEMAND" in lv.label or "bull" in lv.label.lower() else QColor(t.gold)
            if lv.kind == "zone":
                top = self._y(lv.upper if lv.upper is not None else lv.price * 1.001, lo, hi, h)
                bot = self._y(lv.price, lo, hi, h)
                zone = QRectF(self._pad_left, top, w - self._pad_left - self._pad_right, max(2.0, bot - top))
                p.setPen(QPen(col, 1))
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 26))
                p.drawRect(zone)
                p.setPen(QPen(col))
                p.drawText(QPointF(self._pad_left + 6, top + 12), lv.label[:46])
            else:
                y = self._y(lv.price, lo, hi, h)
                p.setPen(QPen(col, 1, Qt.DashLine))
                p.drawLine(QPointF(self._pad_left, y), QPointF(w - self._pad_right + 2, y))
                p.drawText(QPointF(self._pad_left + 6, y - 4), f"{lv.label[:38]} {lv.price:.5g}")

        # candles
        cw = max(1.5, (w - self._pad_left - self._pad_right) / n * 0.62)
        for i, b in enumerate(vis):
            x = self._x(i, n, w)
            bull = b.close >= b.open
            col = QColor(t.bull if bull else t.bear)
            p.setPen(QPen(col, 1))
            yh, yl = self._y(b.high, lo, hi, h), self._y(b.low, lo, hi, h)
            p.drawLine(QPointF(x, yh), QPointF(x, yl))
            yo, yc = self._y(b.open, lo, hi, h), self._y(b.close, lo, hi, h)
            top, bh = min(yo, yc), max(1.0, abs(yc - yo))
            p.setBrush(col if not bull else QColor(col.red(), col.green(), col.blue(), 210))
            p.drawRect(QRectF(x - cw / 2, top, cw, bh))

        # crosshair + OHLC tooltip
        if self._cross is not None:
            x, y = self._cross.x(), self._cross.y()
            if self._pad_left <= x <= w - self._pad_right:
                p.setPen(QPen(QColor(t.muted), 1, Qt.DotLine))
                p.drawLine(QPointF(x, self._pad_top), QPointF(x, h - self._pad_bottom))
                p.drawLine(QPointF(self._pad_left, y), QPointF(w - self._pad_right + 2, y))
                price = lo + (1 - (y - self._pad_top) / (h - self._pad_top - self._pad_bottom)) * (hi - lo)
                p.setPen(QPen(QColor(t.gold_bright)))
                p.drawText(QPointF(w - self._pad_right + 8, y - 4), f"{price:.5g}")
                idx = int((x - self._pad_left) / (w - self._pad_left - self._pad_right) * n)
                if 0 <= idx < n:
                    b = vis[idx]
                    tip = (f"{b.time_utc:%a %d %b %H:%M}  O {b.open:.5g}  H {b.high:.5g}  "
                           f"L {b.low:.5g}  C {b.close:.5g}")
                    p.setFont(QFont(mono(), 8))
                    tw = p.fontMetrics().horizontalAdvance(tip) + 14
                    rect = QRectF(self._pad_left + 8, self._pad_top + 2, tw, 20)
                    p.setBrush(QColor(t.panel))
                    p.setPen(QPen(QColor(t.gold_fill)))
                    p.drawRoundedRect(rect, 5, 5)
                    p.setPen(QPen(QColor(t.text)))
                    p.drawText(rect, Qt.AlignCenter, tip)

        # watermark + freshness (honest demo labelling, §0.1-3)
        wm = QFont(mono(), 9)
        wm.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(wm)
        p.setPen(QColor(t.muted))
        p.drawText(QPointF(self._pad_left + 10, h - 9), self.watermark())
        p.end()
