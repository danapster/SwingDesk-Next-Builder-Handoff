"""Generate a screenshot of every page (offscreen) into docs/screenshots/.

Also seeds a few local plans/alerts so the lifecycle board, journal and
performance pages show their real content rather than empty states.
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from swingdesk.app import MainWindow
from swingdesk.context import AppContext
from swingdesk.core import demo_data
from swingdesk.core.models import LifecycleState, Plan
from swingdesk.core.store import Store, now_iso
from swingdesk.ui.pages.alerts import price_alert_rule

OUT = pathlib.Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(exist_ok=True)


def seed(ctx: AppContext) -> None:
    rec = demo_data.symbol("EURUSD.a")
    gold = demo_data.symbol("XAUUSD.m")
    ctx.store.save_alert(price_alert_rule("EURUSD.a", "price_touch_above",
                                          round(rec.bid * 1.002, 5), "Return to D1 demand"))
    ctx.store.save_alert(price_alert_rule("XAUUSD.m", "price_touch_below",
                                          round(gold.bid * 0.998, 2), "Gold premium exit"))
    plans = [
        Plan("plan-demo-1", "EURUSD.a", "EUR / USD", "LONG", 1.0831, 1.0781, 1.0991,
             1.0, 0.20, "W1 + D1 bullish. Wait for retracement into fresh D1 demand "
             "during the New York setup window.", LifecycleState.WAITING,
             now_iso(), now_iso(), engine_snapshot="[]"),
        Plan("plan-demo-2", "XAUUSD.m", "Gold / USD", "SHORT", 2338.1, 2351.0, 2318.4,
             0.5, 0.08, "LH/LL off the daily order block; sell-side liquidity below.",
             LifecycleState.OPEN, now_iso(), now_iso(), engine_snapshot="[]"),
        Plan("plan-demo-3", "GBPJPY.m", "GBP / JPY", "LONG", 189.42, 187.9, 193.82,
             1.0, 0.20, "Sweep of Asian low + London reversal.", LifecycleState.REVIEW,
             now_iso(), now_iso(), engine_snapshot="[]", actual_fill=189.51,
             realised_r=2.4, behaviour_flags=["Followed plan"], review_completed=True,
             review_note="Textbook London sweep; held to TP2 as planned.",
             closed_at=now_iso()),
    ]
    for p in plans:
        ctx.store.save_plan(p)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    store = Store(pathlib.Path(os.environ.get("SWINGDESK_SHOT_DB", OUT / "shots.db")))
    ctx = AppContext(store)
    win = MainWindow(ctx)
    win.resize(1440, 900)
    seed(ctx)
    ctx.events.plans_changed.emit()
    ctx.events.alerts_changed.emit()

    from swingdesk.ui.pages import LABELS
    for key in LABELS:
        win.navigate(key)
        app.processEvents()
        pix = win.grab()
        path = OUT / f"{key}.png"
        pix.save(str(path))
        print("saved", path.name, pix.width(), "x", pix.height())
    win.close()
    win.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
