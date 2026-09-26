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


@dataclass(frozen=True)
class SizingResult:
    ok: bool
    volume: float
    loss_per_lot: float
    risk_amount: float
    actual_risk: float
    risk_reward: float
    reasons: tuple[str, ...]


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
        reasons.append(f"Requested volume {raw:.2f} lots is below broker minimum "
                       f"{contract.volume_min:.2f}; broker minimum would exceed the requested risk cap.")
    if rr < 2.0:
        reasons.append(f"Reward-to-risk {rr:.2f} is below the 2.0 warning threshold.")
    if actual_risk > risk_amount * 1.05:
        reasons.append("Actual risk noticeably exceeds the requested risk after step rounding.")
    # Safety invariant: never silently recommend the broker minimum when it
    # would exceed the user's requested maximum loss.  The old implementation
    # returned ok=True here, allowing an over-risked plan through pre-flight.
    if raw < contract.volume_min and actual_risk > risk_amount:
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
