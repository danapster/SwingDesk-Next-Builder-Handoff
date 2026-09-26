"""Swing Desk — demo data adapter.

The production plan requires the app to open and stay useful when MT5 is
unavailable. This adapter provides a deterministic, clearly-labelled demo
universe: symbols, contracts, bars, positions and calendar events. It
implements the same surface the MT5 bridge will expose, so pages never
special-case the source.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .models import (AlertRule, Bar, CalendarEvent, ContractSpec, Direction,
                     EngineResult, Position, SymbolRecord, Verdict)
from . import engines

TF_MINUTES = {"M15": 15, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080}

# broker_symbol -> (canonical, family, asset_class, base, profit, visible, digits, point,
#                   tick_value, contract, seed, price)
_UNIVERSE: list[tuple] = [
    ("EURUSD.a",  "EUR / USD",   "FX majors",    "FX",   "EUR", "USD", True,  5, 0.00001, 1.0,     100000, 11, 1.0842),
    ("GBPUSD.a",  "GBP / USD",   "FX majors",    "FX",   "GBP", "USD", True,  5, 0.00001, 1.0,     100000, 21, 1.2673),
    ("USDJPY.a",  "USD / JPY",   "FX majors",    "FX",   "USD", "JPY", True,  3, 0.001,   6.7,     100000, 31, 151.24),
    ("AUDUSD.a",  "AUD / USD",   "FX majors",    "FX",   "AUD", "USD", True,  5, 0.00001, 1.0,     100000, 41, 0.6584),
    ("USDZAR.a",  "USD / ZAR",   "FX exotics",   "FX",   "USD", "ZAR", True,  5, 0.00001, 18.5,    100000, 51, 17.6120),
    ("EURJPY.a",  "EUR / JPY",   "FX crosses",   "FX",   "EUR", "JPY", False, 3, 0.001,   6.7,     100000, 61, 164.19),
    ("GBPJPY.m",  "GBP / JPY",   "FX crosses",   "FX",   "GBP", "JPY", True,  3, 0.001,   6.7,     100000, 71, 191.68),
    ("XAUUSD.m",  "Gold / USD",  "Metals",       "CFD",  "XAU", "USD", True,  2, 0.01,    1.0,     100,    81, 2325.40),
    ("XAGUSD.m",  "Silver / USD","Metals",       "CFD",  "XAG", "USD", False, 3, 0.001,   50.0,    5000,   91, 27.310),
    ("US30.cash", "Dow / USD",   "Index CFDs",   "CFD",  "US30","USD", True,  1, 0.1,     0.1,     1,      101, 39214.0),
    ("USTEC.cash","Nasdaq / USD","Index CFDs",   "CFD",  "USTEC","USD",True,  1, 0.1,     0.1,     1,      111, 17842.5),
    ("GER40.cash","DAX / EUR",   "Index CFDs",   "CFD",  "GER40","EUR",True,  1, 0.1,     0.11,    1,      121, 18230.6),
    ("UK100.cash","FTSE / GBP",  "Index CFDs",   "CFD",  "UK100","GBP",False,1, 0.1,     0.13,    1,      131, 8142.0),
    ("BTCUSD.a",  "Bitcoin / USD","Crypto",      "CFD",  "BTC", "USD", True,  2, 0.01,    1.0,     1,      141, 63128.0),
    ("ETHUSD.a",  "Ethereum / USD","Crypto",     "CFD",  "ETH", "USD", False, 2, 0.01,   1.0,     1,      151, 3085.4),
    ("USDMXN.a",  "USD / MXN",   "FX exotics",   "FX",   "USD", "MXN", False, 5, 0.00001, 17.2,    100000, 161, 17.054),
    ("NZDUSD.a",  "NZD / USD",   "FX majors",    "FX",   "NZD", "USD", False, 5, 0.00001, 1.0,     100000, 171, 0.5991),
    ("USDCHF.a",  "USD / CHF",   "FX majors",    "FX",   "USD", "CHF", False, 5, 0.00001, 1.12,    100000, 181, 0.9042),
    ("XPTUSD.m",  "Platinum / USD","Metals",     "CFD",  "XPT", "USD", False, 2, 0.01,   1.0,     100,    191, 961.20),
    ("JP225.cash","Nikkei / JPY","Index CFDs",   "CFD",  "JP225","JPY",False, 1, 0.1,    0.65,    1,      201, 38460.0),
]

_SYMBOLS: dict[str, SymbolRecord] = {}
_BARS: dict[tuple[str, str], list[Bar]] = {}
_ENGINES: dict[tuple[str, str], list[EngineResult]] = {}
_ACCOUNT_EQUITY = 10_000.0


def _build_symbol(row: tuple) -> SymbolRecord:
    (bs, canon, fam, ac, base, profit, visible, digits, point,
     tick_value, contract, _seed, price) = row
    spread = point * (4 if ac == "FX" else 2)
    return SymbolRecord(
        broker_symbol=bs, canonical_name=canon, family=fam, asset_class=ac,
        base_currency=base, profit_currency=profit,
        mapping_source="MT5 metadata" if not bs[0].isdigit() and ".a" in bs else "Alias table",
        mapping_confidence=0.93 if ".a" in bs else 0.86,
        visible_in_market_watch=visible,
        contract=ContractSpec(
            digits=digits, point=point, tick_size=point, tick_value=tick_value,
            contract_size=contract, volume_min=0.01, volume_max=100.0,
            volume_step=0.01, stops_level_points=20, freeze_level_points=0),
        bid=price - spread / 2, ask=price + spread / 2,
        timeframes=("M15", "H1", "H4", "D1", "W1"))


def universe() -> list[SymbolRecord]:
    if not _SYMBOLS:
        for row in _UNIVERSE:
            _SYMBOLS[row[0]] = _build_symbol(row)
    return list(_SYMBOLS.values())


def symbol(broker_symbol: str) -> SymbolRecord | None:
    universe()
    return _SYMBOLS.get(broker_symbol)


def bars(broker_symbol: str, timeframe: str, count: int = 420) -> list[Bar]:
    key = (broker_symbol, timeframe)
    if key in _BARS:
        return _BARS[key]
    rec = symbol(broker_symbol)
    if rec is None or timeframe not in TF_MINUTES:
        return []
    rnd = random.Random(hash(key) & 0xFFFFFFFF)
    step = TF_MINUTES[timeframe]
    # anchor the last bar to a fixed UTC moment for determinism
    now = datetime(2026, 3, 6, 16, 0, tzinfo=timezone.utc)
    n = max(0, math.floor(60 / (step / 60)) if step >= 60 else 60)
    now = now.replace(minute=0, second=0)
    scale = rec.bid * (0.010 if rec.asset_class == "FX" else 0.024)
    price = rec.bid * (1 - 0.004)
    out: list[Bar] = []
    for i in range(count):
        drift = math.sin(i / 26.0) * scale * 0.12 + math.sin(i / 7.0) * scale * 0.05
        o = price
        c = o + drift + rnd.gauss(0, scale * 0.10)
        hi = max(o, c) + abs(rnd.gauss(0, scale * 0.06))
        lo = min(o, c) - abs(rnd.gauss(0, scale * 0.06))
        t = now - timedelta(minutes=step * (count - i))
        out.append(Bar(time_utc=t, open=o, high=hi, low=lo, close=c,
                       tick_volume=rnd.randint(400, 9000), spread=12))
        price = c
    _BARS[key] = out
    return out


def engine_results(broker_symbol: str, timeframe: str) -> list[EngineResult]:
    key = (broker_symbol, timeframe)
    if key not in _ENGINES:
        _ENGINES[key] = engines.run_all_engines(bars(broker_symbol, timeframe))
    return _ENGINES[key]


def set_watch(broker_symbol: str, visible: bool) -> bool:
    """Enable/disable a broker symbol in Market Watch (symbol_select parity)."""
    universe()
    rec = _SYMBOLS.get(broker_symbol)
    if rec is None:
        return False
    _SYMBOLS[broker_symbol] = SymbolRecord(
        **{**rec.__dict__, "visible_in_market_watch": visible})
    return visible


def tick() -> None:
    """Advance demo prices a small deterministic-random step."""
    universe()
    for bs, rec in list(_SYMBOLS.items()):
        rnd = random.Random(hash((bs, rec.bid)) & 0xFFFF)
        step = rec.bid * 0.0004 * (rnd.random() - 0.45)
        _SYMBOLS[bs] = SymbolRecord(
            **{**rec.__dict__, "bid": rec.bid + step, "ask": rec.ask + step})


def positions() -> list[Position]:
    universe()
    gbp = _SYMBOLS["GBPJPY.m"]; gold = _SYMBOLS["XAUUSD.m"]
    return [
        Position(700512, "GBPJPY.m", "GBP / JPY", "LONG", 0.20, 189.42, 187.90, 193.82, gbp.bid, (gbp.bid - 189.42) * 0.20 * 1000 * 6.7 / 151.24),
        Position(700518, "XAUUSD.m", "Gold / USD", "SHORT", 0.10, 2338.10, 2351.00, 2318.40, gold.bid, (2338.10 - gold.bid) * 0.10 * 100),
    ]


def account_equity() -> float:
    return _ACCOUNT_EQUITY


def calendar_events() -> list[CalendarEvent]:
    base = datetime(2026, 3, 5, 12, 15, tzinfo=timezone.utc)
    return [
        CalendarEvent(base + timedelta(days=1), "ECB rate decision", "EUR", "HIGH", "Europe/Berlin", ("EUR / USD", "DAX / EUR")),
        CalendarEvent(base + timedelta(days=2, hours=3), "US Nonfarm Payrolls", "USD", "HIGH", "America/New_York", ("EUR / USD", "Gold / USD", "Nasdaq / USD")),
        CalendarEvent(base + timedelta(days=3, hours=4), "SARB interest rate decision", "ZAR", "HIGH", "Africa/Johannesburg", ("USD / ZAR",)),
        CalendarEvent(base + timedelta(days=4, hours=5), "BoE Governor speech", "GBP", "MEDIUM", "Europe/London", ("GBP / USD", "GBP / JPY", "FTSE / GBP")),
        CalendarEvent(base + timedelta(days=5, hours=6), "US CPI (YoY)", "USD", "HIGH", "America/New_York", ("EUR / USD", "Gold / USD")),
        CalendarEvent(base + timedelta(days=6, hours=7), "Fed Chair testimony", "USD", "MEDIUM", "America/New_York", ("Nasdaq / USD", "Dow / USD")),
    ]


def opportunity_rows() -> list[dict]:
    """Radar rows: every value derived from computed engine results."""
    rows = []
    for rec in universe():
        results = engine_results(rec.broker_symbol, "D1")
        active = [r for r in results if r.verdict in (Verdict.ACTIVE, Verdict.WATCHING)]
        if not active:
            continue
        aligned = [r for r in active if r.direction in (Direction.LONG, Direction.SHORT)]
        if not aligned:
            continue
        long_votes = sum(r.strength for r in aligned if r.direction == Direction.LONG)
        short_votes = sum(r.strength for r in aligned if r.direction == Direction.SHORT)
        direction = "LONG" if long_votes >= short_votes else "SHORT"
        strength = max(long_votes, short_votes) / (long_votes + short_votes)
        card = engines.scorecard(results)
        rows.append({
            "record": rec,
            "direction": direction,
            "strength": strength,
            "scorecard": card,
            "results": results,
            "why": " · ".join(r.reasons[0].text for r in active[:3] if r.reasons),
        })
    rows.sort(key=lambda r: r["strength"], reverse=True)
    return rows
