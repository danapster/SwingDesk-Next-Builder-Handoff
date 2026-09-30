"""Swing Desk — contract-aware risk sizing.

Implements the production-plan formula exactly:
  loss_per_lot = stop_distance_price * trade_tick_value / trade_tick_size
  risk_amount = account_equity * risk_percent / 100
  raw_volume  = risk_amount / loss_per_lot
  volume      = floor_to_volume_step(raw_volume), clamped to [volume_min, volume_max]
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .models import ContractSpec


MAX_RISK_OVERAGE_FACTOR = 1.05


@dataclass(frozen=True)
class SizingResult:
    ok: bool
    volume: float
    loss_per_lot: float
    risk_amount: float
    actual_risk: float
    risk_reward: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Levels:
    """A trade's three prices, derived from the price the order will fill at."""
    entry: float
    stop: float
    target: float
    basis: str
    notes: tuple[str, ...] = ()


# Fallback buffer when the instrument family is unknown, in points.
SWEEP_BUFFER_POINTS = 10
# FX is quoted in pips, and 10 pips is the conventional buffer beyond a swept
# low.  A pip is 10 points at both 5-digit and 3-digit quoting.
FX_SWEEP_BUFFER_PIPS = 10
# Metals, indices and crypto have no meaningful pip, and a fixed point count is
# meaningless across a 2400 gold contract and a 68000 BTC one, so those scale
# with the instrument's own volatility instead.
ATR_BUFFER_FRACTION = 0.25
# Fallback stop width when the lookback contains no confirmed sweep.
ATR_STOP_MULTIPLE = 1.5
# Default reward multiple. Matches the 2.0 warning threshold in size_position().
DEFAULT_REWARD_RATIO = 2.0


def round_to_tick(price: float, contract: ContractSpec) -> float:
    """Snap a price to the broker's tick grid.

    Sending 1.0831000 for a 5-digit symbol is not merely untidy: some brokers
    reject an off-grid stop outright, and the size maths below would be done
    against a price the terminal will never accept.
    """
    size = contract.tick_size if contract.tick_size > 0 else contract.point
    if size <= 0:
        return float(price)
    return round(round(float(price) / size) * size, int(contract.digits))


def sweep_buffer(family: str, contract: ContractSpec, atr_value: float = 0.0) -> float:
    """How far beyond the swept level the stop should sit, in price terms.

    FX pairs get 10 pips, the buffer a swing stop conventionally carries.
    Everything else scales with ATR, because a fixed point count means something
    entirely different on gold than on bitcoin and nothing sensible across both.
    """
    point = contract.point if contract.point > 0 else 0.0
    if point <= 0:
        return 0.0
    if (family or "").startswith("FX"):
        return FX_SWEEP_BUFFER_PIPS * 10 * point
    if atr_value > 0:
        return ATR_BUFFER_FRACTION * atr_value
    return max(SWEEP_BUFFER_POINTS * point, 0.0)


def derive_levels(market: float, direction: str, contract: ContractSpec,
                  sweep_price: float = 0.0, sweep_kind: str = "",
                  atr_value: float = 0.0, family: str = "",
                  reward_ratio: float = DEFAULT_REWARD_RATIO) -> Levels:
    """Build entry/stop/target around the live market price.

    `market` must be the price the order actually fills at — the ask for a buy,
    the bid for a sell.  Anchoring levels to a historical structure price
    instead is what previously produced orders the broker refused: the levels
    were valid where they were drawn and already stale by the time they were
    sent, so the stop and target landed on the wrong side of the market and
    the volume, sized off the drawn distance, did not match the real risk.

    The stop goes beyond the last liquidity sweep by `sweep_buffer`.  With no
    confirmed sweep it falls back to an ATR stop, so a valid level always
    exists.  Either way it is then pushed out to satisfy the broker's stops
    level, which is frequently stricter than the advertised value.
    """
    notes: list[str] = []
    is_buy = (direction or "").upper() == "LONG"
    required = max(contract.stops_level_points * contract.point, 0.0)
    buffer = sweep_buffer(family, contract, atr_value)
    min_dist = max(buffer, required)
    if min_dist <= 0:
        min_dist = max(SWEEP_BUFFER_POINTS * contract.point, 0.0)

    wants_low = is_buy                      # a long needs room down to the sweep
    basis = ""
    raw_stop = 0.0

    if sweep_price > 0 and ((wants_low and sweep_kind == "LOW") or
                            (not wants_low and sweep_kind == "HIGH")):
        raw_stop = sweep_price - min_dist if wants_low else sweep_price + min_dist
        basis = f"liquidity sweep {sweep_price:.5g} {sweep_kind.lower()} + buffer"
        if required > buffer > 0:
            notes.append(f"The broker stops level ({contract.stops_level_points} points) "
                         f"is wider than the {min_dist:.5g} buffer, so the stop was "
                         "widened to clear it.")
    else:
        width = atr_value * ATR_STOP_MULTIPLE if atr_value > 0 else market * 0.004
        if atr_value <= 0:
            notes.append("No confirmed liquidity sweep and no ATR available; "
                         "stop placed at a provisional 0.4% width.")
        else:
            notes.append("No confirmed liquidity sweep in the lookback; "
                         f"stop placed at {ATR_STOP_MULTIPLE:g}x ATR.")
        raw_stop = market - width if is_buy else market + width
        basis = "ATR stop" if atr_value > 0 else "provisional 0.4% stop"

    # A sweep that sits on the wrong side of the market is stale, not structure.
    if is_buy and raw_stop >= market:
        width = atr_value * ATR_STOP_MULTIPLE if atr_value > 0 else market * 0.004
        raw_stop = market - width
        basis = "ATR stop (sweep already behind the market)"
        notes.append("The swept low is at or above the market; it has already been "
                     "traded through, so the stop fell back to ATR.")
    elif not is_buy and raw_stop <= market:
        width = atr_value * ATR_STOP_MULTIPLE if atr_value > 0 else market * 0.004
        raw_stop = market + width
        basis = "ATR stop (sweep already behind the market)"
        notes.append("The swept high is at or below the market; it has already been "
                     "traded through, so the stop fell back to ATR.")

    # The broker's stops level is a hard floor on the distance, whatever the
    # structure asked for.
    if is_buy and market - raw_stop < required:
        raw_stop = market - required
        notes.append(f"Stop pushed out to the broker stops level "
                     f"({contract.stops_level_points} points).")
    elif not is_buy and raw_stop - market < required:
        raw_stop = market + required
        notes.append(f"Stop pushed out to the broker stops level "
                     f"({contract.stops_level_points} points).")

    risk_distance = abs(market - raw_stop)
    reward_distance = risk_distance * max(reward_ratio, 0.1)

    entry = round_to_tick(market, contract)
    stop = round_to_tick(raw_stop, contract)
    target = round_to_tick(market + reward_distance if is_buy
                           else market - reward_distance, contract)

    # Rounding to the tick grid can shave a point off the stops level; restore it.
    if is_buy and entry - stop < required:
        stop = round_to_tick(entry - required, contract)
    elif not is_buy and stop - entry < required:
        stop = round_to_tick(entry + required, contract)

    return Levels(entry, stop, target, basis, tuple(notes))


def floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(round(value / step, 9)) * step


def size_position(entry: float, stop: float, target: float, risk_percent: float,
                  equity: float, contract: ContractSpec) -> SizingResult:
    reasons: list[str] = []
    numeric = (entry, stop, target, risk_percent, equity, contract.tick_size,
               contract.tick_value, contract.volume_min, contract.volume_max,
               contract.volume_step, contract.point)
    if not all(math.isfinite(v) for v in numeric):
        return SizingResult(False, 0, 0, 0, 0, 0,
                            ("Sizing inputs and broker contract values must be finite.",))
    if entry <= 0 or stop <= 0 or target <= 0:
        return SizingResult(False, 0, 0, 0, 0, 0,
                            ("Entry, stop and target must all be greater than zero.",))
    if risk_percent <= 0 or risk_percent > 100:
        return SizingResult(False, 0, 0, 0, 0, 0, ("Risk percent must be between 0 and 100.",))
    if equity <= 0:
        return SizingResult(False, 0, 0, 0, 0, 0, ("Account equity must be greater than zero.",))
    if contract.tick_size <= 0 or contract.tick_value <= 0:
        return SizingResult(False, 0, 0, 0, 0, 0,
                            ("Broker tick size and tick value must be greater than zero.",))
    if (contract.volume_min <= 0 or contract.volume_max < contract.volume_min or
            contract.volume_step <= 0):
        return SizingResult(False, 0, 0, 0, 0, 0,
                            ("Broker volume constraints are invalid.",))
    if entry == stop:
        return SizingResult(False, 0, 0, 0, 0, 0, ("Entry cannot equal stop.",))
    if not ((stop < entry < target) or (target < entry < stop)):
        return SizingResult(False, 0, 0, 0, 0, 0,
                            ("Stop and target must be on opposite sides of entry.",))
    stop_distance = abs(entry - stop)
    if stop_distance < contract.stops_level_points * contract.point:
        return SizingResult(False, 0, 0, 0, 0, 0,
                            (f"Stop distance {stop_distance:.5g} is inside the broker "
                             f"stops level ({contract.stops_level_points} points).",))
    target_distance = abs(target - entry)
    if target_distance < contract.stops_level_points * contract.point:
        return SizingResult(False, 0, 0, 0, 0, 0,
                            (f"Target distance {target_distance:.5g} is inside the broker "
                             f"stops level ({contract.stops_level_points} points).",))

    loss_per_lot = stop_distance * contract.tick_value / contract.tick_size
    risk_amount = equity * risk_percent / 100
    raw = risk_amount / loss_per_lot if loss_per_lot > 0 else 0.0
    volume = floor_to_step(raw, contract.volume_step)
    volume = min(max(volume, contract.volume_min), contract.volume_max)
    actual_risk = volume * loss_per_lot
    rr = target_distance / stop_distance if stop_distance else 0.0

    if raw > contract.volume_max:
        reasons.append(f"Requested volume {raw:.2f} lots exceeds broker maximum "
                       f"{contract.volume_max:.2f}; clamped.")
    if raw < contract.volume_min:
        if actual_risk > risk_amount * MAX_RISK_OVERAGE_FACTOR:
            reasons.append(f"Requested volume {raw:.2f} lots is below broker minimum "
                           f"{contract.volume_min:.2f}; broker minimum would materially exceed "
                           "the requested risk cap.")
        else:
            reasons.append(f"Requested volume {raw:.2f} lots is below broker minimum "
                           f"{contract.volume_min:.2f}; minimum volume applied within the "
                           "5% rounding tolerance.")
    if rr < 2.0:
        reasons.append(f"Reward-to-risk {rr:.2f} is below the 2.0 warning threshold.")
    if actual_risk > risk_amount * MAX_RISK_OVERAGE_FACTOR:
        reasons.append("Actual risk noticeably exceeds the requested risk after step rounding.")
    # Safety invariant: a broker minimum may only exceed the nominal risk by
    # the same small tolerance already used for lot-step rounding.  Material
    # over-risk remains a hard failure instead of being silently clamped up.
    if (raw < contract.volume_min and
            actual_risk > risk_amount * MAX_RISK_OVERAGE_FACTOR):
        return SizingResult(False, volume, loss_per_lot, risk_amount,
                            actual_risk, rr, tuple(reasons))
    return SizingResult(True, volume, loss_per_lot, risk_amount, actual_risk, rr, tuple(reasons))


def order_check(entry: float, stop: float, target: float, volume: float,
                contract: ContractSpec, equity: float) -> tuple[bool, list[str]]:
    """Broker-side validation gate. A dispatch may never proceed when false."""
    checks: list[str] = []
    ok = True
    if not all(math.isfinite(v) for v in (entry, stop, target, volume, equity)):
        return False, ["Order values must be finite."]
    if entry <= 0 or stop <= 0 or target <= 0:
        ok = False; checks.append("Entry, stop and target must be greater than zero.")
    if volume <= 0:
        ok = False; checks.append("Volume must be greater than zero.")
    if not ((stop < entry < target) or (target < entry < stop)):
        ok = False; checks.append("Stop and target must be on opposite sides of entry.")
    if not (contract.volume_min <= volume <= contract.volume_max):
        ok = False; checks.append(f"Volume {volume} outside broker range "
                                  f"{contract.volume_min}–{contract.volume_max}.")
    if contract.volume_step <= 0:
        ok = False; checks.append("Broker volume step is invalid.")
    elif abs((round(volume / contract.volume_step) * contract.volume_step) - volume) > 1e-9:
        ok = False; checks.append(f"Volume {volume} does not align to step {contract.volume_step}.")
    if abs(entry - stop) < contract.stops_level_points * contract.point:
        ok = False; checks.append("Stop distance violates stops level.")
    if abs(target - entry) < contract.stops_level_points * contract.point:
        ok = False; checks.append("Target distance violates stops level.")
    if equity <= 0:
        ok = False; checks.append("Account equity unavailable.")
    if ok:
        checks.append("volume min/max/step accepted")
        checks.append("stop/target distance accepted")
        checks.append(f"filling mode {contract.filling_mode} available")
    return ok, checks
