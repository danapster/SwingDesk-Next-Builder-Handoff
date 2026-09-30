"""Swing Desk — setup engines A-I (shared primitives, evidence payloads).

Each engine computes a deterministic verdict from real bars and returns
explainable evidence. No engine re-implements another engine's primitive:
pivots, ATR and impulse legs live here once and are shared.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from .models import Bar, Direction, EngineResult, EvidenceLevel, Reason, Verdict

# ---------------------------------------------------------------- primitives


def atr(bars: list[Bar], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for prev, cur in zip(bars[-period - 1 :], bars[-period:]):
        trs.append(max(cur.high - cur.low,
                       abs(cur.high - prev.close),
                       abs(cur.low - prev.close)))
    return mean(trs) if trs else 0.0


def pivots(bars: list[Bar], left: int = 3, right: int = 3) -> list[tuple[int, Bar, str]]:
    """Swing pivots: (index, bar, 'H'|'L')."""
    out: list[tuple[int, Bar, str]] = []
    for i in range(left, len(bars) - right):
        window = bars[i - left : i + right + 1]
        hi = bars[i]
        if hi.high == max(b.high for b in window):
            out.append((i, hi, "H"))
        lo = bars[i]
        if lo.low == min(b.low for b in window):
            out.append((i, lo, "L"))
    return out


def impulse_leg(bars: list[Bar]) -> tuple[Bar, Bar] | None:
    """Most recent opposing-pivot pair (leg start -> leg end)."""
    ps = pivots(bars)
    if len(ps) < 2:
        return None
    a, b = ps[-2], ps[-1]
    if a[2] == b[2]:
        return None
    return a[1], b[1]


def structure_levels(bars: list[Bar], market: float, left: int = 3,
                     right: int = 3, max_levels: int = 4) -> dict:
    """Support and resistance around a price, nearest first.

    A level is a confirmed swing pivot, so it is where the market has actually
    turned rather than an arbitrary round number.  Levels are returned in
    trading order — supports descending toward the market, resistances
    ascending away from it — because the caller walks them outward until the
    bracket it can express.

    Levels at or beyond `market` are excluded from the near side: a support
    already above the price is not support, and treating it as one is how a
    bracket ends up with its stop on the wrong side of the entry.
    """
    ps = pivots(bars, left, right)
    supports = sorted({round(b.low, 12) for _i, b, k in ps
                       if k == "L" and b.low < market}, reverse=True)
    resistances = sorted({round(b.high, 12) for _i, b, k in ps
                          if k == "H" and b.high > market})
    return {"support": supports[:max_levels],
            "resistance": resistances[:max_levels]}


def last_sweep(bars: list[Bar], left: int = 3, right: int = 3) -> tuple[float, str]:
    """Most recent confirmed liquidity sweep as (extreme, "LOW"|"HIGH").

    A sweep is a bar that pierces a level already confirmed as a pivot and then
    closes back inside it, taking out resting liquidity without accepting the
    price.  "LOW" is the sell-side sweep that matters for a long stop; "HIGH"
    is its buy-side mirror for a short.

    Engine C reports the *resting* 40-bar range high/low, which is a different
    thing: it is where liquidity still sits, not where it was last taken.  A
    stop wants the latter.

    Returns (0.0, "") when the lookback holds no confirmed sweep.
    """
    ps = pivots(bars, left, right)
    if not ps:
        return 0.0, ""
    # Newest pivot first, and scan the bars that follow it backwards, so the
    # result is the most recent sweep rather than the first one after some older
    # level. The level is the pivot's own extreme: that is the resting
    # liquidity. Comparing against the lowest low of the whole prior history
    # instead would make almost any bar in a downtrend look like a sweep.
    for idx, bar, kind in reversed(ps):
        if kind == "L":
            level = float(bar.low)
            for b in reversed(bars[idx + 1 :]):
                if b.low < level and b.close > level:
                    return float(b.low), "LOW"
        else:
            level = float(bar.high)
            for b in reversed(bars[idx + 1 :]):
                if b.high > level and b.close < level:
                    return float(b.high), "HIGH"
    return 0.0, ""


# ---------------------------------------------------------------- engines

def engine_a_structure(bars: list[Bar]) -> EngineResult:
    ps = pivots(bars)
    highs = [(i, b) for i, b, k in ps if k == "H"][-3:]
    lows = [(i, b) for i, b, k in ps if k == "L"][-3:]
    if len(highs) < 2 or len(lows) < 2:
        return EngineResult("A.structure", Verdict.NOT_PRESENT, 0, Direction.NONE)

    hh = highs[-1][1].high > highs[-2][1].high
    hl = lows[-1][1].low > lows[-2][1].low
    lh = highs[-1][1].high < highs[-2][1].high
    ll = lows[-1][1].low < lows[-2][1].low

    reasons, evidence = [], []
    if hh and hl:
        bias, direction, strength = "Uptrend: higher highs, higher lows", Direction.LONG, 78
        reasons.append(Reason("A.hh", "Latest swing high above prior high"))
        reasons.append(Reason("A.hl", "Latest swing low above prior low"))
    elif lh and ll:
        bias, direction, strength = "Downtrend: lower highs, lower lows", Direction.SHORT, 78
        reasons.append(Reason("A.lh", "Latest swing high below prior high"))
        reasons.append(Reason("A.ll", "Latest swing low below prior low"))
    else:
        bias, direction, strength = "Range / mixed structure", Direction.NONE, 42
        reasons.append(Reason("A.mixed", "No aligned swing sequence"))

    evidence.append(EvidenceLevel(highs[-1][1].high, f"Swing high · {bias.split(':')[0]}", "level"))
    evidence.append(EvidenceLevel(lows[-1][1].low, f"Swing low · {bias.split(':')[0]}", "level"))
    return EngineResult("A.structure", Verdict.ACTIVE if direction != Direction.NONE else Verdict.WATCHING,
                        strength, direction, reasons, evidence, ["D1", "H4"])


def engine_b_supply_demand(bars: list[Bar]) -> EngineResult:
    a = atr(bars)
    if a == 0:
        return EngineResult("B.supply_demand", Verdict.NOT_PRESENT, 0, Direction.NONE)
    for i in range(len(bars) - 2, 3, -1):
        base, dep = bars[i], bars[i + 1]
        body = abs(dep.close - dep.open)
        rng = dep.high - dep.low
        if body > 1.6 * a and body / rng > 0.62:  # impulsive departure
            if dep.close > dep.open and base.close <= base.open:
                zone_lo, zone_hi = min(base.low, base.close), base.high
                tag = "DEMAND"
                direction = Direction.LONG
            elif dep.close < dep.open and base.close >= base.open:
                zone_lo, zone_hi = base.low, max(base.high, base.close)
                tag = "SUPPLY"
                direction = Direction.SHORT
            else:
                continue
            retested = any(zone_lo <= b.low <= zone_hi or zone_lo <= b.high <= zone_hi
                           for b in bars[i + 2 :])
            state = "TESTED" if retested else "PRISTINE"
            strength = 64 if retested else 82
            reasons = [Reason("B.base", f"{tag} base before impulsive departure ({body:.5g} range)"),
                       Reason("B.departure", f"Departure body {body / a:.1f}x ATR, body dominance {body / rng:.0%}")]
            if retested:
                reasons.append(Reason("B.retest", "Zone has been retested (TESTED)"))
            else:
                reasons.append(Reason("B.fresh", "Zone untested (PRISTINE)"))
            return EngineResult("B.supply_demand",
                                Verdict.WATCHING if retested else Verdict.ACTIVE,
                                strength, direction, reasons,
                                [EvidenceLevel((zone_lo + zone_hi) / 2, f"{tag} · Engine B · {state}",
                                               "zone", zone_hi)],
                                ["H4", "D1"])
    return EngineResult("B.supply_demand", Verdict.NOT_PRESENT, 0, Direction.NONE,
                        [Reason("B.none", "No base with impulsive departure in lookback")])


def engine_c_liquidity(bars: list[Bar]) -> EngineResult:
    if len(bars) < 40:
        return EngineResult("C.liquidity", Verdict.NOT_PRESENT, 0, Direction.NONE)
    window = bars[-40:]
    hi, lo = max(b.high for b in window), min(b.low for b in window)
    price = bars[-1].close
    tol = atr(bars, 9) * 0.22
    eq_highs = any(abs(b.high - hi) < tol for b in window[:-5])
    eq_lows = any(abs(b.low - lo) < tol for b in window[:-5])
    reasons = [Reason("C.pw", f"40-bar range high {hi:.5g} / low {lo:.5g}")]
    evidence = [EvidenceLevel(hi, "Buy-side liquidity (range high)", "level"),
                EvidenceLevel(lo, "Sell-side liquidity (range low)", "level")]
    if eq_highs:
        reasons.append(Reason("C.eqh", "Equal highs near range high (resting liquidity above)"))
    if eq_lows:
        reasons.append(Reason("C.eql", "Equal lows near range low (resting liquidity below)"))
    above = price > (hi + lo) / 2
    return EngineResult("C.liquidity", Verdict.ACTIVE, 60 if (eq_highs or eq_lows) else 48,
                        Direction.NONE if not (eq_highs or eq_lows)
                        else (Direction.SHORT if above else Direction.LONG),
                        reasons, evidence, ["H4", "D1"])


def engine_d_fvg(bars: list[Bar]) -> EngineResult:
    for i in range(len(bars) - 3, len(bars) - 41, -1):
        c1, c3 = bars[i], bars[i + 2]
        if c1.high < c3.low:                       # bullish imbalance
            gap = (c1.high, c3.low)
            direction, tag = Direction.LONG, "bullish FVG"
        elif c1.low > c3.high:                     # bearish imbalance
            gap = (c3.high, c1.low)
            direction, tag = Direction.SHORT, "bearish FVG"
        else:
            continue
        mid = (gap[0] + gap[1]) / 2
        filled = any(b.low <= gap[1] and b.high >= gap[0] for b in bars[i + 3 : i + 83])
        state = "FILLED" if filled else "OPEN"
        reasons = [Reason("D.gap", f"Three-candle {tag} {gap[0]:.5g}–{gap[1]:.5g}"),
                   Reason("D.eq", f"50% equilibrium {mid:.5g}")]
        if filled:
            reasons.append(Reason("D.fill", "Gap has since been filled"))
        return EngineResult("D.fvg", Verdict.WATCHING if filled else Verdict.ACTIVE,
                            46 if filled else 71, direction, reasons,
                            [EvidenceLevel(mid, f"FVG 50% · Engine D · {state}", "zone", gap[1])],
                            ["H1", "H4"])
    return EngineResult("D.fvg", Verdict.NOT_PRESENT, 0, Direction.NONE,
                        [Reason("D.none", "No three-candle imbalance in lookback")])


def engine_e_order_blocks(bars: list[Bar]) -> EngineResult:
    a = atr(bars)
    for i in range(len(bars) - 2, 4, -1):
        ob, dep = bars[i], bars[i + 1]
        body = abs(dep.close - dep.open)
        if body < 1.4 * a:
            continue
        if dep.close > dep.open and ob.close < ob.open:
            tag, direction, lo, hi = "bullish OB", Direction.LONG, ob.low, ob.high
        elif dep.close < dep.open and ob.close > ob.open:
            tag, direction, lo, hi = "bearish OB", Direction.SHORT, ob.low, ob.high
        else:
            continue
        mitigated = any(b.low <= hi and b.high >= lo for b in bars[i + 2 :])
        state = "MITIGATED" if mitigated else "FRESH"
        return EngineResult("E.order_block", Verdict.WATCHING if mitigated else Verdict.ACTIVE,
                            52 if mitigated else 74, direction,
                            [Reason("E.ob", f"Last opposing candle before displacement ({tag})"),
                             Reason("E.state", f"OB is {state}")],
                            [EvidenceLevel((lo + hi) / 2, f"Order block · Engine E · {state}", "zone", hi)],
                            ["H1", "H4"])
    return EngineResult("E.order_block", Verdict.NOT_PRESENT, 0, Direction.NONE)


FIB_LEVELS = (0.0, 23.6, 38.2, 50.0, 61.8, 70.5, 71.0, 78.6, 100.0)


def engine_f_ote(bars: list[Bar]) -> EngineResult:
    leg = impulse_leg(bars)
    if leg is None:
        return EngineResult("F.ote", Verdict.NOT_PRESENT, 0, Direction.NONE)
    start, end = leg
    lo, hi = min(start.low, end.low), max(start.high, end.high)
    if hi == lo:
        return EngineResult("F.ote", Verdict.NOT_PRESENT, 0, Direction.NONE)
    price = bars[-1].close
    direction = Direction.LONG if end.close > start.close else Direction.SHORT
    retr = (hi - price) / (hi - lo) if direction == Direction.LONG else (price - lo) / (hi - lo)
    in_band = 0.62 <= retr <= 0.79
    fib = hi - (hi - lo) * 0.705 if direction == Direction.LONG else lo + (hi - lo) * 0.705
    evidence = [EvidenceLevel(fib, "71% / OTE band", "level")]
    reasons = [Reason("F.leg", f"Leg {start.low:.5g} → {end.high:.5g}"),
               Reason("F.retr", f"Current retracement {retr:.1%} of leg"),
               Reason("F.band", "Price inside 70.5–71 OTE band" if in_band
                      else f"Outside OTE band ({retr:.1%})")]
    return EngineResult("F.ote", Verdict.ACTIVE if in_band else Verdict.WATCHING,
                        76 if in_band else 44, direction, reasons, evidence, ["H4"])


def engine_g_crt(bars: list[Bar]) -> EngineResult:
    if len(bars) < 3:
        return EngineResult("G.crt", Verdict.NOT_PRESENT, 0, Direction.NONE)
    prior, cur = bars[-2], bars[-1]
    swept_high = cur.high > prior.high and cur.close < prior.high
    swept_low = cur.low < prior.low and cur.close > prior.low
    if swept_high:
        direction, txt = Direction.SHORT, "Swept prior high, closed back inside range"
    elif swept_low:
        direction, txt = Direction.LONG, "Swept prior low, closed back inside range"
    else:
        return EngineResult("G.crt", Verdict.NOT_PRESENT, 0, Direction.NONE,
                            [Reason("G.none", "No prior-range sweep on last candle")])
    return EngineResult("G.crt", Verdict.ACTIVE, 69, direction,
                        [Reason("G.sweep", txt),
                         Reason("G.range", f"Prior range {prior.low:.5g}–{prior.high:.5g}")],
                        [EvidenceLevel(prior.high, "CRT prior high", "level"),
                         EvidenceLevel(prior.low, "CRT prior low", "level")], ["H1", "H4"])


def _rsi(bars: list[Bar], period: int = 14) -> list[float]:
    if len(bars) < period + 1:
        return []
    out, gains, losses = [], [], []
    for prev, cur in zip(bars, bars[1:]):
        ch = cur.close - prev.close
        gains.append(max(ch, 0.0)); losses.append(max(-ch, 0.0))
    for i in range(period, len(gains) + 1):
        g, l = mean(gains[i - period : i]), mean(losses[i - period : i])
        out.append(100.0 if l == 0 else 100 - 100 / (1 + g / l))
    return out


def engine_i_divergence(bars: list[Bar]) -> EngineResult:
    rsi = _rsi(bars)
    if len(rsi) < 10:
        return EngineResult("I.divergence", Verdict.NOT_PRESENT, 0, Direction.NONE)
    tail = bars[-len(rsi):]
    # last two price pivot highs / lows in the RSI window
    ph = [i for i in range(2, len(tail) - 2)
          if tail[i].high == max(b.high for b in tail[i - 2 : i + 3])]
    pl = [i for i in range(2, len(tail) - 2)
          if tail[i].low == min(b.low for b in tail[i - 2 : i + 3])]
    if len(ph) >= 2:
        i1, i2 = ph[-2], ph[-1]
        if tail[i2].high > tail[i1].high and rsi[i2] < rsi[i1]:
            return EngineResult("I.divergence", Verdict.ACTIVE, 67, Direction.SHORT,
                                [Reason("I.bear", "Bearish regular divergence: higher price high, lower RSI high")],
                                [EvidenceLevel(tail[i2].high, "Divergence pivot high", "level")], ["H4"])
    if len(pl) >= 2:
        i1, i2 = pl[-2], pl[-1]
        if tail[i2].low < tail[i1].low and rsi[i2] > rsi[i1]:
            return EngineResult("I.divergence", Verdict.ACTIVE, 67, Direction.LONG,
                                [Reason("I.bull", "Bullish regular divergence: lower price low, higher RSI low")],
                                [EvidenceLevel(tail[i2].low, "Divergence pivot low", "level")], ["H4"])
    return EngineResult("I.divergence", Verdict.NOT_PRESENT, 0, Direction.NONE,
                        [Reason("I.none", "No RSI divergence in lookback")])


ENGINES = (engine_a_structure, engine_b_supply_demand, engine_c_liquidity,
           engine_d_fvg, engine_e_order_blocks, engine_f_ote, engine_g_crt,
           engine_i_divergence)


def run_all_engines(bars: list[Bar]) -> list[EngineResult]:
    return [fn(bars) for fn in ENGINES]


GROUPS = ("STRUCTURE", "LOCATION", "LIQUIDITY", "ZONES", "TIMING")
_GROUP_ENGINES = {"STRUCTURE": ("A.structure",), "LOCATION": ("F.ote",),
                  "LIQUIDITY": ("C.liquidity",),
                  "ZONES": ("B.supply_demand", "D.fvg", "E.order_block"),
                  "TIMING": ("G.crt", "I.divergence")}
# How much each group counts toward a direction. Structure leads because it is
# the only group that reads trend rather than a local pattern; timing is
# corroboration, so it can never carry a direction alone.
GROUP_WEIGHTS = {"STRUCTURE": 1.5, "ZONES": 1.25, "LOCATION": 1.0,
                 "LIQUIDITY": 1.0, "TIMING": 0.75}
# An engine below this contributes nothing, whatever its group's weight.
MIN_ENGINE_STRENGTH = 60.0
# A side must lead by at least this share of the total to be actionable. Below
# it the engines disagree and the honest answer is no direction.
MIN_DIRECTION_EDGE = 0.15


@dataclass(frozen=True)
class DirectionVote:
    """Outcome of collapsing the engine set into one actionable direction."""
    direction: Direction            # LONG, SHORT, or NONE when there is no edge
    bull: float
    bear: float
    edge: float
    groups: dict[str, str]
    reasons: list[str] = field(default_factory=list)

    @property
    def actionable(self) -> bool:
        return self.direction != Direction.NONE


def group_vote(results: list[EngineResult],
               min_strength: float = MIN_ENGINE_STRENGTH,
               min_edge: float = MIN_DIRECTION_EDGE) -> DirectionVote:
    """Collapse engine verdicts into a direction, one vote per group.

    The planner previously asked only `any engine says SHORT`, so a single
    strength-60+ SHORT engine outvoted four LONG ones and every symbol with no
    bearish engine silently defaulted to LONG.  Measured across 126 tradable
    symbols that resolved 73% of them SHORT regardless of the evidence, and
    overturned a LONG majority on 55 symbol/timeframe pairs.

    Each group contributes its best qualifying engine once, weighted by
    GROUP_WEIGHTS, so three zone engines agreeing is worth one ZONES vote
    rather than three.  Ties and thin edges return NONE: no signal is a
    distinct outcome from a long signal, and conflating them is what made the
    old default read as conviction it had not earned.
    """
    by_id = {r.engine_id: r for r in results}
    bull = bear = 0.0
    groups: dict[str, str] = {}
    reasons: list[str] = []

    for group in GROUPS:
        qualifying = [by_id[e] for e in _GROUP_ENGINES[group]
                      if e in by_id
                      and by_id[e].verdict != Verdict.NOT_PRESENT
                      and by_id[e].direction != Direction.NONE
                      and by_id[e].strength > min_strength]
        if not qualifying:
            continue
        # One group, one vote, and the group speaks at the average strength of
        # the engines backing its side rather than their sum.  Summing would
        # make ZONES louder simply because it holds three engines instead of
        # one, which hands the largest group the largest voice for free.
        per_side: dict[str, list[float]] = {"LONG": [], "SHORT": []}
        best_for_side: dict[str, EngineResult] = {}
        for r in qualifying:
            key = "LONG" if r.direction == Direction.LONG else "SHORT"
            per_side[key].append(r.strength)
            if key not in best_for_side or r.strength > best_for_side[key].strength:
                best_for_side[key] = r
        # Breadth decides: the side with more engines behind it takes the group.
        # A group where every engine agrees is unanimous and simply votes.  Only
        # when the counts are level does average strength break the tie, so one
        # strong engine cannot outvote two weaker ones on the same side count.
        means = {k: mean(v) for k, v in per_side.items() if v}
        counts = {k: len(v) for k, v in per_side.items() if v}
        if len(counts) == 1:
            side = next(iter(counts))
        elif counts["LONG"] != counts["SHORT"]:
            side = max(counts, key=counts.get)
        elif means["LONG"] == means["SHORT"]:
            continue                       # the group cannot pick a side
        else:
            side = max(means, key=means.get)
        best = best_for_side[side]
        groups[group] = side
        weight = GROUP_WEIGHTS[group] * means[side]
        if side == "LONG":
            bull += weight
        else:
            bear += weight
        agreeing = [r for r in qualifying
                    if (r.direction == Direction.LONG) == (side == "LONG")]
        detail = f"{group} {side} ({best.engine_id} {best.strength:g}"
        if len(agreeing) > 1:
            detail += f", {len(agreeing)} agreeing"
        reasons.append(detail + ")")

    total = bull + bear
    if total <= 0:
        return DirectionVote(Direction.NONE, bull, bear, 0.0, groups,
                             ["No engine cleared the strength threshold — "
                              "there is no trade here, which is not the same as a long."])

    edge = (bull - bear) / total
    leader = Direction.LONG if bull > bear else Direction.SHORT
    if abs(edge) < min_edge:
        return DirectionVote(
            Direction.NONE, bull, bear, edge, groups,
            reasons + [f"Sides are within {abs(edge):.0%} of each other "
                       f"({bull:.0f} vs {bear:.0f}); too close to act on."])
    return DirectionVote(leader, bull, bear, edge, groups, reasons)


def scorecard(results: list[EngineResult]) -> dict[str, int | None]:
    by_id = {r.engine_id: r for r in results}
    out: dict[str, int | None] = {}
    for group, ids in _GROUP_ENGINES.items():
        vals = [by_id[i].strength for i in ids if i in by_id and by_id[i].verdict != Verdict.NOT_PRESENT]
        out[group] = round(mean(vals)) if vals else None
    out["MACRO"] = None  # requires a connected macro provider; shown as '?'
    return out
