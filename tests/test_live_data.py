from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from swingdesk.core.calendar_cache import CalendarCache
from swingdesk.core.mt5_live import MT5LiveProvider


SAMPLE = [{
    "title": "Test CPI",
    "country": "USD",
    "date": "2026-09-28T08:30:00-04:00",
    "impact": "High",
    "forecast": "2.5%",
    "previous": "2.6%",
}]


def test_calendar_runtime_reads_local_json_only(tmp_path, monkeypatch):
    path = tmp_path / "ff_calendar_thisweek.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    cache = CalendarCache(path)
    monkeypatch.setattr("swingdesk.core.calendar_cache.urlopen",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network used")))
    events = cache.load_events()
    assert len(events) == 1
    assert events[0].currency == "USD"
    assert events[0].impact == "HIGH"
    assert events[0].time_utc == datetime(2026, 9, 28, 12, 30, tzinfo=timezone.utc)


def test_calendar_weekly_refresh_is_due_after_monday_midnight_sast(tmp_path):
    path = tmp_path / "ff_calendar_thisweek.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    cache = CalendarCache(path)
    cache._write_meta({"last_download": "2026-09-27T20:00:00+00:00"})
    now = datetime(2026, 9, 27, 22, 1, tzinfo=timezone.utc)
    assert cache.weekly_refresh_due(now)


def test_calendar_rejects_html_rate_limit_payload():
    with pytest.raises(ValueError):
        CalendarCache._validate_payload(b"<!DOCTYPE html><h1>Request Denied</h1>")


class FakeRates(list):
    pass


def _fake_mt5():
    info = SimpleNamespace(
        name="EURUSD.a", description="Euro vs US Dollar", path="Forex\\Majors",
        currency_base="EUR", currency_profit="USD", visible=True,
        digits=5, point=0.00001, trade_tick_size=0.00001,
        trade_tick_value=1.0, trade_tick_value_profit=1.0,
        trade_contract_size=100000, volume_min=0.01, volume_max=100.0,
        volume_step=0.01, trade_stops_level=20, trade_freeze_level=0,
        trade_mode=4, filling_mode=1,
    )
    rates = FakeRates([{
        "time": 1790596800, "open": 1.10, "high": 1.11, "low": 1.09,
        "close": 1.105, "tick_volume": 1000, "spread": 20, "real_volume": 0,
    }])
    pos = SimpleNamespace(ticket=7, symbol="EURUSD.a", type=0, volume=0.1,
                          price_open=1.10, sl=1.09, tp=1.12,
                          price_current=1.105, profit=50.0)
    return SimpleNamespace(
        TIMEFRAME_M15=15, TIMEFRAME_H1=60, TIMEFRAME_H4=240,
        TIMEFRAME_D1=1440, TIMEFRAME_W1=10080, POSITION_TYPE_BUY=0,
        initialize=lambda *_a, **_k: True,
        shutdown=lambda: None,
        last_error=lambda: (1, "ok"),
        terminal_info=lambda: SimpleNamespace(name="Broker MT5", company="Broker"),
        account_info=lambda: SimpleNamespace(login=1234, server="Broker-Live",
                                             currency="USD", balance=10000.0,
                                             equity=10125.0),
        symbols_get=lambda: (info,),
        symbol_info=lambda name: info if name == info.name else None,
        symbol_info_tick=lambda name: SimpleNamespace(bid=1.1001, ask=1.1003),
        symbol_select=lambda *_a, **_k: True,
        copy_rates_from_pos=lambda *_a, **_k: rates,
        positions_get=lambda: (pos,),
    )


def test_mt5_live_provider_maps_real_broker_surface(monkeypatch):
    fake = _fake_mt5()
    monkeypatch.setattr("swingdesk.core.mt5_live.importlib.import_module", lambda _n: fake)
    provider = MT5LiveProvider()
    assert provider.connect()
    assert len(provider.universe()) == 1
    rec = provider.symbol("EURUSD.a")
    assert rec is not None
    assert rec.canonical_name == "EUR / USD"
    assert rec.bid == pytest.approx(1.1001)
    assert rec.contract.tick_value == pytest.approx(1.0)
    bars = provider.bars("EURUSD.a", "D1", 1)
    assert len(bars) == 1 and bars[0].close == pytest.approx(1.105)
    assert provider.account_equity() == pytest.approx(10125.0)
    positions = provider.positions()
    assert len(positions) == 1 and positions[0].ticket == 7


def test_mt5_connection_info_identifies_live_account(monkeypatch):
    fake = _fake_mt5()
    monkeypatch.setattr("swingdesk.core.mt5_live.importlib.import_module", lambda _n: fake)
    provider = MT5LiveProvider()
    assert provider.connect()
    info = provider.connection_info()
    assert info["connected"] is True
    assert info["server"] == "Broker-Live"
    assert info["login"] == 1234
