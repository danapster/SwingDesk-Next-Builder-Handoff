"""Find the real reason order_send is rejected by probing stop distances.

Tries a spread of stop/target distances on a demo account, with and without
stops, and reports the retcode for each so the broker's actual stops-level
constraint becomes visible. Closes anything it opens.

    python tools/mt5_probe_stops.py --symbol EURUSD
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swingdesk.core import demo_data  # noqa: E402


def line(label: str, value) -> None:
    print(f"{label:<28} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--volume", type=float, default=0.01)
    ap.add_argument("--magic", type=int, default=990099)
    args = ap.parse_args()

    sys.modules.pop("pytest", None)
    if not demo_data.connect_live(force=True):
        print("Not connected:", demo_data.last_error())
        return 1

    st = demo_data.connection_status()
    line("account", f"{st.get('login')} @ {st.get('server')}")
    if "demo" not in str(st.get("server", "")).lower():
        print("REFUSING: not a demo account.")
        return 2

    provider = demo_data._LIVE
    mt5 = provider.mt5
    sym = mt5.symbol_info(args.symbol)
    if sym is None:
        print(f"Symbol {args.symbol!r} not found")
        return 1
    line("trade_stops_level", f"{sym.trade_stops_level} points")
    line("trade_freeze_level", f"{sym.trade_freeze_level} points")
    line("point / digits", f"{sym.point} / {sym.digits}")
    line("filling_mode mask", sym.filling_mode)
    line("min/vol/max/step", f"{sym.volume_min} / {sym.volume_limit} / "
                             f"{sym.volume_max} / {sym.volume_step}")
    line("trade_mode", sym.trade_mode)
    line("account trade_allowed", mt5.account_info().trade_allowed)

    tick = mt5.symbol_info_tick(args.symbol)
    d = sym.digits
    pt = sym.point
    before = {p.ticket for p in demo_data.positions()}
    line("price", f"{tick.ask} / {tick.bid}")

    cases = [
        ("no stops", None, None),
        ("10 points", 10, 10),
        ("20 points", 20, 20),
        ("50 points", 50, 50),
        ("100 points", 100, 100),
    ]

    print("\n[probe] stop-distance sweep" + "-" * 34)
    for name, sl_pts, tp_pts in cases:
        sl = round(tick.ask - sl_pts * pt, d) if sl_pts else 0.0
        tp = round(tick.ask + tp_pts * pt, d) if tp_pts else 0.0
        res = demo_data.order_send(args.symbol, "LONG", args.volume,
                                   stop=sl, target=tp, planned_entry=tick.ask,
                                   magic=args.magic, deviation_points=100,
                                   comment="SwingDesk stops probe", verify=False)
        line(name, f"retcode {res.retcode} ok={res.ok} :: {res.message}")
        if res.ok and res.ticket:
            time.sleep(0.4)
            pos = {p.ticket: p for p in demo_data.positions()}
            for t in set(pos) - before:
                p = pos[t]
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": p.broker_symbol,
                    "position": t, "volume": p.volume, "type": mt5.ORDER_TYPE_SELL,
                    "price": mt5.symbol_info_tick(p.broker_symbol).bid,
                    "deviation": 100, "magic": args.magic,
                    "comment": "probe close", "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": provider._filling_mode(sym),
                })
                time.sleep(0.3)
            before = {p.ticket for p in demo_data.positions()}

    # Also isolate: valid stops but no TP, and a plain market order request shape.
    print("\n[probe] request-shape checks" + "-" * 32)
    res = demo_data.order_send(args.symbol, "LONG", args.volume,
                               stop=round(tick.ask - 100 * pt, d), target=0.0,
                               planned_entry=tick.ask, magic=args.magic,
                               deviation_points=100, comment="probe sl only", verify=False)
    line("stop, no target", f"retcode {res.retcode} ok={res.ok} :: {res.message}")
    if res.ok and res.ticket:
        time.sleep(0.4)
        pos = {p.ticket: p for p in demo_data.positions()}
        for t in set(pos) - before:
            p = pos[t]
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "symbol": p.broker_symbol,
                "position": t, "volume": p.volume, "type": mt5.ORDER_TYPE_SELL,
                "price": mt5.symbol_info_tick(p.broker_symbol).bid,
                "deviation": 100, "magic": args.magic, "comment": "probe close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": provider._filling_mode(sym)})
        before = {p.ticket for p in demo_data.positions()}
        time.sleep(0.3)

    line("final open positions", len(demo_data.positions()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
