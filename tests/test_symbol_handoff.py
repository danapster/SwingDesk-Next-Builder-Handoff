"""Symbol handoff between Radar, Evidence and the Planner.

Guards two faults that both made the planner ignore the chosen instrument and
fall back to whatever happened to be first in the combo (visually always
EURUSD):

  1. Radar navigated to the planner without publishing the selected symbol.
  2. The planner stored whole SymbolRecord objects in the combo and matched
     with findData(record), which compares by value. The live provider rebuilds
     SymbolRecord on every tick, so a fresh bid/ask never matched the stale
     stored copy and the selection silently did not move.
"""
from __future__ import annotations

import dataclasses

import pytest

from swingdesk.core import demo_data
from swingdesk.core.models import Direction, EngineResult, Verdict


def planner_symbol(page) -> str:
    return page.symbol_combo.currentData()


def radar_rows(page):
    return demo_data.opportunity_rows()


# --------------------------------------------------------------- radar handoff
def test_plan_this_button_opens_the_chosen_pair(make_app):
    win = make_app()
    radar = win.pages["radar"]
    rows = radar_rows(radar)
    if not rows:
        pytest.skip("no evaluated opportunities in the demo universe")

    target = rows[0]["record"]
    # Pick a row that is NOT the first instrument, so a default selection fails.
    other = next((r["record"] for r in rows
                  if r["record"].broker_symbol != demo_data.universe()[0].broker_symbol),
                 None)
    if other is not None:
        target = other

    radar.open_planner(target)
    assert win.stack.currentWidget() is win.pages["plans"]
    assert planner_symbol(win.pages["plans"]) == target.broker_symbol


def test_new_thesis_uses_the_focused_pair(make_app):
    win = make_app()
    radar = win.pages["radar"]
    rows = radar_rows(radar)
    if len(rows) < 2:
        pytest.skip("need two opportunities to prove focus is honoured")

    target = rows[1]["record"]
    radar.open_evidence(target)          # focusing via Evidence
    radar.btn_new_thesis.click()

    assert win.stack.currentWidget() is win.pages["plans"]
    assert planner_symbol(win.pages["plans"]) == target.broker_symbol


def test_new_thesis_falls_back_to_top_opportunity(make_app):
    win = make_app()
    radar = win.pages["radar"]
    rows = radar_rows(radar)
    if not rows:
        pytest.skip("no evaluated opportunities in the demo universe")
    radar._focus = None
    radar.btn_new_thesis.click()
    assert planner_symbol(win.pages["plans"]) == rows[0]["record"].broker_symbol


def test_evidence_still_opens_evidence(make_app):
    win = make_app()
    radar = win.pages["radar"]
    rows = radar_rows(radar)
    if not rows:
        pytest.skip("no evaluated opportunities in the demo universe")
    target = rows[0]["record"]
    radar.open_evidence(target)
    assert win.stack.currentWidget() is win.pages["evidence"]
    assert win.ctx.active_symbol is target


# ------------------------------------------------- planner selection robustness
def test_planner_combo_stores_a_stable_broker_key(make_app):
    win = make_app()
    page = win.pages["plans"]
    keys = [page.symbol_combo.itemData(i) for i in range(page.symbol_combo.count())]
    assert all(isinstance(k, str) for k in keys), "combo must key on broker_symbol"
    assert all(k for k in keys)


def test_selection_survives_a_fresh_tick_snapshot(make_app):
    """A new bid/ask must not break the handoff."""
    win = make_app()
    page = win.pages["plans"]
    base = demo_data.symbol("GBPUSD.a")
    if base is None:
        pytest.skip("symbol unavailable in this universe")
    page.sync_symbol_selection(base)
    assert planner_symbol(page) == "GBPUSD.a"

    # Same instrument, different prices — what MT5 hands back on the next tick.
    moved = dataclasses.replace(base, bid=base.bid + 0.001, ask=base.ask + 0.001)
    assert moved != base, "records must actually differ to be a valid regression case"
    page.sync_symbol_selection(moved)
    assert planner_symbol(page) == "GBPUSD.a"


def test_form_record_resolves_the_live_symbol(make_app):
    win = make_app()
    page = win.pages["plans"]
    page.sync_symbol_selection(demo_data.symbol("XAUUSD.m"))
    rec = page.form_record()
    assert rec is not None
    assert rec.broker_symbol == "XAUUSD.m"


def test_saved_plan_keeps_the_selected_symbol(make_app, monkeypatch):
    """End-to-end: the plan that gets persisted must be the chosen pair."""
    win = make_app()
    page = win.pages["plans"]
    rec = demo_data.symbol("XAUUSD.m")
    page.sync_symbol_selection(rec)
    assert planner_symbol(page) == "XAUUSD.m"

    # Drive a known bullish vote: fill_from_engines legitimately abstains when the
    # evidence is thin, and this test is about which symbol gets persisted.
    fakes = [EngineResult(engine_id=e, verdict=Verdict.ACTIVE, strength=s,
                          direction=Direction.LONG, evidence=[])
             for e, s in (("A.structure", 78), ("B.supply_demand", 82),
                          ("D.fvg", 71), ("E.order_block", 74), ("G.crt", 69))]
    monkeypatch.setattr(demo_data, "engine_results", lambda *_a, **_k: fakes)
    page.fill_from_engines()

    # The cap has to at least afford the broker's minimum volume across the stop
    # width the engines actually produced, and that depends on live account
    # equity, which this test does not control. Derive a workable percentage so
    # the assertion stays about symbol persistence instead of risk appetite —
    # size_position rightly refuses to over-risk to satisfy a cap the instrument
    # cannot meet.
    live = page.form_record()
    distance = abs(page.entry.value() - page.stop.value())
    per_lot = distance * live.contract.tick_value / live.contract.tick_size
    needed = per_lot * live.contract.volume_min / demo_data.account_equity() * 100
    page.risk_pct.setValue(round(min(100.0, max(1.0, needed * 1.5)), 2))

    before = len(win.ctx.store.plans())
    page.save_plan()
    plans = win.ctx.store.plans()
    assert len(plans) == before + 1
    assert plans[0].broker_symbol == "XAUUSD.m"
    assert plans[0].canonical_name == rec.canonical_name


def test_unknown_symbol_does_not_move_the_selection(make_app):
    win = make_app()
    page = win.pages["plans"]
    before = planner_symbol(page)
    ghost = dataclasses.replace(demo_data.universe()[0], broker_symbol="NOPE.zzz")
    page.sync_symbol_selection(ghost)
    assert planner_symbol(page) == before
