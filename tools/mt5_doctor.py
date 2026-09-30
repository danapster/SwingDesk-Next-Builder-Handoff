"""Diagnose the Swing Desk → MetaTrader 5 connection.

Read-only. Reports whether the terminal is reachable, whether the account may
trade, which filling modes and order types are permitted, and what the live
provider actually sees. Run this before trusting the Order_Send button:

    python tools/mt5_doctor.py
    python tools/mt5_doctor.py --symbol EURUSD --volume 0.10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swingdesk.core import demo_data  # noqa: E402
from swingdesk.core.models import ContractSpec  # noqa: E402


def line(label: str, value) -> None:
    print(f"{label:<26} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="", help="broker symbol to inspect, e.g. EURUSD.a")
    ap.add_argument("--volume", type=float, default=0.10)
    ap.add_argument("--terminal", default="", help="path to terminal64.exe")
    args = ap.parse_args()

    print("Swing Desk MT5 doctor — read-only diagnostics\n" + "-" * 52)

    if args.terminal:
        demo_data.configure_terminal(args.terminal)

    # Never let the test/self-test demo switch hijack the diagnostic.
    sys.modules.pop("pytest", None)
    connected = demo_data.connect_live(force=True)
    line("connected", connected)
    if not connected:
        line("error", demo_data.last_error() or "unknown")
        print("\nFix the above first — Order_Send will refuse to run until this connects.")
        return 1

    status = demo_data.connection_status()
    for key in ("terminal", "company", "server", "login", "currency", "balance", "equity"):
        line(key, status.get(key, ""))

    provider = getattr(demo_data, "_LIVE", None)
    mt5 = getattr(provider, "mt5", None)
    account = mt5.account_info() if mt5 else None
    if account is not None:
        line("trade_allowed", getattr(account, "trade_allowed", "?"))
        line("trade_expert", getattr(account, "trade_expert", "?"))

    if args.symbol:
        symbol = args.symbol
    else:
        recs = demo_data.universe()
        if not recs:
            print("\nNo symbols returned by the terminal — Market Watch may be empty.")
            return 1
        symbol = recs[0].broker_symbol
    line("inspecting symbol", symbol)

    rec = demo_data.symbol(symbol)
    if rec is None:
        line("symbol_info", "NOT FOUND — check the exact broker name")
        return 1
    c: ContractSpec = rec.contract
    line("digits / point", f"{c.digits} / {c.point}")
    line("tick size / value", f"{c.tick_size} / {c.tick_value}")
    line("volume min/max/step", f"{c.volume_min} / {c.volume_max} / {c.volume_step}")
    line("stops level (points)", c.stops_level_points)
    line("freeze level (points)", c.freeze_level_points)
    line("trade_mode", c.trade_mode)
    line("filling_mode (mask)", c.filling_mode)
    line("bid / ask", f"{rec.bid} / {rec.ask}")
    if rec.bid == 0.0 or rec.ask == 0.0:
        print("\nNo live prices — the symbol is probably outside trading hours.")

    if mt5 is not None:
        info = mt5.symbol_info(symbol)
        mask = int(getattr(info, "filling_mode", 0) or 0) if info else 0
        chosen = provider._filling_mode(info) if info else None
        line("resolved request filling", chosen)
        names = []
        if mask & 1:
            names.append("FOK")
        if mask & 2:
            names.append("IOC")
        if mask & 4:
            names.append("RETURN")
        line("filling allowed by symbol", ", ".join(names) or "none reported")
        line("open positions", len(demo_data.positions()))

    print("\nDispatch constants present: " + ", ".join(
        n for n in ("TRADE_ACTION_DEAL", "ORDER_TYPE_BUY", "ORDER_TYPE_SELL",
                    "ORDER_FILLING_FOK", "ORDER_FILLING_IOC", "TRADE_RETCODE_DONE")
        if mt5 is not None and hasattr(mt5, n)))
    print("\nNo order was placed. Use the Order_Send button in Swing Desk to trade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
