# Swing Desk — Button Map

Every interactive control in the application, what it is connected to, and the
observable result (all verified by automated tests in `tests/`).

Legend: ✅ = covered by a pytest-qt test · 🔁 = re-renders live data · 💾 = persisted

## Global shell

| Control | Connected to | Behaviour | |
|---|---|---|---|
| Sidebar nav: **Radar** | `MainWindow.navigate("radar")` | Switches `QStackedWidget` to the Radar page, marks button active | ✅ |
| Sidebar nav: **Markets** | `navigate("markets")` | as above | ✅ |
| Sidebar nav: **Evidence** | `navigate("evidence")` | as above | ✅ |
| Sidebar nav: **Plans** | `navigate("plans")` | as above | ✅ |
| Sidebar nav: **Positions** | `navigate("positions")` | as above | ✅ |
| Sidebar nav: **Journal** | `navigate("journal")` | as above | ✅ |
| Sidebar nav: **Performance** | `navigate("performance")` | as above | ✅ |
| Sidebar nav: **Calendar** | `navigate("calendar")` | as above | ✅ |
| Sidebar nav: **Alerts** | `navigate("alerts")` | as above (badge shows rule count) | ✅ |
| Sidebar nav: **Weekly Board** | `navigate("weekly")` | as above | ✅ |
| Sidebar nav: **Broker** | `navigate("broker")` | as above | ✅ |
| Sidebar nav: **Settings** | `navigate("settings")` | as above | ✅ |
| Keyboard **Ctrl+1 … Ctrl+9** | `QShortcut` per page | Navigates to the corresponding page | ✅ |
| Status footer | 1-second timer | DEMO ADAPTER status + live NY/LON/SAST clocks | 🔁 |

## Radar page

| Control | Behaviour | |
|---|---|---|
| **Refresh scan** | Re-runs engine scan over the demo universe; updates scan counter/timestamp; re-renders opportunity list and scorecard; toast confirmation | ✅ 🔁 |
| **New thesis** | Navigates to the Planner | ✅ |
| Opportunity row **Evidence** button (one per ranked market) | Sets the active market, navigates to Evidence — chart loads *that* symbol | ✅ |
| Active-thesis card **Open planner** | Navigates to the Planner (card hidden when no thesis exists → honest empty state) | ✅ |

## Markets page

| Control | Behaviour | |
|---|---|---|
| **Scope** combo (All broker symbols / Market Watch / Mapped / Active setups) | Filters the table; count label always shows *shown of total* + Market Watch count — scopes never conflated | ✅ |
| **Search** box | Live filter on broker symbol and canonical name | ✅ |
| **Asset class** combo | Filters FX/CFD | ✅ |
| **Refresh** | Advances demo prices, re-renders table, preserves the current scope | ✅ 🔁 |
| Table **row select / double-click** | Selects market; double-click opens Evidence for it | ✅ |
| **View evidence** | Sets active market from selection → Evidence page | ✅ |
| **Toggle Market Watch** | Flips the symbol's `visible` flag (symbol_select parity) and re-renders | ✅ |
| **Build plan** | Sets active market → Planner with that instrument selected | ✅ |

## Evidence page

| Control | Behaviour | |
|---|---|---|
| **Market** combo | Rebinds chart, evidence stack and layers to the selected symbol — never a default (§20 failure prevented) | ✅ |
| **Timeframe** buttons M15/H1/H4/D1/W1 | Reloads bars + engine results for that timeframe; exclusive checkable group | ✅ |
| **Fit chart** | Resets zoom to fit the visible window | ✅ |
| **Export chart (PNG)** | Saves the chart image to the exports folder, toast shows the file | ✅ |
| **Create thesis** | Sets active market → Planner | ✅ |
| **Layer** checkboxes (Structure, Liquidity, S&D, FVG, Order blocks, Targets) | Toggles engine evidence layers on the chart | ✅ |
| Chart **wheel / drag / hover** | Zoom, pan, crosshair with OHLC + timestamp tooltip | — |

## Plans page (planner + lifecycle board)

| Control | Behaviour | |
|---|---|---|
| Form fields (instrument, direction, entry, stop, target, risk %) | Every change recomputes sizing live: max loss, volume from broker contract math, actual risk, R:R, warnings | ✅ 🔁 |
| **Use engine levels** | Fills entry/stop/target from the Engine B zone and engine direction votes | ✅ |
| **Run pre-flight** | Recomputes and gates through `order_check`; toast PASSED / FAILED with reason | ✅ |
| **Save plan** | Validates level ordering for direction, computes volume, snapshots all engine results, persists to SQLite, plan appears on the board in THESIS | ✅ 💾 |
| Lifecycle board **→ NEXT-STATE** buttons (per plan) | Validated transitions only (`LIFECYCLE_TRANSITIONS`); OPEN/TRIGGERED require explicit confirmation; CLOSED stamps close time | ✅ 💾 |
| Plan card **Journal** | Navigates to the Journal for review | ✅ |
| Plan card **Delete** | Confirmation-gated delete from the database | ✅ |

## Positions page

| Control | Behaviour | |
|---|---|---|
| Row **Close** | Confirmation dialog → removes demo position; any linked OPEN/MANAGING plan is reconciled to CLOSED with actual fill and realised R | ✅ 💾 |
| **Close all (typed confirm)** | Requires typing `CLOSE ALL`; wrong input cancels | ✅ |
| **Refresh** | Re-renders positions, portfolio risk and thesis monitor | ✅ 🔁 |

## Journal page

| Control | Behaviour | |
|---|---|---|
| **Export journal (CSV)** | Writes every closed/reviewed plan with plan-vs-actual values to the exports folder | ✅ |
| Review form (plan selector, 5 behaviour-flag checkboxes, note) | **Complete review** moves the plan CLOSED → REVIEW, stores flags and note | ✅ 💾 |

## Performance page

| Control | Behaviour | |
|---|---|---|
| **Export report (Markdown)** | Win rate, expectancy, total R, per-market/direction/behaviour tables — computed only from stored closed plans; honest empty state when none | ✅ |

## Calendar page

| Control | Behaviour | |
|---|---|---|
| Per-event **Alert me** | Arms a price alert on the first affected discovered instrument for the event window | ✅ 💾 |
| Clock boxes | Live zone-aware clocks (New York / London / Johannesburg / Frankfurt) | 🔁 |

## Alerts page

| Control | Behaviour | |
|---|---|---|
| **Use current price** | Sets the level field to the current demo bid | ✅ |
| **Create alert** | Persists a deterministic price-cross rule (≥ or ≤ level) | ✅ 💾 |
| Rule **Pause / Resume** | Toggles the rule; resume re-arms a fired alert | ✅ 💾 |
| Rule **Delete** | Removes the rule | ✅ 💾 |
| Alert log | Fired alerts are written to SQLite and shown with timestamps; the 3-second demo tick loop evaluates armed rules against live demo prices | ✅ 🔁 |

## Weekly Board page

| Control | Behaviour | |
|---|---|---|
| **Export board (Markdown)** | Events, computed markets-to-watch and live plan counts → exports folder | ✅ |

## Broker page

| Control | Behaviour | |
|---|---|---|
| **Choose terminal64.exe…** | Native file dialog; path persisted; label shows the choice; local mode continues if cancelled | ✅ 💾 |
| **Try real MT5 (Windows)** | Attempts the real `MetaTrader5` package: CONNECTED / NOT LOGGED IN / unavailable, each with the precise next action | ✅ |
| **Refresh discovery** | Re-renders universe counts (all vs Market Watch shown separately), timeframes, account figure and the selected contract | ✅ 🔁 |

## Settings page

| Control | Behaviour | |
|---|---|---|
| **Theme** combo (Obsidian / Paper / Terminal) | Applies the full QSS theme live across the app | ✅ 💾 |
| **Density** combo (Comfort / Compact / Terminal) | Re-applies spacing/typography live | ✅ 💾 |
| **Brand orbit animation** checkbox | Starts/stops the animated brand frame | 💾 |
| Default risk %, Start page | Stored; start page honoured on next launch | ✅ 💾 |
| **Save settings** | Persists all settings locally, toast confirmation | ✅ 💾 |
| **Export diagnostics** | Writes a JSON diagnostic bundle (mode, universe size, paths, settings) to exports | ✅ |
