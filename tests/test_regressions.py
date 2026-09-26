"""Regression coverage for validation, alerts, repeated renders, and safe demo state."""
from __future__ import annotations

import math
import sys
import types
from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QLabel, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from swingdesk.core import demo_data, risk
from swingdesk.core.models import ContractSpec, Direction, EngineResult, LifecycleState, Plan, Verdict
from swingdesk.core.store import Store, new_id, now_iso
from swingdesk.ui.pages.alerts import time_alert_rule
from swingdesk.ui.theme import OrbitBrand
from swingdesk.ui.widgets import clear_layout


def _contract(**overrides):
    base = dict(
        digits=5, point=0.00001, tick_size=0.00001, tick_value=1.0,
        contract_size=100000, volume_min=0.01, volume_max=100.0,
        volume_step=0.01, stops_level_points=20, freeze_level_points=0,
    )
    base.update(overrides)
    return ContractSpec(**base)


def _valid_size(contract=None):
    return risk.size_position(1.1000, 1.0950, 1.1150, 1.0, 10_000.0,
                              contract or _contract())


def _fill_valid_plan(page):
    page.direction.setCurrentText("LONG")
    page.entry.setValue(1.0831)
    page.stop.setValue(1.0781)
    page.target.setValue(1.0991)
    page.risk_pct.setValue(1.0)


# 1
def test_size_rejects_nan_entry():
    assert not risk.size_position(math.nan, 1.0, 2.0, 1, 10_000, _contract()).ok


# 2
def test_size_rejects_nonpositive_prices():
    assert not risk.size_position(0, 1.0, 2.0, 1, 10_000, _contract()).ok


# 3
def test_size_rejects_nonpositive_equity():
    assert not risk.size_position(1.1, 1.0, 1.3, 1, 0, _contract()).ok


# 4
def test_size_rejects_invalid_tick_contract():
    assert not risk.size_position(1.1, 1.0, 1.3, 1, 10_000,
                                  _contract(tick_size=0)).ok


# 5
def test_size_rejects_invalid_volume_contract():
    assert not risk.size_position(1.1, 1.0, 1.3, 1, 10_000,
                                  _contract(volume_min=2, volume_max=1)).ok


# 6
def test_size_rejects_same_side_stop_target():
    assert not risk.size_position(1.10, 1.09, 1.095, 1, 10_000, _contract()).ok


# 7
def test_size_rejects_stop_inside_stops_level():
    c = _contract(stops_level_points=50)
    assert not risk.size_position(1.10000, 1.09980, 1.11000, 1, 10_000, c).ok


# 8
def test_size_rejects_target_inside_stops_level():
    c = _contract(stops_level_points=50)
    assert not risk.size_position(1.10000, 1.09000, 1.10020, 1, 10_000, c).ok


# 9
def test_broker_minimum_cannot_silently_exceed_risk_cap():
    # A materially oversized minimum lot is a hard failure.
    c = _contract(volume_min=1.0, volume_step=0.01)
    result = risk.size_position(1.10, 1.00, 1.30, 0.1, 1_000, c)
    assert not result.ok
    assert result.actual_risk > result.risk_amount * risk.MAX_RISK_OVERAGE_FACTOR

    # A tiny broker-minimum/step overage is allowed within the same 5%
    # tolerance used elsewhere by the sizing engine.  This matches GBPJPY.m
    # at 0.01 lots in the demo lifecycle tests (~1.84% over nominal risk).
    c2 = ContractSpec(
        digits=3, point=0.001, tick_size=0.001, tick_value=6.7,
        contract_size=100000, volume_min=0.01, volume_max=100.0,
        volume_step=0.01, stops_level_points=20, freeze_level_points=0,
    )
    rounded = risk.size_position(189.42, 187.90, 193.82, 1.0, 10_000, c2)
    assert rounded.ok
    assert rounded.risk_amount < rounded.actual_risk <= rounded.risk_amount * risk.MAX_RISK_OVERAGE_FACTOR


# 10
def test_valid_size_still_passes():
    result = _valid_size()
    assert result.ok and result.volume > 0


# 11
def test_order_check_rejects_nonfinite_value():
    ok, _ = risk.order_check(math.inf, 1.0, 2.0, 0.1, _contract(), 10_000)
    assert not ok


# 12
def test_order_check_rejects_same_side_levels():
    ok, checks = risk.order_check(1.10, 1.09, 1.095, 0.1, _contract(), 10_000)
    assert not ok and any("opposite" in x for x in checks)


# 13
def test_order_check_rejects_misaligned_volume_step():
    ok, checks = risk.order_check(1.10, 1.09, 1.13, 0.015, _contract(), 10_000)
    assert not ok and any("step" in x for x in checks)


# 14
def test_order_check_rejects_target_inside_stops_level():
    c = _contract(stops_level_points=50)
    ok, checks = risk.order_check(1.1000, 1.0900, 1.1002, 0.1, c, 10_000)
    assert not ok and any("Target" in x for x in checks)


# 15
def test_alert_spinbox_accepts_high_priced_instrument(make_app):
    win = make_app()
    page = win.pages["alerts"]
    assert page.level.maximum() >= 63_000


# 16
def test_high_price_alert_is_not_clamped_to_99_99(make_app):
    win = make_app()
    page = win.pages["alerts"]
    page.level.setValue(63_128.25)
    assert page.level.value() == pytest.approx(63_128.25)


# 17
def test_time_alert_rule_persists_exact_utc_epoch():
    when = datetime(2026, 9, 27, 12, 30, tzinfo=timezone.utc)
    rule = time_alert_rule("EURUSD.a", when, "event")
    assert rule.kind == "time_event"
    assert rule.level == pytest.approx(when.timestamp())


# 18
def test_calendar_alert_uses_event_time_not_price(make_app):
    win = make_app()
    event = demo_data.calendar_events()[0]
    page = win.pages["calendar"]
    before = len(win.ctx.store.alerts())
    page.create_event_alert(event)
    rules = win.ctx.store.alerts()
    assert len(rules) == before + 1
    assert rules[0].kind == "time_event"
    assert rules[0].level == pytest.approx(event.time_utc.timestamp())


# 19
def test_due_time_alert_fires_without_market_price(make_app, monkeypatch):
    win = make_app()
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rule = time_alert_rule("MISSING.SYMBOL", past, "macro")
    win.ctx.store.save_alert(rule)
    monkeypatch.setattr(win.ctx, "current_price", lambda _symbol: 0.0)
    win._tick_data()
    stored = {r.id: r for r in win.ctx.store.alerts()}[rule.id]
    assert stored.fired_at is not None
    assert any("event time reached" in msg for _, msg in win.ctx.store.alert_log())


# 20
def test_clear_layout_recursively_removes_nested_widgets(qapp):
    host = QWidget()
    outer = QVBoxLayout(host)
    nested = QHBoxLayout()
    label = QLabel("nested")
    nested.addWidget(label)
    outer.addLayout(nested)
    clear_layout(outer)
    qapp.processEvents()
    assert outer.count() == 0
    assert label.parent() is host or label.parent() is None


# 21
def test_repeated_planner_render_does_not_accumulate_layout_items(make_app, qapp):
    win = make_app()
    page = win.pages["plans"]
    _fill_valid_plan(page)
    page.render_computed()
    first = page.computed.layout().count()
    for _ in range(5):
        page.render_computed()
        qapp.processEvents()
    assert page.computed.layout().count() == first


# 22
def test_engine_fill_short_without_zone_does_not_crash(make_app, monkeypatch):
    win = make_app()
    page = win.pages["plans"]
    fake = EngineResult(engine_id="X", verdict=Verdict.ACTIVE, strength=80,
                        direction=Direction.SHORT, evidence=[])
    monkeypatch.setattr(demo_data, "engine_results", lambda *_args, **_kwargs: [fake])
    page.fill_from_engines()
    assert page.direction.currentText() == "SHORT"
    assert page.target.value() < page.entry.value() < page.stop.value()


# 23
def test_invalid_plan_cannot_be_saved(make_app):
    win = make_app()
    page = win.pages["plans"]
    page.direction.setCurrentText("LONG")
    page.entry.setValue(1.10)
    page.stop.setValue(1.09)
    page.target.setValue(1.095)
    before = len(win.ctx.store.plans())
    page.save_plan()
    assert len(win.ctx.store.plans()) == before


# 24
def test_stored_overrisk_volume_cannot_transition_to_triggered(make_app):
    win = make_app()
    rec = demo_data.symbol("EURUSD.a")
    assert rec is not None
    p = Plan(id=new_id("plan"), broker_symbol=rec.broker_symbol,
             canonical_name=rec.canonical_name, direction="LONG",
             entry=1.0831, stop=1.0781, target=1.0991, risk_percent=1.0,
             volume=100.0, thesis="legacy unsafe volume", state=LifecycleState.WAITING,
             created_at=now_iso(), updated_at=now_iso(), engine_snapshot="[]")
    win.ctx.store.save_plan(p)
    page = win.pages["plans"]
    page.transition(p.id, LifecycleState.TRIGGERED)
    saved = {x.id: x for x in win.ctx.store.plans()}[p.id]
    assert saved.state == LifecycleState.WAITING


# 25
def test_lifecycle_board_is_horizontally_scrollable(make_app):
    win = make_app()
    page = win.pages["plans"]
    assert isinstance(page.board_scroll, QScrollArea)
    assert page.board_scroll.widgetResizable() is False
    assert page.board_scroll.maximumHeight() <= 440


# 26
def test_sidebar_brand_has_noncollapsed_size_hint(qapp):
    inner = QWidget()
    brand = OrbitBrand(inner)
    assert brand.minimumHeight() >= 72
    assert brand.sizeHint().height() >= 72
    assert brand.sizeHint().width() >= 180
    brand.deleteLater()
    qapp.processEvents()


# 27
def test_successful_mt5_probe_still_labels_demo_active(make_app, monkeypatch):
    win = make_app()
    page = win.pages["broker"]
    fake = types.SimpleNamespace(
        initialize=lambda *_args, **_kwargs: True,
        terminal_info=lambda: types.SimpleNamespace(name="Test MT5"),
        account_info=lambda: types.SimpleNamespace(login=123, balance=1000.0, currency="USD"),
        shutdown=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    page.try_real_mt5()
    assert "DEMO ACTIVE" in page.status_badge.text()
    assert "still using DEMO data" in page.status_detail.text()
