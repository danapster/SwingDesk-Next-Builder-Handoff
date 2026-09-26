"""Live MetaTrader 5 market-data provider.

This provider is intentionally read-only: it supplies broker discovery, ticks,
contract metadata, candles, account equity and open positions. It does not send,
modify or close orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib
import os
import time

from . import engines
from .models import Bar, ContractSpec, Direction, EngineResult, Position, SymbolRecord, Verdict

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
        if any(x in up for x in ("US30", "USTEC", "NAS", "SPX", "GER40", "DE40",
                                  "UK100", "JP225", "DJ", "DAX")):
            return "CFD", "Index CFDs"
        if base and profit and len(base) == 3 and len(profit) == 3:
            if base in _MAJOR and profit in _MAJOR:
                if "USD" in (base, profit):
                    return "FX", "FX majors"
                return "FX", "FX crosses"
            return "FX", "FX exotics"
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
            out: list[Bar] = []
            for r in rates or ():
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
