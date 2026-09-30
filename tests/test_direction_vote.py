"""Direction voting: the planner must not resolve SHORT by default.

The planner asked `any(engine says SHORT with strength > 60)` and defaulted to
LONG otherwise.  Two faults fell out of that:

  * a single bearish engine outvoted a majority of bullish ones — GBPJPY had
    A, B, E and G voting LONG and was still sent SHORT on one vote from F
  * no signal at all resolved to LONG, so "nothing found" and "found a long"
    were indistinguishable and the planner read as confident when it was empty

Measured over the 126 tradable symbols on OctaFX-Demo, the old rule resolved 94
H1 / 100 D1 to SHORT and overturned a LONG majority on 56 symbol/timeframe
pairs.  The engines themselves are symmetric; only the collapse was not.
"""
from __future__ import annotations

import pytest

from swingdesk.core import engines
from swingdesk.core.models import Direction, EngineResult, Verdict


def eng(engine_id: str, direction: str, strength: float) -> EngineResult:
    return EngineResult(engine_id, Verdict.ACTIVE, strength, Direction(direction))


# ------------------------------------------------------------- the old faults
def test_one_bearish_engine_cannot_outvote_a_bullish_majority():
    results = [eng("A.structure", "LONG", 78), eng("B.supply_demand", "LONG", 82),
               eng("E.order_block", "LONG", 74), eng("G.crt", "LONG", 69),
               eng("F.ote", "SHORT", 76)]
    vote = engines.group_vote(results)
    assert vote.direction == Direction.LONG
    assert vote.actionable


def test_no_signal_is_not_a_long_signal():
    results = [eng("A.structure", "NONE", 42)]
    vote = engines.group_vote(results)
    assert vote.direction == Direction.NONE
    assert not vote.actionable
    assert any("no trade" in r for r in vote.reasons)


def test_an_empty_result_set_abstains():
    vote = engines.group_vote([])
    assert vote.direction == Direction.NONE
    assert not vote.actionable


def test_weak_engines_do_not_vote():
    """Everything below the strength threshold is not a signal."""
    results = [eng("A.structure", "LONG", 42), eng("B.supply_demand", "SHORT", 45)]
    assert engines.group_vote(results).direction == Direction.NONE


# --------------------------------------------------------------- one per group
def test_three_agreeing_zone_engines_count_as_one_zone_vote():
    """ZONES holds three engines and must not get three times the say.

    The group contributes one GROUP_WEIGHTS entry scaled by the *average* of its
    engines.  Summing instead would hand the three-engine group the loudest
    voice on the board for free.
    """
    results = [eng("A.structure", "LONG", 78),
               eng("B.supply_demand", "LONG", 82),
               eng("D.fvg", "LONG", 71),
               eng("E.order_block", "LONG", 74),
               eng("G.crt", "LONG", 69)]
    vote = engines.group_vote(results)
    assert vote.groups["ZONES"] == "LONG"
    assert vote.bear == 0.0
    expected = (engines.GROUP_WEIGHTS["STRUCTURE"] * 78 +
                engines.GROUP_WEIGHTS["ZONES"] * ((82 + 71 + 74) / 3) +
                engines.GROUP_WEIGHTS["TIMING"] * 69)
    assert vote.bull == pytest.approx(expected)
    # Summing would have produced 305.75 here rather than 263.33.
    summed = (engines.GROUP_WEIGHTS["STRUCTURE"] * 78 +
              engines.GROUP_WEIGHTS["ZONES"] * (82 + 71 + 74) +
              engines.GROUP_WEIGHTS["TIMING"] * 69)
    assert vote.bull < summed


def test_a_group_decides_on_breadth_before_strength():
    """One strong SHORT zone must not beat two agreeing LONG zones.

    This is the same mistake the old any() rule made, one level up: taking the
    single strongest engine in a group let one bearish zone outvote two bullish
    ones.
    """
    results = [eng("B.supply_demand", "LONG", 64),
               eng("D.fvg", "LONG", 71),
               eng("E.order_block", "SHORT", 74)]
    vote = engines.group_vote(results)
    assert vote.groups["ZONES"] == "LONG"
    assert vote.direction == Direction.LONG


def test_structure_outweighs_zones():
    """A bearish trend reading outweighs three bullish zones, by design.

    STRUCTURE is the only group that reads trend rather than a local pattern,
    so it is weighted highest.  Here it leads the tally, but not by enough to
    clear the edge threshold on its own — which is the honest answer when the
    trend and the zones disagree this evenly.
    """
    results = [eng("A.structure", "SHORT", 78),
               eng("B.supply_demand", "LONG", 82),
               eng("D.fvg", "LONG", 71),
               eng("E.order_block", "LONG", 74)]
    vote = engines.group_vote(results)
    assert vote.groups["STRUCTURE"] == "SHORT"
    assert vote.groups["ZONES"] == "LONG"
    assert vote.bear > vote.bull, "the weighted structure reading must lead"
    assert engines.GROUP_WEIGHTS["STRUCTURE"] > engines.GROUP_WEIGHTS["ZONES"]
    # Trend and zones disagree, so no side is asserted.
    assert vote.direction == Direction.NONE
    assert any("too close" in r for r in vote.reasons)


def test_timing_speaks_at_average_strength_not_the_sum():
    """Two timing engines must not outvote one structure reading.

    TIMING holds G.crt and I.divergence.  Summing their strength would let a
    group that happens to have two engines outweigh STRUCTURE, which has one.
    """
    results = [eng("A.structure", "LONG", 78),
               eng("G.crt", "SHORT", 69),
               eng("I.divergence", "SHORT", 67)]
    vote = engines.group_vote(results)
    assert vote.direction == Direction.LONG
    assert vote.groups["STRUCTURE"] == "LONG"
    assert vote.groups["TIMING"] == "SHORT"


def test_timing_breaks_a_deadlock_between_two_real_groups():
    """It cannot decide alone, but it can break a tie the others left."""
    results = [eng("A.structure", "LONG", 78),
               eng("F.ote", "SHORT", 76),
               eng("G.crt", "LONG", 69)]
    vote = engines.group_vote(results)
    assert vote.direction == Direction.LONG
    assert vote.groups["TIMING"] == "LONG"


# ----------------------------------------------------------------- thin edges
def test_a_narrow_edge_abstains():
    """Structure LONG against two SHORT zones is too evenly split to act on."""
    results = [eng("A.structure", "LONG", 78),
               eng("B.supply_demand", "SHORT", 82),
               eng("E.order_block", "SHORT", 74)]
    vote = engines.group_vote(results)
    assert abs(vote.edge) < engines.MIN_DIRECTION_EDGE
    assert vote.direction == Direction.NONE
    assert any("too close" in r for r in vote.reasons)


def test_min_edge_is_configurable():
    results = [eng("A.structure", "LONG", 78),
               eng("B.supply_demand", "SHORT", 82),
               eng("E.order_block", "SHORT", 74)]
    vote = engines.group_vote(results)
    assert not vote.actionable
    assert engines.group_vote(results, min_edge=0.0).actionable


def test_a_cleared_edge_is_actionable_and_reports_its_evidence():
    results = [eng("A.structure", "LONG", 78),
               eng("B.supply_demand", "LONG", 82),
               eng("D.fvg", "LONG", 74),
               eng("G.crt", "LONG", 69),
               eng("F.ote", "SHORT", 76)]
    vote = engines.group_vote(results)
    assert vote.actionable
    assert vote.direction == Direction.LONG
    assert vote.edge > engines.MIN_DIRECTION_EDGE
    assert vote.groups["STRUCTURE"] == "LONG"
    assert vote.groups["ZONES"] == "LONG"
    assert vote.groups["LOCATION"] == "SHORT"
    assert any("ZONES" in r for r in vote.reasons)


def test_a_majority_of_groups_beats_one_opposing_group():
    """The GBPJPY case: three groups LONG, one SHORT, must resolve LONG."""
    results = [eng("A.structure", "LONG", 78),
               eng("B.supply_demand", "LONG", 82),
               eng("E.order_block", "LONG", 74),
               eng("G.crt", "LONG", 69),
               eng("F.ote", "SHORT", 76)]
    vote = engines.group_vote(results)
    assert vote.direction == Direction.LONG
    assert sum(1 for s in vote.groups.values() if s == "LONG") == 3


def test_not_present_engines_are_excluded():
    results = [eng("A.structure", "SHORT", 78),
               EngineResult("B.supply_demand", Verdict.NOT_PRESENT, 0, Direction.NONE),
               eng("G.crt", "LONG", 69)]
    vote = engines.group_vote(results)
    assert "ZONES" not in vote.groups
