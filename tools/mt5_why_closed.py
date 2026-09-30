"""Explain a 10016 'market is closed' rejection: stale feed or real closure?

    python tools/mt5_why_closed.py --symbol EURUSD
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swingdesk.core import demo_data  # noqa: E402


def line(label: str, value) -> None:
    print(f"{label:<26} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    args = ap.parse_args()

    sys.modules.pop("pytest", None)
    if not demo_data.connect_live(force=True):
        print("Not connected:", demo_data.last_error())
        return 1

    provider = demo_data._LIVE
    mt5 = provider.mt5
    info = mt5.account_info()
    line("server time (broker)", dt.datetime.fromtimestamp(
        info.server_time if hasattr(info, "server_time") else 0).strftime("%Y-%m-%d %H:%M:%S"))
    line("local machine time", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    line("utc now", dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    tick = mt5.symbol_info_tick(args.symbol)
    if tick is None:
        line("tick", "NONE — no quotes at all")
    else:
        t = dt.datetime.fromtimestamp(tick.time)
        age = (dt.datetime.utcnow() - t).total_seconds()
        line("tick time", t.strftime("%Y-%m-%d %H:%M:%S"))
        line("tick age (seconds)", f"{age:,.0f}")
        line("bid / ask", f"{tick.bid} / {tick.ask}")
        if age > 900:
            print("\n  => STALE FEED. The quote is over 15 minutes old.")
            print("     The server has no live prices, so it reports the market")
            print("     as closed. This is a data/entitlement problem, not a")
            print("     closed market: check the terminal's Market Watch and")
            print("     Tools > Options > Expert Advisors / Server > Add symbol.")
        else:
            print("\n  => Feed is live. The closure is a real trading session break.")

    sym = mt5.symbol_info(args.symbol)
    if sym is not None:
        modes = {0: "DISABLED", 1: "LONGONLY", 2: "SHORTONLY", 3: "CLOSEONLY", 4: "FULL"}
        line("trade_mode", f"{sym.trade_mode} ({modes.get(sym.trade_mode, '?')})")
        line("visible in Market Watch", sym.visible)
        for attr in ("session_buy", "session_sell"):
            s = getattr(sym, attr, None)
            if s is not None:
                line(attr, f"quotes={s.quotes} trade={s.trade} "
                           f"quote_from={dt.datetime.fromtimestamp(s.quote_from):%H:%M} "
                           f"quote_to={dt.datetime.fromtimestamp(s.quote_to):%H:%M} "
                           f"trade_from={dt.datetime.fromtimestamp(s.trade_from):%H:%M} "
                           f"trade_to={dt.datetime.fromtimestamp(s.trade_to):%H:%M}")

    line("open positions", len(mt5.positions_get() or ()))
    line("account trade_allowed", getattr(info, "trade_allowed", "?"))
    print("\nNo order was placed by this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
