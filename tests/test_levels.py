"""Level derivation: SL/TP must be valid at the price the order actually fills at.

Regression cover for orders the broker refused because the stop and target were
drawn around a historical zone price.  By the time the order was sent the market
had usually moved past that anchor, which put the target on the wrong side of the
market and sized the position off a distance it would never fill across.

The rule these tests lock in:

  * levels are anchored on the fill price (ask to buy, bid to sell)
  * the stop sits beyond the last liquidity sweep
  * whatever the structure asks for, the broker's stops level is a hard floor
  * a sweep already behind the market is stale, so the stop falls back to ATR
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from swingdesk.core import engines, risk
from swingdesk.core.models import Bar, ContractSpec
from swingdesk.core.mt5_live import MT5LiveProvider

EURUSD = ContractSpec(digits=5, point=1e-05, tick_size=1e-05, tick_value=1.0,
                      contract_size=100000.0, volume_min=0.01, volume_max=50.0,
                      volume_step=0.01, stops_level_points=20,
                      freeze_level_points=0)
USDJPY = ContractSpec(digits=3, point=1e-03, tick_size=1e-03, tick_value=6.7,
                      contract_size=100000.0, volume_min=0.01, volume_max=50.0,
                      volume_step=0.01, stops_level_points=30,
                      freeze_level_points=0)


def guard_passes(direction: str, market: float, lv, contract: ContractSpec) -> bool:
    """Replicate every local guard in MT5LiveProvider.order_send."""
    is_buy = direction == "LONG"
    if is_buy:
        if lv.stop >= market or lv.target <= market:
            return False
    else:
        if lv.stop <= market or lv.target >= market:
            return False
    required = contract.stops_level_points * contract.point
    return (abs(market - lv.stop) >= required and
            abs(market - lv.target) >= required)


# ----------------------------------------------------------------- anchoring
def test_levels_anchor_on_the_fill_price_not_a_stale_zone():
    """The reported fault: TP below the market, sizing off a phantom distance."""
    market = 1.0835                      # live ask
    lv = risk.derive_levels(market, "LONG", EURUSD, 1.0805, "LOW", 0.0018)

    assert lv.entry == pytest.approx(market)
    assert lv.stop < market < lv.target
    assert guard_passes("LONG", market, lv, EURUSD)

    sizing = risk.size_position(lv.entry, lv.stop, lv.target, 1.0, 10_000.0, EURUSD)
    assert sizing.ok
    # The whole point: risk is now measured across the distance that fills.
    assert sizing.actual_risk <= sizing.risk_amount * 1.05


def test_short_anchors_below_the_bid():
    lv = risk.derive_levels(149.203, "SHORT", USDJPY, 149.318, "HIGH", 0.42)
    assert lv.target < lv.entry < lv.stop
    assert guard_passes("SHORT", 149.203, lv, USDJPY)


# ----------------------------------------------------------------- the sweep
def test_stop_sits_beyond_the_swept_liquidity():
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0800, "LOW", 0.0012,
                            family="FX majors")
    assert lv.stop < 1.0800, "stop must clear the swept low"
    assert "sweep" in lv.basis


def test_fx_buffer_is_ten_pips():
    """10 pips is 100 points at both 5-digit and 3-digit quoting."""
    five = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0800, "LOW", 0.0012,
                              family="FX majors")
    assert (1.0800 - five.stop) == pytest.approx(0.0010)
    assert (1.0800 - five.stop) == pytest.approx(10 * 10 * EURUSD.point)

    three = risk.derive_levels(149.203, "SHORT", USDJPY, 149.318, "HIGH", 0.42,
                               family="FX crosses")
    assert (three.stop - 149.318) == pytest.approx(0.100)
    assert (three.stop - 149.318) == pytest.approx(10 * 10 * USDJPY.point)


def test_non_fx_buffer_scales_with_volatility_instead_of_points():
    """A fixed point count means nothing across gold and bitcoin."""
    gold = ContractSpec(digits=2, point=0.01, tick_size=0.01, tick_value=1.0,
                        contract_size=100.0, volume_min=0.01, volume_max=100.0,
                        volume_step=0.01, stops_level_points=20,
                        freeze_level_points=0)
    atr = 8.0
    lv = risk.derive_levels(2325.41, "LONG", gold, 2320.00, "LOW", atr,
                            family="Metals")
    assert (2320.00 - lv.stop) == pytest.approx(risk.ATR_BUFFER_FRACTION * atr)

    # Same 20-point stops level, but a quiet instrument gets a tighter buffer
    # than a violent one — which a point count could never express.
    calm = risk.derive_levels(2325.41, "LONG", gold, 2320.00, "LOW", 2.0,
                              family="Metals")
    wild = risk.derive_levels(2325.41, "LONG", gold, 2320.00, "LOW", 40.0,
                              family="Metals")
    assert (2320.00 - calm.stop) < (2320.00 - wild.stop)


def test_unknown_family_falls_back_to_a_fixed_buffer():
    # stops_level 0 so the fallback is what is actually under test.
    plain = ContractSpec(digits=5, point=1e-05, tick_size=1e-05, tick_value=1.0,
                         contract_size=100000.0, volume_min=0.01, volume_max=50.0,
                         volume_step=0.01, stops_level_points=0,
                         freeze_level_points=0)
    lv = risk.derive_levels(1.0825, "LONG", plain, 1.0800, "LOW", 0.0, family="")
    assert (1.0800 - lv.stop) == pytest.approx(risk.SWEEP_BUFFER_POINTS * plain.point)


def test_sweep_buffer_widens_when_the_broker_stops_level_is_larger():
    tight = ContractSpec(digits=5, point=1e-05, tick_size=1e-05, tick_value=1.0,
                         contract_size=100000.0, volume_min=0.01, volume_max=50.0,
                         volume_step=0.01, stops_level_points=300,
                         freeze_level_points=0)
    lv = risk.derive_levels(1.0825, "LONG", tight, 1.0800, "LOW", 0.0012,
                            family="FX majors")
    # 300 points beats the 100-point (10 pip) FX rule; the tighter of the two wins.
    assert (1.0800 - lv.stop) == pytest.approx(300 * tight.point)
    assert any("stops level" in n for n in lv.notes)


def test_a_sweep_already_behind_the_market_is_treated_as_stale():
    """Price already traded through the level, so it cannot anchor the stop."""
    lv = risk.derive_levels(1.0835, "LONG", EURUSD, 1.0850, "LOW", 0.0018)
    assert guard_passes("LONG", 1.0835, lv, EURUSD)
    assert "ATR" in lv.basis
    assert any("already been traded through" in n for n in lv.notes)


def test_a_sweep_on_the_wrong_side_is_ignored():
    """A low sweep is meaningless for a short; use the high."""
    lv = risk.derive_levels(149.203, "SHORT", USDJPY, 140.0, "LOW", 0.42)
    assert guard_passes("SHORT", 149.203, lv, USDJPY)
    assert "ATR" in lv.basis


# ------------------------------------------------------------- broker floor
def test_stops_level_is_a_floor_even_when_structure_asks_for_less():
    tight = ContractSpec(digits=5, point=1e-05, tick_size=1e-05, tick_value=1.0,
                         contract_size=100000.0, volume_min=0.01, volume_max=50.0,
                         volume_step=0.01, stops_level_points=500,
                         freeze_level_points=0)
    lv = risk.derive_levels(1.0835, "LONG", tight, 1.0830, "LOW", 0.0002)
    assert (1.0835 - lv.stop) >= 500 * tight.point - 1e-12
    assert guard_passes("LONG", 1.0835, lv, tight)


def test_no_sweep_and_no_atr_still_yields_a_sendable_order():
    lv = risk.derive_levels(1.0835, "LONG", EURUSD, 0.0, "", 0.0)
    assert guard_passes("LONG", 1.0835, lv, EURUSD)
    assert any("provisional" in n for n in lv.notes)


# -------------------------------------------------------------- tick grid
@pytest.mark.parametrize("contract,market,direction", [
    (EURUSD, 1.083512, "LONG"),
    (USDJPY, 149.2034, "SHORT"),
])
def test_prices_land_on_the_broker_tick_grid(contract, market, direction):
    lv = risk.derive_levels(market, direction, contract, 0.0, "", 0.0031)
    step = contract.tick_size
    for price in (lv.entry, lv.stop, lv.target):
        assert abs(price / step - round(price / step)) < 1e-6, f"{price} off grid"
        assert round(price, contract.digits) == pytest.approx(price)


# ------------------------------------------------------------- last_sweep()
def _bars(rows):
    t0 = datetime(2026, 1, 1)
    return [Bar(t0 + timedelta(hours=i), o, h, l, c, 100)
            for i, (o, h, l, c) in enumerate(rows)]


def test_last_sweep_finds_the_low_that_took_liquidity():
    bars = _bars([(1.0900, 1.0905, 1.0870, 1.0875)] * 6 +
                 [(1.0870, 1.0878, 1.0820, 1.0825)] * 5 +
                 [(1.0820, 1.0825, 1.0810, 1.0815)] * 4 +
                 [(1.0815, 1.0820, 1.0790, 1.0815)] +     # the sweep: dips under 1.0810
                 [(1.0815, 1.0840, 1.0812, 1.0830)])      # recovers, holds above
    price, kind = engines.last_sweep(bars)
    assert kind == "LOW"
    assert price == pytest.approx(1.0790)


def test_last_sweep_stays_silent_on_a_clean_trend():
    bars = _bars([(1.0900 - i * 0.0004, 1.0905 - i * 0.0004,
                   1.0870 - i * 0.0004, 1.0875 - i * 0.0004) for i in range(30)])
    assert engines.last_sweep(bars) == (0.0, "")


def test_last_sweep_handles_too_few_bars():
    assert engines.last_sweep([]) == (0.0, "")
    assert engines.last_sweep(_bars([(1.0, 1.1, 0.9, 1.0)])) == (0.0, "")


# ------------------------------------------------------------- family matters
@pytest.mark.parametrize("name,base,profit,expected", [
    # "DJ" is the Dow's token and sits inside USDJPY, which used to file every
    # yen pair as an index CFD — and so gave it an index-sized stop buffer.
    ("USDJPY", "USD", "JPY", "FX majors"),
    ("EURJPY", "EUR", "JPY", "FX crosses"),      # no USD leg, so a cross
    ("EURUSD", "EUR", "USD", "FX majors"),
    ("EURGBP", "EUR", "GBP", "FX crosses"),
    ("USDMXN", "USD", "MXN", "FX exotics"),
    ("EURUSD.a", "EUR", "USD", "FX majors"),      # suffixed FX is still FX
    ("US30", "USD", "USD", "Index CFDs"),
    ("NAS100", "USD", "USD", "Index CFDs"),
    ("JP225", "JPY", "JPY", "Index CFDs"),
    ("DAX", "EUR", "EUR", "Index CFDs"),
    ("XAUUSD", "XAU", "USD", "Metals"),
    ("BTCUSD", "BTC", "USD", "Crypto"),
    # A single-letter equity ticker must not be mistaken for a currency pair.
    ("T.NYSE", "USD", "USD", "Broker CFDs"),
    ("NFLX.Daily", "USD", "USD", "Broker CFDs"),
])
def test_family_classification(name, base, profit, expected):
    assert MT5LiveProvider._classify(name, base, profit)[1] == expected
