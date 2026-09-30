"""List open positions/orders with their magic and comment, and optionally
close only Swing Desk probe leftovers (magic 990099).

    python tools/mt5_probe_cleanup.py            # report only
    python tools/mt5_probe_cleanup.py --close    # close probe leftovers
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swingdesk.core import demo_data  # noqa: E402

PROBE_MAGIC = 990099


def line(label: str, value) -> None:
    print(f"{label:<28} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--close", action="store_true", help="close probe positions")
    args = ap.parse_args()

    sys.modules.pop("pytest", None)
    if not demo_data.connect_live(force=True):
        print("Not connected:", demo_data.last_error())
        return 1

    st = demo_data.connection_status()
    line("account", f"{st.get('login')} @ {st.get('server')}")
    provider = demo_data._LIVE
    mt5 = provider.mt5

    positions = list(mt5.positions_get() or ())
    orders = list(mt5.orders_get() or ())
    history = list(mt5.history_deals_get() or ())

    print(f"\nopen positions: {len(positions)}")
    for p in positions:
        probe = int(p.magic) == PROBE_MAGIC
        line(f"  #{p.ticket}",
             f"{'PROBE' if probe else 'yours'} {p.symbol} vol={p.volume} "
             f"@ {p.price_open} sl={p.sl} tp={p.tp} magic={p.magic} "
             f"comment={p.comment!r} profit={p.profit}")

    print(f"\nopen pending orders: {len(orders)}")
    for o in orders:
        probe = int(o.magic) == PROBE_MAGIC
        line(f"  #{o.ticket}",
             f"{'PROBE' if probe else 'yours'} {o.symbol} vol={o.volume} "
             f"@ {o.price_open} magic={o.magic} state={o.state} comment={o.comment!r}")

    mine = [p for p in positions if int(p.magic) == PROBE_MAGIC]
    if not mine:
        print("\nNo probe positions left to clean up.")
    elif not args.close:
        print(f"\n{len(mine)} probe position(s) present. Re-run with --close to remove them.")
    else:
        print(f"\nclosing {len(mine)} probe position(s)")
        for p in mine:
            tick = mt5.symbol_info_tick(p.symbol)
            is_buy = int(p.type) == int(mt5.POSITION_TYPE_BUY)
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "position": p.ticket,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if is_buy else tick.ask,
                "deviation": 100,
                "magic": p.magic,
                "comment": "probe cleanup",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": provider._filling_mode(mt5.symbol_info(p.symbol)),
            })
            time.sleep(0.5)
            line(f"  close #{p.ticket}",
                 f"retcode {res.retcode} — {provider._describe_retcode(res.retcode)}")
        line("positions remaining", len(mt5.positions_get() or ()))

    if history:
        line("\ndeals in history", len(history))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
