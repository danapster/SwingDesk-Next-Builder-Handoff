"""End-to-end dispatch probe: place a real order, track it, then close it.

Intended for DEMO accounts only. It places a minimum-size order, reports the
exact retcode, confirms whether the ticket actually appears in the account, and
then removes the position so no stray trade is left behind.

    python tools/mt5_probe_order.py --symbol EURUSD
    python tools/mt5_probe_order.py --symbol EURUSD --keep   # do not close
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swingdesk.core import demo_data  # noqa: E402


def line(label: str, value) -> None:
    print(f"{label:<24} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--volume", type=float, default=0.01)
    ap.add_argument("--magic", type=int, default=990099)
    ap.add_argument("--keep", action="store_true", help="do not close the position")
    args = ap.parse_args()

    sys.modules.pop("pytest", None)
    if not demo_data.connect_live(force=True):
        print("Not connected:", demo_data.last_error())
        return 1

    status = demo_data.connection_status()
    line("account", f"{status.get('login')} @ {status.get('server')}")
    line("balance", status.get("balance"))
    if "demo" not in str(status.get("server", "")).lower():
        print("\nREFUSING: this account does not look like a demo account.")
        print("Re-run against a demo terminal, or pass an explicit demo symbol.")
        return 2
    print("\n[probe] placing a real order to observe the full dispatch path\n" + "-" * 52)

    rec = demo_data.symbol(args.symbol)
    if rec is None:
        print(f"Symbol {args.symbol!r} not found. Try the exact broker name.")
        return 1

    is_buy = True
    price = rec.ask if is_buy else rec.bid
    digits = rec.contract.digits
    # 20 points of room keeps stops clear of the 14-point stops level.
    sl = round(price - 20 * rec.contract.point, digits)
    tp = round(price + 20 * rec.contract.point, digits)
    line("symbol", rec.broker_symbol)
    line("side", "BUY" if is_buy else "SELL")
    line("volume", args.volume)
    line("price / sl / tp", f"{price} / {sl} / {tp}")

    before = {p.ticket for p in demo_data.positions()}
    line("positions before", len(before))

    result = demo_data.order_send(
        rec.broker_symbol, "LONG" if is_buy else "SHORT", args.volume,
        stop=sl, target=tp, planned_entry=price,
        magic=args.magic, deviation_points=50, comment="SwingDesk probe")

    line("ok", result.ok)
    line("retcode", result.retcode)
    line("message", result.message)
    line("order_ticket", result.order_ticket)
    line("deal_ticket", result.deal_ticket)
    line("position_ticket", result.position_ticket)
    line("verified", result.verified)
    line("fill price", result.price)

    provider = demo_data._LIVE
    mt5 = provider.mt5
    line("last_error()", mt5.last_error() if mt5 else "-")

    print("\n[probe] account state after the send" + "-" * 30)
    live_orders = mt5.orders_get(symbol=rec.broker_symbol) if mt5 else ()
    live_positions = mt5.positions_get(symbol=rec.broker_symbol) if mt5 else ()
    line("orders_get", len(live_orders or ()))
    line("positions_get", len(live_positions or ()))
    for p in (live_positions or ()):
        line("  position", f"#{p.ticket} {p.type} {p.volume} @ {p.price_open} "
                           f"magic={p.magic} sl={p.sl} tp={p.tp} comment={p.comment!r}")
    for o in (live_orders or ()):
        line("  order", f"#{o.ticket} {o.type} {o.volume} @ {o.price_open} "
                        f"magic={o.magic} state={o.state} comment={o.comment!r}")

    after = {p.ticket: p for p in demo_data.positions()}
    new = set(after) - before
    line("new tickets detected", sorted(new) or "none")

    if not args.keep and new:
        print("\n[probe] closing the probe position" + "-" * 30)
        for ticket in new:
            p = after[ticket]
            close = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.broker_symbol,
                "position": ticket,
                "volume": p.volume,
                "type": (mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY),
                "price": (mt5.symbol_info_tick(p.broker_symbol).bid if is_buy
                          else mt5.symbol_info_tick(p.broker_symbol).ask),
                "deviation": 50,
                "magic": args.magic,
                "comment": "SwingDesk probe close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": provider._filling_mode(mt5.symbol_info(p.broker_symbol)),
            }
            res = mt5.order_send(close)
            time.sleep(0.4)
            line(f"close #{ticket}", f"retcode {res.retcode} {provider._describe_retcode(res.retcode)}")
        line("positions after", len(demo_data.positions()))
    elif args.keep:
        print("\n[probe] --keep given; position left open deliberately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
