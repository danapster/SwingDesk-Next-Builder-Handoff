"""Order dispatch: retcode decoding, verification, and the offline fail-closed.

These guard the failure that motivated the work: the UI reported "Order sent"
while nothing ever reached MetaTrader 5. A dispatch must only be reported as
successful when the broker returns an accepted retcode AND the ticket is found
on the account; every other path has to fail closed with an accurate reason.
"""
from __future__ import annotations

import sys
import types

import pytest

from swingdesk.core import demo_data
from swingdesk.core.models import OrderResult
from swingdesk.core.mt5_live import MT5LiveProvider


class FakeSymbolInfo:
    def __init__(self, name="EURUSD", digits=5, point=1e-05, filling_mode=1,
                 trade_stops_level=14, volume_step=0.01, volume_min=0.01,
                 volume_max=500.0, trade_mode=4):
        self.name = name
        self.digits = digits
        self.point = point
        self.trade_tick_size = point
        self.trade_tick_value = 1.0
        self.trade_contract_size = 100000
        self.volume_step = volume_step
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.trade_stops_level = trade_stops_level
        self.trade_freeze_level = 0
        self.filling_mode = filling_mode
        self.trade_mode = trade_mode
        self.visible = True


class FakeResult:
    def __init__(self, retcode, order=0, deal=0):
        self.retcode = retcode
        self.order = order
        self.deal = deal


class FakePosition:
    def __init__(self, ticket, symbol, magic, side=0, volume=0.01, price=1.1335):
        self.ticket = ticket
        self.symbol = symbol
        self.magic = magic
        self.type = side
        self.volume = volume
        self.price_open = price
        self.sl = 0.0
        self.tp = 0.0
        self.comment = "SwingDesk"


class FakeMT5:
    """Minimal stand-in for the MetaTrader5 module."""

    def __init__(self, retcode=10009, order=0, deal=0, check_retcode=0,
                 positions=(), orders=(), filling_mask=1, digits=5, point=1e-05):
        self.TRADE_ACTION_DEAL = 1
        self.ORDER_TYPE_BUY = 0
        self.ORDER_TYPE_SELL = 1
        self.ORDER_TIME_GTC = 0
        self.ORDER_FILLING_FOK = 0
        self.ORDER_FILLING_IOC = 1
        self.ORDER_FILLING_RETURN = 2
        self.POSITION_TYPE_BUY = 0
        self._retcode = retcode
        self._order = order
        self._deal = deal
        self._check_retcode = check_retcode
        self._positions = list(positions)
        self._orders = list(orders)
        self._digits = digits
        self._point = point
        self.sent = []
        self.checks = []
        self._filling_mask = filling_mask
        self.shutdown_called = False

    # -- constants mirroring the real module's numeric values
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_INVALID = 10013
    TRADE_RETCODE_INVALID_VOLUME = 10014
    TRADE_RETCODE_INVALID_PRICE = 10015
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_TRADE_DISABLED = 10017
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_REJECT = 10006

    def symbol_info(self, name):
        return FakeSymbolInfo(name=name, digits=self._digits, point=self._point,
                              filling_mode=self._filling_mask)

    def symbol_info_tick(self, name):
        return types.SimpleNamespace(bid=1.13340, ask=1.13350, time=0)

    def order_check(self, request):
        self.checks.append(dict(request))
        return types.SimpleNamespace(retcode=self._check_retcode, comment="")

    def order_send(self, request):
        self.sent.append(dict(request))
        return FakeResult(self._retcode, self._order, self._deal)

    def positions_get(self, symbol=None):
        return tuple(self._positions)

    def orders_get(self, symbol=None):
        return tuple(self._orders)

    def last_error(self):
        return (0, "Success")

    def shutdown(self):
        self.shutdown_called = True


def provider_with(mt5) -> MT5LiveProvider:
    p = MT5LiveProvider()
    p.mt5 = mt5
    p.connected = True
    return p


# --------------------------------------------------------------- retcode decoding
def test_retcode_10016_is_invalid_stops_not_market_closed():
    """Regression: 10016 was mislabelled 'market is closed', hiding the real fault."""
    p = provider_with(FakeMT5())
    text = p._describe_retcode(10016)
    assert "invalid stops" in text
    assert "market is closed" not in text


def test_market_closed_uses_its_own_code():
    p = provider_with(FakeMT5())
    text = p._describe_retcode(10018)
    assert "market is closed" in text
    assert "invalid stops" not in text


def test_unknown_retcode_still_reports_the_code():
    p = provider_with(FakeMT5())
    assert "424242" in p._describe_retcode(424242)


# ------------------------------------------------------------------ filling mode
def test_filling_mode_follows_the_symbol_mask():
    p = provider_with(FakeMT5(filling_mask=1))
    assert p._filling_mode(p.mt5.symbol_info("EURUSD")) == 0   # FOK
    p2 = provider_with(FakeMT5(filling_mask=2))
    assert p2._filling_mode(p2.mt5.symbol_info("EURUSD")) == 1  # IOC
    p3 = provider_with(FakeMT5(filling_mask=4))
    assert p3._filling_mode(p3.mt5.symbol_info("EURUSD")) == 2  # RETURN


# --------------------------------------------------------------------- happy path
def test_successful_order_is_verified_against_the_account():
    mt5 = FakeMT5(retcode=10009, order=555,
                  positions=(FakePosition(555, "EURUSD", 42),))
    p = provider_with(mt5)
    res = p.order_send("EURUSD", "LONG", 0.01, stop=1.13300, target=1.13400,
                       magic=42, verify=True)
    assert res.ok
    assert res.verified
    assert res.ticket == 555
    assert res.retcode == 10009
    assert mt5.sent[0]["type"] == 0
    assert mt5.sent[0]["volume"] == 0.01


def test_order_rejected_when_stops_fail_broker_order_check():
    """The broker's real stops level is stricter than symbol_info advertises."""
    mt5 = FakeMT5(check_retcode=10016)
    p = provider_with(mt5)
    # Comfortably outside the advertised 14-point level, so the order clears the
    # local guard and is refused by the broker's own check — the fault this test
    # exists to cover is a broker stricter than symbol_info, not a local one.
    res = p.order_send("EURUSD", "LONG", 0.01, stop=1.13300, target=1.13400)
    assert not res.ok
    assert "invalid stops" in res.message
    assert mt5.sent == []          # nothing was actually sent


def test_order_blocked_locally_when_stop_is_inside_the_stops_level():
    """A stop that drifted inside the stops level is caught before sending."""
    mt5 = FakeMT5()
    p = provider_with(mt5)
    # 2 points from the 1.1335 market, against an advertised 14.
    res = p.order_send("EURUSD", "LONG", 0.01, stop=1.13348, target=1.13400)
    assert not res.ok
    assert "stops level" in res.message
    assert mt5.sent == []
    assert mt5.checks == []        # never even asked the broker


def test_accepted_but_unlisted_is_not_reported_as_verified():
    mt5 = FakeMT5(retcode=10009, order=0, deal=777)   # no positions/orders back
    p = provider_with(mt5)
    res = p.order_send("EURUSD", "LONG", 0.01, verify=True)
    assert res.ok
    assert not res.verified
    assert "NOT confirmed" in res.message or "not found" in res.message


def test_server_rejection_reports_the_real_code():
    mt5 = FakeMT5(retcode=10019)   # no money
    p = provider_with(mt5)
    res = p.order_send("EURUSD", "LONG", 0.01)
    assert not res.ok
    assert res.retcode == 10019
    assert "margin" in res.message


def test_offline_provider_refuses_to_send():
    p = MT5LiveProvider()
    p.mt5 = None
    p.connected = False
    p.last_error = "MT5 initialize failed"
    res = p.order_send("EURUSD", "LONG", 0.01)
    assert not res.ok
    assert "initialize failed" in res.message


def test_wrong_sided_stops_are_refused_locally():
    mt5 = FakeMT5()
    p = provider_with(mt5)
    # A LONG stop above the market can never be valid.
    res = p.order_send("EURUSD", "LONG", 0.01, stop=1.14000, target=1.15000)
    assert not res.ok
    assert "below the market" in res.message
    assert mt5.sent == []


def test_volume_is_normalised_to_the_broker_step():
    mt5 = FakeMT5(retcode=10009, order=1, positions=(FakePosition(1, "EURUSD", 7),))
    p = provider_with(mt5)
    p.order_send("EURUSD", "LONG", 0.0173, magic=7)
    assert mt5.sent[0]["volume"] == pytest.approx(0.01)


# ------------------------------------------------------------ offline fail-closed
def test_router_refuses_when_mt5_is_offline(monkeypatch):
    """No terminal must never look like a successful dispatch."""
    monkeypatch.setattr(demo_data, "_ensure_live", lambda: False)
    monkeypatch.setattr(demo_data, "_LIVE", None)
    monkeypatch.setattr(demo_data, "_LIVE_ERROR", "no terminal")
    res = demo_data.order_send("EURUSD", "LONG", 0.01)
    assert isinstance(res, OrderResult)
    assert not res.ok
    assert not res.verified
    assert "no terminal" in res.message


# -------------------------------------------------------------------- plans page
def test_send_button_blocks_when_mt5_is_offline(make_app, monkeypatch):
    win = make_app()
    page = win.pages["plans"]
    monkeypatch.setattr(demo_data, "connection_status", lambda: {"connected": False})
    called = []
    monkeypatch.setattr(demo_data, "order_send", lambda *a, **k: called.append(1))
    page.send_order()
    assert called == [], "must not dispatch while the terminal is down"


def test_send_button_reports_rejection(make_app, monkeypatch):
    win = make_app()
    page = win.pages["plans"]
    page.entry.setValue(1.13350)
    page.stop.setValue(1.13300)
    page.target.setValue(1.13450)
    monkeypatch.setattr(demo_data, "connection_status",
                        lambda: {"connected": True, "login": 1, "server": "OctaFX-Demo"})
    monkeypatch.setattr(
        demo_data, "order_send",
        lambda *a, **k: OrderResult(False, 10016, "invalid stops"))
    page.send_order()
    # nothing is persisted when the broker refuses
    assert all("mt5_ticket" not in b for p in win.ctx.store.plans()
               for b in p.behaviour_flags)


def test_verified_fill_is_persisted_as_an_open_plan(make_app, monkeypatch):
    win = make_app()
    page = win.pages["plans"]
    page.entry.setValue(1.13350)
    page.stop.setValue(1.13300)
    page.target.setValue(1.13450)
    before = len(win.ctx.store.plans())
    monkeypatch.setattr(demo_data, "connection_status",
                        lambda: {"connected": True, "login": 1, "server": "OctaFX-Demo"})
    monkeypatch.setattr(
        demo_data, "order_send",
        lambda *a, **k: OrderResult(True, 10009, "done", symbol="EURUSD", direction="LONG",
                                    volume=0.01, price=1.13350, order_ticket=4242,
                                    deal_ticket=4243, position_ticket=4242,
                                    verified=True, planned_entry=1.13350))
    page.send_order()
    plans = win.ctx.store.plans()
    assert len(plans) == before + 1
    dispatched = plans[0]
    assert "mt5_ticket:4242" in dispatched.behaviour_flags
    assert dispatched.actual_fill == pytest.approx(1.13350)
