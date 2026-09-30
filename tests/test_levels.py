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


def test_a_sweep_already_behind_the_market_is_treated_as_stale():
    """Price already traded through the level, so it cannot anchor the stop."""
    lv = risk.derive_levels(1.0835, "LONG", EURUSD, 1.0850, "LOW", 0.0018)
    assert guard_passes("LONG", 1.0835, lv, EURUSD)
    assert "ATR" in lv.basis
    assert any("already been traded through" in n for n in lv.notes)


# ------------------------------------------------------------ reward multiple
def test_default_target_is_two_r():
    assert risk.DEFAULT_REWARD_RATIO == 2.0
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0800, "LOW", 0.0012,
                            family="FX majors")
    assert (lv.target - lv.entry) / (lv.entry - lv.stop) == pytest.approx(
        2.0, abs=0.01)


def test_reward_multiple_is_configurable():
    for r in (1.0, 1.5, 3.0, 5.0):
        lv = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0800, "LOW", 0.0012,
                                family="FX majors", reward_ratio=r)
        assert (lv.target - lv.entry) / (lv.entry - lv.stop) == pytest.approx(
            r, abs=1e-3)
        assert guard_passes("LONG", 1.0825, lv, EURUSD)


def test_short_reward_multiple_mirrors_the_long_case():
    lv = risk.derive_levels(149.203, "SHORT", USDJPY, 149.318, "HIGH", 0.42,
                            family="FX crosses")
    # abs=0.01 rather than 1e-3: USDJPY quotes at 3 digits, so rounding the
    # target to the tick grid can shift the realised multiple by a few
    # ten-thousandths of a yen.
    assert (lv.entry - lv.target) / (lv.stop - lv.entry) == pytest.approx(
        2.0, abs=0.01)


def test_derived_target_sits_on_the_warning_threshold():
    """A 2R target lands on the line, so it must not be flagged as sub-2R."""
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0800, "LOW", 0.0012,
                            family="FX majors")
    sizing = risk.size_position(lv.entry, lv.stop, lv.target, 1.0, 10_000.0,
                                EURUSD)
    assert sizing.ok
    assert not [r for r in sizing.reasons if "warning threshold" in r]


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


# ------------------------------------------------- structure-defined brackets
def test_stop_goes_beyond_the_nearest_support():
    """The trader's rule: last support + 10 pips, on H4 structure."""
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0800)
    assert "support 1.08" in lv.basis
    assert (1.0800 - lv.stop) == pytest.approx(10 * 10 * EURUSD.point)
    assert guard_passes("LONG", 1.0825, lv, EURUSD)


def test_stop_goes_beyond_the_nearest_resistance_for_a_short():
    lv = risk.derive_levels(149.203, "SHORT", USDJPY, 0.0, "", 0.42,
                            family="FX crosses", resistance=149.318)
    assert "resistance 149.32" in lv.basis
    assert (lv.stop - 149.318) == pytest.approx(10 * 10 * USDJPY.point)
    assert guard_passes("SHORT", 149.203, lv, USDJPY)


def test_structure_beats_the_liquidity_sweep():
    """A confirmed level is where price turned; a sweep is a wick through one."""
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 1.0750, "LOW", 0.0012,
                            family="FX majors", support=1.0800)
    assert "support" in lv.basis
    assert "sweep" not in lv.basis


def test_target_is_the_next_level_in_the_move():
    # Support at 1.0800 puts the stop 35 pips away, so the first level out at
    # 1.0865 clears it and 1.0855 would not have.
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0800,
                            next_levels=[1.0865, 1.0890])
    assert lv.target == pytest.approx(1.0865)
    assert "next resistance 1.0865" in lv.basis


def test_short_targets_the_next_support_down():
    # Resistance at 149.318 with a 10-pip buffer leaves the stop 21.5 pips away.
    lv = risk.derive_levels(149.203, "SHORT", USDJPY, 0.0, "", 0.42,
                            family="FX crosses", resistance=149.318,
                            next_levels=[149.100, 148.900])
    assert lv.target == pytest.approx(148.900)
    assert "next support 148.9" in lv.basis
    assert any("Skipped 1" in n for n in lv.notes)


def test_levels_inside_the_stop_distance_are_skipped():
    """A target nearer than the stop cannot be expressed, so walk further out."""
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0800,
                            next_levels=[1.0830, 1.0840, 1.0890])
    assert lv.target == pytest.approx(1.0890)
    assert any("Skipped 2" in n for n in lv.notes)
    # The target always sits further away than the stop.
    assert (lv.target - lv.entry) > (lv.entry - lv.stop)


def test_target_never_lands_inside_the_stop():
    for supports in ([1.0810], [1.0800, 1.0790, 1.0750]):
        lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                                family="FX majors", support=1.0770,
                                next_levels=supports)
        assert (lv.target - lv.entry) >= (lv.entry - lv.stop) - 1e-9


def test_target_falls_back_to_r_when_no_level_clears_the_stop():
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0800,
                            next_levels=[1.0826])
    assert "target 2R" in lv.basis
    assert any("inside the stop distance" in n for n in lv.notes)
    assert guard_passes("LONG", 1.0825, lv, EURUSD)


def test_target_falls_back_when_no_level_lies_in_the_move():
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0800, next_levels=[])
    assert "target 2R" in lv.basis
    assert any("No resistance lies ahead" in n for n in lv.notes)


def test_atr_fallback_still_applies_without_structure():
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors")
    assert "ATR stop" in lv.basis
    assert guard_passes("LONG", 1.0825, lv, EURUSD)


def test_a_level_on_the_wrong_side_is_treated_as_stale():
    """Support above the market is not support."""
    lv = risk.derive_levels(1.0825, "LONG", EURUSD, 0.0, "", 0.0012,
                            family="FX majors", support=1.0850)
    assert "ATR stop" in lv.basis
    assert any("wrong side of the market" in n for n in lv.notes)
    assert guard_passes("LONG", 1.0825, lv, EURUSD)


# --------------------------------------------------------- structure_levels()
def test_structure_levels_orders_by_trading_distance():
    bars = _bars([(1.0900, 1.0905, 1.0870, 1.0875)] * 6 +
                 [(1.0870, 1.0878, 1.0820, 1.0825)] * 5 +
                 [(1.0820, 1.0825, 1.0810, 1.0815)] * 4 +
                 [(1.0815, 1.0820, 1.0805, 1.0818)] +
                 [(1.0818, 1.0840, 1.0812, 1.0835)])
    lv = engines.structure_levels(bars, market=1.0825, max_levels=99)
    assert lv["support"], "expected support below the market"
    assert lv["resistance"], "expected resistance above the market"
    # Supports descend toward the market, resistances ascend away from it.
    assert lv["support"] == sorted(lv["support"], reverse=True)
    assert lv["resistance"] == sorted(lv["resistance"])
    assert all(s < 1.0825 for s in lv["support"])
    assert all(r > 1.0825 for r in lv["resistance"])


def test_structure_levels_excludes_levels_on_the_wrong_side():
    bars = _bars([(1.0900, 1.0905, 1.0870, 1.0875)] * 6 +
                 [(1.0870, 1.0878, 1.0820, 1.0825)] * 5 +
                 [(1.0820, 1.0825, 1.0810, 1.0815)] * 4 +
                 [(1.0815, 1.0820, 1.0805, 1.0818)] +
                 [(1.0818, 1.0840, 1.0812, 1.0835)])
    lv = engines.structure_levels(bars, market=1.0825, max_levels=99)
    # Nothing above the market is offered as support, whatever its label.
    assert all(s < 1.0825 for s in lv["support"])


def test_structure_levels_can_be_empty():
    assert engines.structure_levels([], market=1.08) == {"support": [],
                                                         "resistance": []}


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
