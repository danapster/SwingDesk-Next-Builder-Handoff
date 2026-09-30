"""Live MetaTrader 5 provider.

Read-only market data (broker discovery, ticks, contract metadata, candles,
account equity, open positions) plus one guarded write path: `order_send`,
which places a market order and verifies the ticket is actually listed.

Dispatch is deliberately hard to trigger by accident — the UI gates it behind
order_check plus an explicit confirmation, and the provider itself refuses
unverified sends (§10.3).
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib
import math
import os
import time

from . import engines
from .models import (Bar, ContractSpec, Direction, EngineResult, OrderResult,
                     Position, SymbolRecord, Verdict)

TF_ATTRS = {
    "M15": "TIMEFRAME_M15",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
}

_MAJOR = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
_METALS = {"XAU": "Gold", "XAG": "Silver", "XPT": "Platinum", "XPD": "Palladium"}


class MT5LiveProvider:
    def __init__(self) -> None:
        self.mt5 = None
        self.connected = False
        self.terminal_path = ""
        self.last_error = ""
        self._engines: dict[tuple[str, str], tuple[float, list[EngineResult]]] = {}

    def connect(self, terminal_path: str = "") -> bool:
        self.last_error = ""
        try:
            mt5 = importlib.import_module("MetaTrader5")
        except Exception as exc:
            self.last_error = f"MetaTrader5 package unavailable: {type(exc).__name__}: {exc}"
            self.connected = False
            return False

        try:
            path = (terminal_path or "").strip()
            ok = mt5.initialize(path) if path else mt5.initialize()
            if not ok:
                err = getattr(mt5, "last_error", lambda: ("?", "initialize failed"))()
                self.last_error = f"MT5 initialize failed: {err}"
                self.connected = False
                return False
            info = mt5.terminal_info()
            account = mt5.account_info()
            if info is None or account is None:
                self.last_error = "MT5 initialized but terminal/account information is unavailable"
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                self.connected = False
                return False
            self.mt5 = mt5
            self.connected = True
            self.terminal_path = path
            return True
        except Exception as exc:
            self.last_error = f"MT5 connect error: {type(exc).__name__}: {exc}"
            self.connected = False
            return False

    def shutdown(self) -> None:
        if self.mt5 is not None and self.connected:
            try:
                self.mt5.shutdown()
            except Exception:
                pass
        self.connected = False

    def connection_info(self) -> dict:
        if not self.connected or self.mt5 is None:
            return {}
        try:
            ti = self.mt5.terminal_info()
            ai = self.mt5.account_info()
            if ti is None or ai is None:
                return {}
            return {
                "connected": True,
                "terminal": getattr(ti, "name", "MetaTrader 5"),
                "company": getattr(ti, "company", ""),
                "server": getattr(ai, "server", ""),
                "login": getattr(ai, "login", ""),
                "currency": getattr(ai, "currency", ""),
                "balance": float(getattr(ai, "balance", 0.0) or 0.0),
                "equity": float(getattr(ai, "equity", 0.0) or 0.0),
            }
        except Exception:
            return {}

    @staticmethod
    def _currency_parts(info) -> tuple[str, str]:
        base = str(getattr(info, "currency_base", "") or "").upper().strip()
        profit = str(getattr(info, "currency_profit", "") or "").upper().strip()
        name = str(getattr(info, "name", "") or "").upper()
        letters = "".join(ch for ch in name if ch.isalpha())
        if not base and len(letters) >= 6:
            base = letters[:3]
        if not profit and len(letters) >= 6:
            profit = letters[3:6]
        return base, profit

    @staticmethod
    def _classify(name: str, base: str, profit: str) -> tuple[str, str]:
        up = name.upper()
        if base in _METALS or up.startswith(tuple(_METALS)):
            return "CFD", "Metals"
        if "BTC" in up or "ETH" in up or "CRYPTO" in up:
            return "CFD", "Crypto"
        # A six-letter stem carrying 3+3 currency metadata is a spot FX pair, and
        # that has to be settled before the index heuristics below.  "DJ" is the
        # Dow's token and "USDJPY" contains it, so every yen pair was being filed
        # as an index CFD — which then gave it an index-sized stop buffer.
        stem = up.split(".", 1)[0]
        letters = "".join(ch for ch in stem if ch.isalpha())
        if (len(letters) == 6 and stem.isalpha() and base and profit
                and len(base) == 3 and len(profit) == 3):
            if base in _MAJOR and profit in _MAJOR:
                if "USD" in (base, profit):
                    return "FX", "FX majors"
                return "FX", "FX crosses"
            return "FX", "FX exotics"
        if any(x in up for x in ("US30", "USTEC", "NAS", "SPX", "GER40", "DE40",
                                  "UK100", "JP225", "DJ", "DAX")):
            return "CFD", "Index CFDs"
        return "CFD", "Broker CFDs"

    @staticmethod
    def _canonical(name: str, base: str, profit: str) -> str:
        if base in _METALS and profit:
            return f"{_METALS[base]} / {profit}"
        if base and profit:
            return f"{base} / {profit}"
        return name

    def _record(self, info, tick=None) -> SymbolRecord:
        base, profit = self._currency_parts(info)
        asset_class, family = self._classify(str(info.name), base, profit)
        point = float(getattr(info, "point", 0.0) or 0.0)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or point)
        tick_value = float(
            getattr(info, "trade_tick_value", 0.0)
            or getattr(info, "trade_tick_value_profit", 0.0)
            or 0.0
        )
        spec = ContractSpec(
            digits=int(getattr(info, "digits", 0) or 0),
            point=point,
            tick_size=tick_size,
            tick_value=tick_value,
            contract_size=float(getattr(info, "trade_contract_size", 0.0) or 0.0),
            volume_min=float(getattr(info, "volume_min", 0.0) or 0.0),
            volume_max=float(getattr(info, "volume_max", 0.0) or 0.0),
            volume_step=float(getattr(info, "volume_step", 0.0) or 0.0),
            stops_level_points=int(getattr(info, "trade_stops_level", 0) or 0),
            freeze_level_points=int(getattr(info, "trade_freeze_level", 0) or 0),
            trade_mode=str(getattr(info, "trade_mode", "")),
            filling_mode=str(getattr(info, "filling_mode", "")),
        )
        if tick is None and self.mt5 is not None:
            try:
                tick = self.mt5.symbol_info_tick(info.name)
            except Exception:
                tick = None
        bid = float(getattr(tick, "bid", 0.0) or 0.0) if tick is not None else 0.0
        ask = float(getattr(tick, "ask", 0.0) or 0.0) if tick is not None else 0.0
        return SymbolRecord(
            broker_symbol=str(info.name),
            canonical_name=self._canonical(str(info.name), base, profit),
            family=family,
            asset_class=asset_class,
            base_currency=base,
            profit_currency=profit,
            mapping_source="MT5 metadata",
            mapping_confidence=1.0,
            visible_in_market_watch=bool(getattr(info, "visible", False)),
            contract=spec,
            bid=bid,
            ask=ask,
            timeframes=tuple(TF_ATTRS),
        )

    def universe(self) -> list[SymbolRecord]:
        if not self.connected or self.mt5 is None:
            return []
        try:
            infos = self.mt5.symbols_get() or ()
            return [self._record(info) for info in infos]
        except Exception as exc:
            self.last_error = f"MT5 symbols_get failed: {type(exc).__name__}: {exc}"
            return []

    def symbol(self, broker_symbol: str) -> SymbolRecord | None:
        if not self.connected or self.mt5 is None:
            return None
        try:
            info = self.mt5.symbol_info(broker_symbol)
            if info is None:
                return None
            return self._record(info, self.mt5.symbol_info_tick(broker_symbol))
        except Exception as exc:
            self.last_error = f"MT5 symbol lookup failed: {type(exc).__name__}: {exc}"
            return None

    def set_watch(self, broker_symbol: str, visible: bool) -> bool:
        if not self.connected or self.mt5 is None:
            return False
        try:
            return bool(self.mt5.symbol_select(broker_symbol, bool(visible)))
        except Exception as exc:
            self.last_error = f"MT5 symbol_select failed: {type(exc).__name__}: {exc}"
            return False

    def bars(self, broker_symbol: str, timeframe: str, count: int = 420) -> list[Bar]:
        if not self.connected or self.mt5 is None:
            return []
        attr = TF_ATTRS.get(timeframe)
        if not attr or not hasattr(self.mt5, attr):
            return []
        try:
            rates = self.mt5.copy_rates_from_pos(
                broker_symbol, getattr(self.mt5, attr), 0, int(count))
            if rates is None or len(rates) == 0:
                try:
                    self.mt5.symbol_select(broker_symbol, True)
                    rates = self.mt5.copy_rates_from_pos(
                        broker_symbol, getattr(self.mt5, attr), 0, int(count))
                except Exception:
                    pass
            if rates is None:
                return []
            out: list[Bar] = []
            for r in rates:
                def val(key, default=0):
                    try:
                        return r[key]
                    except Exception:
                        return getattr(r, key, default)
                out.append(Bar(
                    time_utc=datetime.fromtimestamp(float(val("time")), tz=timezone.utc),
                    open=float(val("open")),
                    high=float(val("high")),
                    low=float(val("low")),
                    close=float(val("close")),
                    tick_volume=int(val("tick_volume", 0) or 0),
                    spread=int(val("spread", 0) or 0),
                    real_volume=int(val("real_volume", 0) or 0),
                ))
            return out
        except Exception as exc:
            self.last_error = f"MT5 rates failed for {broker_symbol}: {type(exc).__name__}: {exc}"
            return []

    def engine_results(self, broker_symbol: str, timeframe: str) -> list[EngineResult]:
        key = (broker_symbol, timeframe)
        cached = self._engines.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < 10.0:
            return cached[1]
        result = engines.run_all_engines(self.bars(broker_symbol, timeframe))
        self._engines[key] = (now, result)
        return result

    def tick(self) -> None:
        self._engines.clear()

    def account_equity(self) -> float:
        if not self.connected or self.mt5 is None:
            return 0.0
        try:
            ai = self.mt5.account_info()
            return float(getattr(ai, "equity", 0.0) or 0.0) if ai is not None else 0.0
        except Exception:
            return 0.0

    def positions(self) -> list[Position]:
        if not self.connected or self.mt5 is None:
            return []
        try:
            raw = self.mt5.positions_get() or ()
            buy_type = getattr(self.mt5, "POSITION_TYPE_BUY", 0)
            result: list[Position] = []
            for p in raw:
                rec = self.symbol(str(p.symbol))
                canonical = rec.canonical_name if rec is not None else str(p.symbol)
                direction = "LONG" if getattr(p, "type", buy_type) == buy_type else "SHORT"
                result.append(Position(
                    ticket=int(getattr(p, "ticket", 0) or 0),
                    broker_symbol=str(getattr(p, "symbol", "")),
                    canonical_name=canonical,
                    direction=direction,
                    volume=float(getattr(p, "volume", 0.0) or 0.0),
                    entry=float(getattr(p, "price_open", 0.0) or 0.0),
                    stop=float(getattr(p, "sl", 0.0) or 0.0),
                    take_profit=float(getattr(p, "tp", 0.0) or 0.0),
                    current_price=float(getattr(p, "price_current", 0.0) or 0.0),
                    profit=float(getattr(p, "profit", 0.0) or 0.0),
                ))
            return result
        except Exception as exc:
            self.last_error = f"MT5 positions_get failed: {type(exc).__name__}: {exc}"
            return []

    def _filling_mode(self, info) -> int:
        """Pick a request filling mode the symbol actually accepts.

        The symbol advertises a bitmask (SYMBOL_FILLING_FOK=1, IOC=2, BOC=4)
        while the request wants the matching ORDER_FILLING_* constant.  Sending
        a hard-coded mode is the classic cause of retcode 10061
        "Invalid filling mode", so derive it from the symbol instead.
        """
        mask = int(getattr(info, "filling_mode", 0) or 0)
        if mask & 1:
            return int(self.mt5.ORDER_FILLING_FOK)
        if mask & 2:
            return int(self.mt5.ORDER_FILLING_IOC)
        if mask & 4:
            return int(getattr(self.mt5, "ORDER_FILLING_RETURN", 2))
        return int(getattr(self.mt5, "ORDER_FILLING_IOC", 1))

    @staticmethod
    def _norm_price(value: float, digits: int) -> float:
        return round(float(value), int(digits))

    @staticmethod
    def _norm_volume(volume: float, step: float, vmin: float, vmax: float) -> float:
        step = step if step and step > 0 else 0.01
        v = math.floor(round(float(volume) / step, 9)) * step
        return min(max(v, vmin if vmin > 0 else step), vmax if vmax > 0 else v)

    def _retcode_name(self, retcode: int) -> str:
        """Authoritative retcode label read from the MT5 module itself."""
        mt5 = self.mt5
        if mt5 is not None:
            for attr in dir(mt5):
                if attr.startswith("TRADE_RETCODE_") and \
                        int(getattr(mt5, attr, -1)) == int(retcode):
                    return attr[len("TRADE_RETCODE_"):].lower().replace("_", " ")
        return "unknown"

    def _describe_retcode(self, retcode: int) -> str:
        """Explain a rejection.

        Codes are keyed off the MT5 module's own constants rather than hard-coded
        numbers: the literal 10016 is INVALID_STOPS, not "market closed", and
        guessing here previously misreported why a dispatch was refused.
        """
        mt5 = self.mt5

        def code(name: str) -> int:
            return int(getattr(mt5, name, -999)) if mt5 is not None else -999

        hints = {
            code("TRADE_RETCODE_REQUOTE"): "price changed — the quote moved away",
            code("TRADE_RETCODE_REJECT"): "order refused by the broker",
            code("TRADE_RETCODE_CANCEL"): "order cancelled",
            code("TRADE_RETCODE_PLACED"): "accepted as a pending order",
            code("TRADE_RETCODE_DONE"): "done",
            code("TRADE_RETCODE_DONE_PARTIAL"): "partially filled",
            code("TRADE_RETCODE_ERROR"): "generic trade server error",
            code("TRADE_RETCODE_TIMEOUT"): "trade server timeout",
            code("TRADE_RETCODE_INVALID"): "invalid request",
            code("TRADE_RETCODE_INVALID_VOLUME"): "invalid volume for this symbol",
            code("TRADE_RETCODE_INVALID_PRICE"): "invalid price for this symbol",
            code("TRADE_RETCODE_INVALID_STOPS"):
                "invalid stops — stop/target is inside the broker stops level "
                "or on the wrong side of the market",
            code("TRADE_RETCODE_TRADE_DISABLED"):
                "trading is disabled for this symbol",
            code("TRADE_RETCODE_MARKET_CLOSED"):
                "market is closed for this symbol right now",
            code("TRADE_RETCODE_NO_MONEY"): "not enough free margin",
            code("TRADE_RETCODE_PRICE_CHANGED"): "price changed",
            code("TRADE_RETCODE_PRICE_OFF"): "no quotes / price unavailable",
            code("TRADE_RETCODE_INVALID_EXPIRATION"): "invalid expiry",
            code("TRADE_RETCODE_ORDER_CHANGED"): "order state changed",
            code("TRADE_RETCODE_TOO_MANY_REQUESTS"): "too many requests — slow down",
            code("TRADE_RETCODE_NO_CHANGES"): "no changes to apply",
            code("TRADE_RETCODE_LOCKED"): "account is locked for trading",
            code("TRADE_RETCODE_FROZEN"): "account is frozen",
            code("TRADE_RETCODE_INVALID_FILL"): "invalid filling mode",
            code("TRADE_RETCODE_CONNECTION"): "no connection to the trade server",
            code("TRADE_RETCODE_LIMIT_VOLUME"): "volume exceeds the account limit",
            code("TRADE_RETCODE_MARKET_BUSY"): "market is busy",
        }
        name = self._retcode_name(retcode)
        hint = hints.get(int(retcode))
        if hint is None:
            return f"{name} ({retcode})"
        return f"{name} ({retcode}) — {hint}"

    def _find_ticket(self, symbol: str, magic: int, order_ticket: int):
        """Locate the dispatched order in live orders or open positions."""
        for getter in ("positions_get", "orders_get"):
            try:
                rows = getattr(self.mt5, getter)(symbol=symbol) or ()
            except Exception:
                rows = ()
            for r in rows:
                if order_ticket and int(getattr(r, "ticket", 0) or 0) == order_ticket:
                    return int(getattr(r, "ticket", 0) or 0)
                if int(getattr(r, "magic", 0) or 0) == magic and \
                        str(getattr(r, "symbol", "")) == symbol:
                    return int(getattr(r, "ticket", 0) or 0)
        return 0

    def _preflight_order(self, request: dict) -> tuple[bool, str]:
        """Run the broker's own order_check before sending anything.

        SwingDesk's local `risk.order_check` trusts the symbol's advertised
        stops level, but a broker's real limit is often stricter (observed on
        OctaFX-Demo: advertised 14 points, server enforced >20). Only the
        server knows the true constraint, so ask it directly.
        """
        mt5 = self.mt5
        if not hasattr(mt5, "order_check"):
            return True, ""
        try:
            res = mt5.order_check(request)
        except Exception as exc:
            return True, f"order_check unavailable ({type(exc).__name__}: {exc})"
        if res is None:
            err = ""
            try:
                err = mt5.last_error()
            except Exception:
                pass
            return True, f"order_check returned None (last_error={err})"
        retcode = int(getattr(res, "retcode", 0) or 0)
        if retcode == 0:
            return True, ""
        comment = str(getattr(res, "comment", "") or "")
        return False, f"broker order_check {self._describe_retcode(retcode)}" + (
            f": {comment}" if comment else "")

    def order_send(self, symbol: str, direction: str, volume: float,
                   stop: float = 0.0, target: float = 0.0,
                   planned_entry: float = 0.0, magic: int = 20260101,
                   deviation_points: int = 20, comment: str = "SwingDesk",
                   verify: bool = True) -> OrderResult:
        """Place one market order and confirm it is actually listed.

        The UI must never claim a send succeeded on the strength of a return
        value alone: the ticket is looked up in the account afterwards and
        `verified` is only set when the broker lists it.
        """
        if not self.connected or self.mt5 is None:
            return OrderResult(False, -1, self.last_error or "MT5 is not connected")

        direction = (direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return OrderResult(False, -1, f"Unsupported direction {direction!r}")

        try:
            info = self.mt5.symbol_info(symbol)
        except Exception as exc:
            return OrderResult(False, -1, f"symbol_info failed: {type(exc).__name__}: {exc}")
        if info is None:
            return OrderResult(False, -1, f"Unknown symbol {symbol!r}")

        try:
            tick = self.mt5.symbol_info_tick(symbol)
        except Exception as exc:
            return OrderResult(False, -1, f"symbol_info_tick failed: {type(exc).__name__}: {exc}")
        if tick is None:
            return OrderResult(False, -1, f"No tick for {symbol} — market may be closed")

        digits = int(getattr(info, "digits", 0) or 0)
        vol = self._norm_volume(volume,
                                float(getattr(info, "volume_step", 0.01) or 0.01),
                                float(getattr(info, "volume_min", 0.01) or 0.01),
                                float(getattr(info, "volume_max", 100.0) or 100.0))
        is_buy = direction == "LONG"
        price = self._norm_price(tick.ask if is_buy else tick.bid, digits)
        sl = self._norm_price(stop, digits) if stop else 0.0
        tp = self._norm_price(target, digits) if target else 0.0

        if is_buy and sl and sl >= price:
            return OrderResult(False, -1, "Stop loss must sit below the market for a LONG")
        if is_buy and tp and tp <= price:
            return OrderResult(False, -1, "Take profit must sit above the market for a LONG")
        if not is_buy and sl and sl <= price:
            return OrderResult(False, -1, "Stop loss must sit above the market for a SHORT")
        if not is_buy and tp and tp >= price:
            return OrderResult(False, -1, "Take profit must sit below the market for a SHORT")

        # Side alone is not enough. The market moves between planning and
        # sending, and a stop that is still on the correct side can end up
        # closer to the fill than the broker's stops level allows, which comes
        # back as retcode 10016 rather than anything the planner could have
        # warned about.
        stops_level = float(getattr(info, "trade_stops_level", 0) or 0) * float(
            getattr(info, "point", 0.0) or 0.0)
        if sl and abs(price - sl) < stops_level:
            self.last_error = (f"Order blocked — stop loss is "
                               f"{abs(price - sl):.5g} from the market, inside the broker "
                               f"stops level ({abs(stops_level):.5g}). Re-derive levels "
                               f"from the current price.")
            return OrderResult(False, -1, self.last_error, symbol, direction, vol,
                               price, sl, tp, planned_entry=planned_entry)
        if tp and abs(price - tp) < stops_level:
            self.last_error = (f"Order blocked — take profit is "
                               f"{abs(price - tp):.5g} from the market, inside the broker "
                               f"stops level ({abs(stops_level):.5g}). Re-derive levels "
                               f"from the current price.")
            return OrderResult(False, -1, self.last_error, symbol, direction, vol,
                               price, sl, tp, planned_entry=planned_entry)

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol,
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": int(deviation_points),
            "magic": int(magic),
            "comment": str(comment)[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(info),
        }

        # Ask the broker to validate before committing: its real stops level is
        # frequently stricter than the value advertised in symbol_info.
        passed, why = self._preflight_order(request)
        if not passed:
            self.last_error = f"Order blocked before sending — {why}"
            return OrderResult(False, -1, self.last_error, symbol, direction, vol,
                               price, sl, tp, planned_entry=planned_entry)

        try:
            result = self.mt5.order_send(request)
        except Exception as exc:
            self.last_error = f"MT5 order_send raised: {type(exc).__name__}: {exc}"
            return OrderResult(False, -1, self.last_error)

        if result is None:
            err = ""
            try:
                err = self.mt5.last_error()
            except Exception:
                pass
            self.last_error = f"order_send returned None (last_error={err})"
            return OrderResult(False, -1, self.last_error, symbol, direction, vol,
                               price, sl, tp, planned_entry=planned_entry)

        retcode = int(getattr(result, "retcode", -1))
        order_ticket = int(getattr(result, "order", 0) or 0)
        deal_ticket = int(getattr(result, "deal", 0) or 0)
        accepted = retcode in (
            int(getattr(self.mt5, "TRADE_RETCODE_DONE", 10009)),
            int(getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
            int(getattr(self.mt5, "TRADE_RETCODE_PLACED", 10008)),
        )
        if not accepted:
            self.last_error = f"order rejected — retcode {retcode}: {self._describe_retcode(retcode)}"
            return OrderResult(False, retcode, self.last_error, symbol, direction, vol,
                               price, sl, tp, order_ticket, deal_ticket,
                               planned_entry=planned_entry)

        # Accepted by the server is not the same as listed on the account.
        ticket = 0
        if verify:
            for _ in range(6):
                ticket = self._find_ticket(symbol, magic, order_ticket)
                if ticket:
                    break
                time.sleep(0.25)
        if ticket == 0 and order_ticket:
            ticket = order_ticket

        message = f"ticket {ticket or order_ticket} — {self._describe_retcode(retcode)}"
        if verify and not ticket:
            message = (f"broker accepted the order (retcode {retcode}) but the ticket was "
                       "not found in open orders or positions — check the MT5 terminal")
        self.last_error = ""
        return OrderResult(True, retcode, message, symbol, direction, vol, price, sl, tp,
                           order_ticket, deal_ticket, ticket, bool(ticket),
                           planned_entry=planned_entry)

    def opportunity_rows(self) -> list[dict]:
        rows = []
        visible = [r for r in self.universe() if r.visible_in_market_watch]
        limit = max(1, int(os.environ.get("SWINGDESK_SCAN_LIMIT", "120")))
        for rec in visible[:limit]:
            results = self.engine_results(rec.broker_symbol, "D1")
            active = [r for r in results if r.verdict in (Verdict.ACTIVE, Verdict.WATCHING)]
            aligned = [r for r in active if r.direction in (Direction.LONG, Direction.SHORT)]
            if not aligned:
                continue
            long_votes = sum(r.strength for r in aligned if r.direction == Direction.LONG)
            short_votes = sum(r.strength for r in aligned if r.direction == Direction.SHORT)
            total = long_votes + short_votes
            if total <= 0:
                continue
            rows.append({
                "record": rec,
                "direction": "LONG" if long_votes >= short_votes else "SHORT",
                "strength": max(long_votes, short_votes) / total,
                "scorecard": engines.scorecard(results),
                "results": results,
                "why": " · ".join(r.reasons[0].text for r in active[:3] if r.reasons),
            })
        rows.sort(key=lambda r: r["strength"], reverse=True)
        return rows
