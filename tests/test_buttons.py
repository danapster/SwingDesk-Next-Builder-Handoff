"""Button-behaviour tests: every action button produces an observable result."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from swingdesk.core import demo_data
from swingdesk.core.models import (Direction, EngineResult, LifecycleState,
                                   UniverseScope, Verdict)
from swingdesk.core.store import now_iso


# ------------------------------------------------------------------- radar
def test_radar_refresh_updates_scan_timestamp(make_app):
    win = make_app()
    page = win.pages["radar"]
    before = page.scan_label.text()
    page.btn_refresh.click()
    assert page.scan_label.text() != before
    assert "Scan #" in page.scan_label.text()


def test_radar_new_thesis_navigates_to_plans(make_app):
    win = make_app()
    win.navigate("radar")
    win.pages["radar"].btn_new_thesis.click()
    assert win.stack.currentWidget() is win.pages["plans"]


def test_radar_opportunity_opens_evidence_for_that_market(make_app):
    win = make_app()
    win.navigate("radar")
    page = win.pages["radar"]
    # every opportunity row carries an Evidence button; click the first one
    btn = page.opp_card.findChildren(type(page.btn_refresh))[0]
    btn.click()
    assert win.stack.currentWidget() is win.pages["evidence"]
    assert win.ctx.active_symbol is not None
    ev = win.pages["evidence"]
    assert ev.symbol_combo.currentData() == win.ctx.active_symbol.broker_symbol


# ----------------------------------------------------------------- markets
def test_markets_scopes_do_not_conflate(make_app):
    win = make_app()
    page = win.pages["markets"]
    total = len(demo_data.universe())
    mw = sum(1 for r in demo_data.universe() if r.visible_in_market_watch)
    page.scope_combo.setCurrentIndex(0)  # ALL
    assert page.table.rowCount() == total
    page.scope_combo.setCurrentIndex(1)  # MARKET_WATCH
    assert page.table.rowCount() == mw
    assert page.table.rowCount() != total or mw == total  # scopes are distinct
    assert "never conflated" in page.count_label.text()


def test_markets_search_filters(make_app):
    win = make_app()
    page = win.pages["markets"]
    page.search.setText("gold")
    assert 1 <= page.table.rowCount() <= 3
    page.search.setText("zzzznope")
    assert page.table.rowCount() == 0


def test_markets_toggle_watch(make_app):
    win = make_app()
    page = win.pages["markets"]
    # select a known row: find Gold
    for i in range(page.table.rowCount()):
        if page.table.item(i, 0).text() == "XAUUSD.m":
            page.table.setCurrentCell(i, 0)
            break
    before = demo_data.symbol("XAUUSD.m").visible_in_market_watch
    page.btn_watch.click()
    after = demo_data.symbol("XAUUSD.m").visible_in_market_watch
    assert after != before


def test_markets_view_evidence_button(make_app):
    win = make_app()
    win.navigate("markets")
    page = win.pages["markets"]
    page.table.setCurrentCell(0, 0)
    page.btn_view.click()
    assert win.stack.currentWidget() is win.pages["evidence"]


def test_markets_non_first_symbol_opens_matching_evidence(make_app):
    win = make_app()
    win.navigate("markets")
    markets = win.pages["markets"]

    wanted_row = -1
    wanted_symbol = ""
    for row in range(markets.table.rowCount()):
        symbol = markets.table.item(row, 0).text()
        if symbol != markets.table.item(0, 0).text():
            wanted_row = row
            wanted_symbol = symbol
            break

    assert wanted_row >= 0, "need at least two discovered markets"
    markets.table.setCurrentCell(wanted_row, 0)
    markets.btn_view.click()

    assert win.stack.currentWidget() is win.pages["evidence"]
    ev = win.pages["evidence"]
    assert ev.symbol_combo.currentData() == wanted_symbol
    assert win.ctx.active_symbol is not None
    assert win.ctx.active_symbol.broker_symbol == wanted_symbol
    assert wanted_symbol in ev.freshness.text()


# ---------------------------------------------------------------- evidence
def test_evidence_chart_bound_to_selection_not_first_symbol(make_app):
    """§20: the chart must follow the selected market, never a default."""
    win = make_app()
    ev = win.pages["evidence"]
    gold = demo_data.symbol("XAUUSD.m")
    win.ctx.set_active_symbol(gold)
    assert "Gold" in ev.chart.watermark()
    nas = demo_data.symbol("USTEC.cash")
    ev.symbol_combo.setCurrentIndex(ev.symbol_combo.findData(nas.broker_symbol))
    assert "Nasdaq" in ev.chart.watermark()
    assert ev.chart._bars, "chart has bars for the selected symbol"


def test_evidence_keeps_selected_broker_symbol_across_live_snapshot_refresh(make_app, monkeypatch):
    """Live bid/ask changes must not reset Evidence to the first combo item."""
    from dataclasses import replace

    win = make_app()
    ev = win.pages["evidence"]

    original = demo_data.symbol("XAUUSD.m")
    assert original is not None
    fresh = replace(original, bid=original.bid + 1.25, ask=original.ask + 1.25)

    real_universe = demo_data.universe
    snapshot = []
    for rec in real_universe():
        snapshot.append(fresh if rec.broker_symbol == original.broker_symbol else rec)

    monkeypatch.setattr(demo_data, "universe", lambda: list(snapshot))
    monkeypatch.setattr(
        demo_data,
        "symbol",
        lambda broker_symbol: next(
            (r for r in snapshot if r.broker_symbol == broker_symbol), None
        ),
    )

    win.ctx.set_active_symbol(original)

    assert ev.symbol_combo.currentData() == "XAUUSD.m"
    current = ev.current_record()
    assert current is fresh
    assert "Gold" in ev.chart.watermark()


def test_evidence_timeframe_buttons_change_chart(make_app):
    win = make_app()
    ev = win.pages["evidence"]
    for b in ev._tf_group.buttons():
        if b.text() == "H4":
            b.click()
    assert ev.chart.watermark().endswith("H4")
    assert ev.timeframe == "H4"


def test_evidence_fit_button(make_app):
    win = make_app()
    ev = win.pages["evidence"]
    ev.chart._count = 30
    ev.btn_fit.click()
    assert ev.chart._count > 30


def test_evidence_export_chart_creates_png(make_app):
    win = make_app()
    ev = win.pages["evidence"]
    ev.btn_snapshot.click()
    files = list(Path(win.ctx.exports_dir()).glob("chart-*.png"))
    assert files, "chart PNG was not written"


def test_evidence_layers_toggle(make_app):
    win = make_app()
    ev = win.pages["evidence"]
    with_all = len(ev.active_layers())
    ev.layer_checks["Structure"].setChecked(False)
    assert len(ev.active_layers()) < with_all


def test_evidence_create_thesis_goes_to_plans(make_app):
    win = make_app()
    win.navigate("evidence")
    win.pages["evidence"].btn_thesis.click()
    assert win.stack.currentWidget() is win.pages["plans"]


# ------------------------------------------------------------------- plans
def _fill_plan_form(page, entry=1.0831, stop=1.0781, target=1.0991):
    for i in range(page.symbol_combo.count()):
        if page.symbol_combo.itemData(i) == "EURUSD.a":
            page.symbol_combo.setCurrentIndex(i)
            break
    page.direction.setCurrentText("LONG")
    page.entry.setValue(entry)
    page.stop.setValue(stop)
    page.target.setValue(target)


def test_plans_use_engine_levels_button(make_app, monkeypatch):
    """The button fills a bracket from real engine votes.

    The default instrument is not guaranteed to have an actionable direction —
    group_vote abstains when the evidence is thin — and then the button
    correctly refuses rather than filling a guess. Drive it with a known set so
    this asserts the fill path, not today's market.
    """
    win = make_app()
    page = win.pages["plans"]
    assert page.entry.value() == 0

    fakes = [EngineResult(engine_id=e, verdict=Verdict.ACTIVE, strength=s,
                          direction=Direction.LONG, evidence=[])
             for e, s in (("A.structure", 78), ("B.supply_demand", 82),
                          ("D.fvg", 71), ("E.order_block", 74), ("G.crt", 69))]
    monkeypatch.setattr(demo_data, "engine_results", lambda *_a, **_k: fakes)
    page.btn_fill.click()
    assert page.entry.value() != 0 and page.stop.value() != 0
    assert page.direction.currentText() == "LONG"
    assert page.stop.value() < page.entry.value() < page.target.value()


def test_plans_compute_sizing_visible(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    assert page._check_state is not None
    assert "order_check" in page._check_state.text()


def test_plans_save_persists_and_appears_on_board(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.thesis_text.setPlainText("W1+D1 aligned, demand zone entry.")
    n_before = len(win.ctx.store.plans())
    page.btn_save.click()
    plans = win.ctx.store.plans()
    assert len(plans) == n_before + 1
    plan = plans[0]
    assert plan.state == LifecycleState.THESIS
    assert plan.volume > 0
    assert json.loads(plan.engine_snapshot)  # engine reasons snapshotted
    # board shows it with a transition button
    btns = [b for b in page.board.findChildren(type(page.btn_save))
            if b.text().startswith("→")]
    assert btns, "lifecycle transition button missing"


def test_plans_full_lifecycle_with_validated_transitions(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    plan_id = win.ctx.store.plans()[0].id

    def click_transition(label):
        for b in page.board.findChildren(type(page.btn_save)):
            if b.text() == label:
                b.click()
                return True
        return False

    assert click_transition("→ WAITING")
    assert win.ctx.store.plans()[0].state == LifecycleState.WAITING
    assert click_transition("→ TRIGGERED")
    assert click_transition("→ OPEN")
    assert click_transition("→ CLOSED")
    plan = win.ctx.store.plans()[0]
    assert plan.state == LifecycleState.CLOSED and plan.closed_at


def test_plans_illegal_transition_blocked(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    # THESIS can only go to WAITING/SCANNING; calling OPEN directly must not apply
    page.transition(win.ctx.store.plans()[0].id, LifecycleState.OPEN)
    assert win.ctx.store.plans()[0].state == LifecycleState.THESIS


def test_plans_delete(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    pid = win.ctx.store.plans()[0].id
    page.delete_plan(pid)
    assert all(p.id != pid for p in win.ctx.store.plans())


def test_preflight_blocks_bad_levels(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page, entry=1.0831, stop=1.0831, target=1.0991)  # stop == entry
    page.btn_preflight.click()
    assert page._check_state is not None
    assert "INVALID" in page._check_state.text() or "REJECTED" in page._check_state.text()


# --------------------------------------------------------------- positions
def test_positions_close_one_moves_linked_plan_to_closed(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    # make it match the demo GBPJPY position so the close links them
    for i in range(page.symbol_combo.count()):
        if page.symbol_combo.itemData(i) == "GBPJPY.m":
            page.symbol_combo.setCurrentIndex(i)
            break
    page.direction.setCurrentText("LONG")
    page.entry.setValue(189.42); page.stop.setValue(187.9); page.target.setValue(193.82)
    page.btn_save.click()
    pid = win.ctx.store.plans()[0].id
    # fast-forward plan to OPEN
    pos_page = win.pages["positions"]
    win.pages["plans"].transition(pid, LifecycleState.WAITING)
    win.pages["plans"].transition(pid, LifecycleState.TRIGGERED)
    win.pages["plans"].transition(pid, LifecycleState.OPEN)

    n_pos = len(win.ctx.positions)
    close_btns = [b for b in pos_page.table.findChildren(type(pos_page.btn_refresh))
                  if b.text() == "Close"]
    assert close_btns, "Close buttons missing on positions table"
    close_btns[0].click()
    assert len(win.ctx.positions) == n_pos - 1
    linked = [p for p in win.ctx.store.plans() if p.id == pid]
    assert linked and linked[0].state == LifecycleState.CLOSED
    assert linked[0].realised_r is not None


def test_positions_close_all_requires_typed_confirm(make_app):
    win = make_app()
    win.navigate("positions")
    page = win.pages["positions"]
    n = len(win.ctx.positions)
    # simulate the user typing the wrong word
    win.run_confirm_typed = lambda t, x, e: False
    page.btn_close_all.click()
    assert len(win.ctx.positions) == n, "bulk close ran without correct confirmation"
    win.run_confirm_typed = lambda t, x, e: True
    page.btn_close_all.click()
    assert len(win.ctx.positions) == 0


# ----------------------------------------------------------------- journal
def test_journal_export_csv(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    pid = win.ctx.store.plans()[0].id
    page.transition(pid, LifecycleState.WAITING)
    page.transition(pid, LifecycleState.TRIGGERED)
    page.transition(pid, LifecycleState.OPEN)
    page.transition(pid, LifecycleState.CLOSED)
    win.pages["journal"].btn_export.click()
    out = Path(win.ctx.exports_dir()) / "journal.csv"
    assert out.exists() and "EUR / USD" in out.read_text()


def test_journal_review_completion(make_app):
    win = make_app()
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    pid = win.ctx.store.plans()[0].id
    page.transition(pid, LifecycleState.WAITING)
    page.transition(pid, LifecycleState.TRIGGERED)
    page.transition(pid, LifecycleState.OPEN)
    page.transition(pid, LifecycleState.CLOSED)
    jpage = win.pages["journal"]
    jpage.plan_combo.setCurrentIndex(0)
    jpage.flag_boxes["Exited early"].setChecked(True)
    jpage.note.setPlainText("Cut it early before TP2.")
    jpage.complete_review()
    plan = {p.id: p for p in win.ctx.store.plans()}[pid]
    assert plan.state == LifecycleState.REVIEW
    assert "Exited early" in plan.behaviour_flags


# ------------------------------------------------------------- performance
def test_performance_empty_state_then_real_metrics(make_app):
    win = make_app()
    perf = win.pages["performance"]
    win.navigate("performance")
    # empty state when no closed trades (never fabricated numbers)
    from PySide6.QtWidgets import QLabel
    assert any("No closed trades" in w.text() for w in perf.findChildren(QLabel))
    # close a plan with a realised R
    page = win.pages["plans"]
    _fill_plan_form(page)
    page.btn_save.click()
    pid = win.ctx.store.plans()[0].id
    for st in (LifecycleState.WAITING, LifecycleState.TRIGGERED, LifecycleState.OPEN):
        page.transition(pid, st)
    plan = {p.id: p for p in win.ctx.store.plans()}[pid]
    plan.state = LifecycleState.CLOSED
    plan.realised_r = 2.4
    plan.closed_at = now_iso()
    win.ctx.store.save_plan(plan)
    perf.refresh()
    assert any(w.text() == "1" for w in perf.findChildren(QLabel))
    assert any("+2.40R" in w.text() for w in perf.findChildren(QLabel))
    perf.btn_export.click()
    assert (Path(win.ctx.exports_dir()) / "performance-report.md").exists()


# ---------------------------------------------------------------- calendar
def test_calendar_keeps_five_visible_rows_and_scrolls(make_app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractItemView

    win = make_app()
    page = win.pages["calendar"]
    assert page.table.minimumHeight() >= 190
    assert page.table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert page.table.verticalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert page.scroll_area.widgetResizable() is True
    assert page.scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert page.scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff


def test_calendar_event_alert_button_creates_rule(make_app):
    from PySide6.QtWidgets import QPushButton
    win = make_app()
    win.navigate("calendar")
    page = win.pages["calendar"]
    n = len(win.ctx.store.alerts())
    btns = [b for b in page.table.findChildren(QPushButton) if b.text() == "Alert me"]
    assert btns, "Alert me buttons missing"
    btns[0].click()
    assert len(win.ctx.store.alerts()) == n + 1


def test_calendar_clocks_tick(make_app):
    win = make_app()
    page = win.pages["calendar"]
    page._tick_clocks()
    assert ":" in page.clock_labels["Africa/Johannesburg"].text()


# ------------------------------------------------------------------ alerts
def test_alert_create_pause_resume_delete(make_app):
    win = make_app()
    win.navigate("alerts")
    page = win.pages["alerts"]
    page.level.setValue(1.123456)
    page.note.setText("test rule")
    page.btn_create.click()
    rules = win.ctx.store.alerts()
    assert len(rules) == 1 and rules[0].enabled
    # pause
    page.toggle_rule(rules[0].id)
    assert win.ctx.store.alerts()[0].enabled is False
    # resume re-arms
    page.toggle_rule(rules[0].id)
    assert win.ctx.store.alerts()[0].enabled is True
    # delete
    page.delete_rule(rules[0].id)
    assert win.ctx.store.alerts() == []


def test_alert_fires_on_actual_price_cross(make_app):
    win = make_app()
    page = win.pages["alerts"]
    rec = demo_data.symbol("EURUSD.a")
    # arm an above-alert already satisfied by the current price: deterministic fire
    from swingdesk.ui.pages.alerts import price_alert_rule
    rule = price_alert_rule("EURUSD.a", "price_touch_above", rec.bid * 0.999, "cross test")
    win.ctx.store.save_alert(rule)
    win._tick_data()
    fired = win.ctx.store.alerts()[0]
    assert fired.fired_at is not None
    assert any("EURUSD.a" in msg for _at, msg in win.ctx.store.alert_log())


# ----------------------------------------------------------------- weekly
def test_weekly_board_exports(make_app):
    win = make_app()
    win.navigate("weekly")
    page = win.pages["weekly"]
    page.export_board()
    out = Path(win.ctx.exports_dir()) / "weekly-board.md"
    assert out.exists()
    assert "Weekly Swing Board" in out.read_text()


# ------------------------------------------------------------------ broker
def test_broker_choose_terminal_persists_path(make_app):
    win = make_app()
    win.navigate("broker")
    page = win.pages["broker"]
    page.btn_choose.click()
    assert "terminal64.exe" in win.ctx.terminal_path
    assert "terminal64.exe" in page.path_label.text()
    assert win.ctx.setting("terminal_path") == win.ctx.terminal_path


def test_broker_refresh_updates_discovery(make_app):
    win = make_app()
    page = win.pages["broker"]
    page.btn_refresh.click()
    assert "Universe" in page.disc_label.text()
    assert "Market Watch" in page.disc_label.text()  # scopes shown separately


def test_broker_mt5_unavailable_message_is_precise(make_app):
    win = make_app()
    page = win.pages["broker"]
    page.btn_test_mt5.click()
    text = page.status_detail.text()
    assert "MetaTrader5" in text and "Precise action" in text


# ---------------------------------------------------------------- settings
def test_settings_page_uses_vertical_scroller(make_app):
    from PySide6.QtCore import Qt

    win = make_app()
    page = win.pages["settings"]
    assert page.scroll_area.widgetResizable() is True
    assert page.scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert page.scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert page.scroll_area.widget() is not None


def test_settings_theme_change_applies_live(make_app):
    win = make_app()
    page = win.pages["settings"]
    page.theme_combo.setCurrentText("Paper · daylight")
    assert win.ctx.setting("theme") == "paper"
    page.theme_combo.setCurrentText("Terminal · monochrome")
    assert win.ctx.setting("theme") == "terminal"


def test_settings_density_change_applies(make_app):
    win = make_app()
    page = win.pages["settings"]
    page.density_combo.setCurrentIndex(0)  # comfort
    assert win.ctx.setting("density") == "comfort"


def test_settings_save_persists(make_app):
    win = make_app()
    page = win.pages["settings"]
    page.default_risk.setValue(2.5)
    page.btn_save.click()
    assert win.ctx.setting("default_risk") == "2.50"


def test_settings_export_diagnostics(make_app):
    win = make_app()
    page = win.pages["settings"]
    page.btn_diagnostics.click()
    out = Path(win.ctx.exports_dir()) / "diagnostics.json"
    data = json.loads(out.read_text())
    assert data["app"] == "Swing Desk"
