# Swing Desk — Production Build Plan

**Version:** 2.0  
**Target:** Windows 10/11 x64 desktop application  
**Distribution:** One signed Inno Setup installer containing a PyInstaller one-folder application  
**Primary integration:** MetaTrader 5 terminal installed on the trader's PC  
**Product chain:** **MARKET → THESIS → PLAN → EXECUTION → REVIEW**

---

## 0. Purpose of this handoff

This document is the clean production specification for rebuilding Swing Desk from zero. It supersedes every earlier prototype, scaffold, demo, HTML-only build, and partially wired PySide6 shell.

A builder must not inherit implementation code from those earlier attempts. The HTML and screenshots in the asset pack are visual references only. The completed desktop product must be implemented and tested as a real PySide6 application.

### 0.1 Definition of “complete”

Swing Desk is complete only when all of the following are true:

1. Every navigation item opens a real, functional page.
2. Every value shown as live data comes from MT5, a connected provider, or persisted user input.
3. There are no hard-coded example opportunities, theses, countdowns, account values, positions, events, scores, or targets in production mode.
4. The application opens with MT5 unavailable and clearly reports degradation without crashing.
5. With MT5 open and logged in, the app discovers the account, broker, full broker universe, Market Watch universe, timeframes, symbol specifications, sessions, orders, positions, deals, and bars.
6. Selecting a market loads that exact broker symbol and timeframe on the chart.
7. Engines A–I run on real bars and publish typed, explainable evidence.
8. A plan can move through its complete lifecycle and persist across restarts.
9. Risk sizing uses the broker contract and the broker validates every dispatch through `order_check`.
10. All chart controls, filters, forms, buttons, menus, tabs, tables, and dialogs have implemented behavior and automated UI tests.
11. A clean Windows build creates `SwingDesk.exe`, smoke-tests it, builds `SwingDeskSetup-<version>.exe`, installs it, launches it, and uninstalls it without deleting user data.
12. A release candidate passes the acceptance matrix in §24 on a Windows VM and on a real MT5 demo account.

A visually convincing shell is not a completed product.

---

## 1. Product intent

Swing Desk is a decision workstation for serious swing traders. It is not a signal vending machine, chatbot, browser dashboard, or collection of unrelated indicators.

It answers five questions:

1. **What** should I trade?
2. **Why** that market?
3. **Where** is price likely to react?
4. **When** should I execute?
5. **Where** are invalidation and targets?

Then it records whether the trader followed the plan and turns the result into better future decisions.

### 1.1 Non-negotiable product principles

- **Decision first.** Radar is home; chart is evidence.
- **Discovery, never assumption.** MT5 owns the broker universe and contracts.
- **Canonical presentation, literal execution.** Show EUR/USD while retaining `EURUSD.a` for broker operations.
- **Explainable deterministic logic.** No opaque AI confidence score and no LLM dependency.
- **One owner per concept.** Shared primitives are implemented once.
- **Timezone-aware.** Use IANA zones through `zoneinfo`; never fixed offsets.
- **Broker-final validation.** No dispatch without an accepted `order_check`.
- **Graceful degradation.** Local planning and journal features remain available without MT5 or network.
- **Warnings by default.** Guardian Mode is explicit opt-in.
- **No simulated production data.** Empty states are better than fabricated values.

### 1.2 Non-goals for the first sellable release

- No autonomous strategy execution.
- No cloud account requirement.
- No mobile application.
- No social feed or chat feature.
- No scraping-dependent core workflow.
- No promise of profitability.
- No broker credential storage; Swing Desk connects to the logged-in local terminal.

---

## 2. Primary user workflows

### 2.1 First launch

1. App creates `%LOCALAPPDATA%\SwingDesk` directories and database.
2. Runtime guard validates packaged NumPy/pandas/MT5 versions.
3. GUI opens immediately.
4. MT5 bridge starts as a separate copy of the same executable with `--bridge`.
5. Header shows `CONNECTING` while preserving usable local pages.
6. If MT5 is found, app discovers terminal/account/universe and shows `CONNECTED`.
7. If not found, app shows a precise action: “Open your broker’s MT5 terminal and log in,” plus a “Choose terminal64.exe” button.
8. Onboarding asks only for theme, density, display timezone set, default risk percentage, and start page.

### 2.2 Market discovery and scanning

1. Broker page shows connection, account, terminal path, server and discovery timestamp.
2. Markets page provides four explicit scopes:
   - **All broker symbols** — every `symbols_get()` result.
   - **Market Watch** — symbols where `visible` is true.
   - **Mapped** — symbols with canonical mappings.
   - **Active setups** — symbols with at least one evaluated engine not equal to `NOT_PRESENT`.
3. Search, asset-class, currency, status, timeframe-role and freshness filters are available.
4. User can enable a hidden broker symbol through `symbol_select`.
5. Refresh never silently switches scope.
6. Selected market becomes the active context for evidence, planner and alerts.

### 2.3 Evidence and chart workflow

1. Click market row.
2. Evidence page displays canonical and literal broker symbol.
3. Selected timeframe loads 500–2,000 bars incrementally.
4. Chart supports zoom, pan, crosshair, time axis, price axis, OHLC tooltip and reset.
5. Engine outputs are rendered from their evidence payloads; UI never recalculates an engine concept.
6. Layer controls display Structure, Liquidity, S&D, OB, FVG/iFVG, Fib, PD Array, Sessions, Events, Targets, Positions and Orders.
7. Hovering evidence answers “why is this here?” with engine, rule, timeframe and calculation timestamp.
8. From the evidence page the user can create or update a thesis.

### 2.4 Thesis and planning workflow

1. User starts from a radar row or market evidence page.
2. Planner snapshots all current engine outputs.
3. Why section copies engine reasons verbatim and allows user notes separately.
4. Entry area must reference an evidence zone or a user-marked zone.
5. Invalidation must reference a structural level or user-confirmed level.
6. Targets reference liquidity, measured move, prior levels or user-confirmed levels.
7. Risk engine calculates position size from the broker contract.
8. Wait Engine lists outstanding conditions.
9. User explicitly confirms transition from WATCHING to THESIS.
10. Plan persists and appears on lifecycle board.

### 2.5 Execution workflow

1. Plan becomes typed `OrderIntent`.
2. Pre-flight displays every warning/block.
3. Broker contract gates and `order_check` run.
4. Request is never sent if `order_check` fails.
5. User explicitly confirms dispatch.
6. Full request and response are journaled.
7. MT5 positions/orders are reconciled back to the plan.

### 2.6 Management and review workflow

1. Open position shows current R, planned R, next target, next event and thesis state.
2. Optional management automations are explicit per position.
3. On close, deals reconcile from MT5 history.
4. Plan moves CLOSED → REVIEW.
5. Review compares planned vs actual values and records behavior flags.
6. Performance Lab aggregates only persisted, auditable records.

---

## 3. Technology baseline

| Layer | Required choice | Release policy |
|---|---|---|
| OS | Windows 10/11 x64 | Required |
| Python build | CPython 3.11.9 x64 | Exact build baseline |
| GUI | PySide6 | Resolve exact version in Windows lock file |
| Chart | pyqtgraph | Native desktop chart |
| MT5 | MetaTrader5 Python package | Windows wheel only |
| Numerics | NumPy 1.26.4 | Exact; block NumPy 2.x |
| Dataframes | pandas 2.2.3 | Exact |
| Storage | SQLite WAL | Local, migration-controlled |
| Timezones | zoneinfo + tzdata | IANA zones |
| Secrets | Windows Credential Manager/DPAPI | No plaintext secrets |
| Freeze | PyInstaller one-folder | Do not use one-file for production |
| Installer | Inno Setup 6.3+ | Single distributable setup EXE |
| Tests | pytest + pytest-qt | Unit, integration and UI |
| Quality | ruff, black, mypy | CI gates |

### 3.1 Dependency locking

Maintain:

- `requirements.in` — human-edited direct dependencies.
- `requirements-lock-win311.txt` — exact Windows build lock generated and committed.
- `requirements-dev-lock-win311.txt` — exact test/build tools.

The release report must record resolved versions and hashes. Do not publish a release with broad ranges only.

---

## 4. Process architecture

```text
SwingDesk.exe — GUI process
  ├─ PySide6 shell and pages
  ├─ application store / event bus
  ├─ worker pool for analysis and disk reads
  ├─ SQLite repository writer
  └─ BridgeProcess supervisor
        └─ SwingDesk.exe --bridge
             ├─ token-authenticated JSONL RPC
             ├─ loopback only
             └─ sole owner of MetaTrader5 package
                    └─ broker terminal64.exe
```

### 4.1 Bridge requirements

- Bind only `127.0.0.1` on an ephemeral port.
- Use a 32-byte token stored under `%LOCALAPPDATA%\SwingDesk\bridge.token` with user-only ACL.
- Request/response IDs and structured errors.
- Server-push events or polling service for connection, tick and position changes.
- Heartbeat every 2 seconds.
- Exponential restart backoff with upper limit.
- GUI must survive bridge death.
- One MT5 API owner; no GUI-thread MT5 imports.
- Every method has an integration test against a fake adapter.

### 4.2 Required bridge RPC methods

- `ping`, `initialize`, `shutdown`, `version`
- `terminal_info`, `account_info`
- `symbols`, `symbol_info`, `symbol_select`
- `probe_timeframes`
- `tick`, `bars`, `ticks`
- `positions`, `orders`, `history_deals`, `history_orders`
- `calc_margin`, `calc_profit`
- `order_check`, `order_send`

### 4.3 Connection state machine

```text
STARTING → CONNECTING → CONNECTED
                    ↘ TERMINAL_NOT_FOUND
                    ↘ NOT_LOGGED_IN
                    ↘ DISCONNECTED
                    ↘ ERROR
```

The UI subscribes to state changes. A status label may never remain stale after a successful reconnect.

---

## 5. Discovery and normalization

### 5.1 Universe source

`symbols_get()` is authoritative. Preserve every broker record and timestamp the discovery snapshot.

Do not use a hard-coded required market list. Alias mappings help presentation only.

### 5.2 Market scopes

The UI must never confuse Market Watch with the full broker universe. Store and expose:

```python
UniverseScope.ALL
UniverseScope.MARKET_WATCH
UniverseScope.MAPPED
UniverseScope.ACTIVE_SETUPS
```

The scope is visible above every market table and persists as a setting.

### 5.3 Symbol normalization order

1. User override keyed by broker and server.
2. MT5 `currency_base` and `currency_profit` metadata.
3. Data-driven aliases.
4. Description and path evidence.
5. Asset-class heuristics.
6. `UNMAPPED` with broker literal shown unchanged.

Every record retains:

```python
broker_symbol
canonical_name
family
asset_class
base_currency
profit_currency
mapping_source
mapping_confidence
user_override
```

### 5.4 Timeframes

MT5 has constants but no universal broker timeframe declaration. Probe supported MT5 timeframe constants by requesting a small bar sample. Role-bind by measured duration:

- execution
- setup
- swing
- higher

Never require H8. Resample only when explicitly enabled and documented.

### 5.5 Contract boundary

Only `ContractSpec` reads raw MT5 symbol contract fields. Other modules use its canonical API.

Required fields include digits, point, tick size/value, contract size, volume min/max/step, stops level, freeze level, order mode, filling mode, expiration mode, trade mode, currency fields and sessions.

---

## 6. Market-data engine

- Prioritize the selected symbol.
- Incremental SQLite or Parquet-compatible cache under the application cache directory.
- Fetch with `copy_rates_from_pos` and `copy_rates_range`.
- Preserve broker bar timestamps and convert only at presentation boundaries.
- Detect stale bars, gaps, rollover discontinuities and duplicate timestamps.
- Align multi-timeframe bars without lookahead.
- Never block the GUI thread.
- A request has cancellation and generation IDs so stale worker results cannot overwrite a new selection.

### 6.1 Bar model

```python
@dataclass(frozen=True)
class Bar:
    time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int | None
    real_volume: int | None
```

---

## 7. Shared analytical primitives

Implement and test once:

- candle body, range, wicks and direction
- true range and ATR
- pivots and swing sequences
- range high/low/equilibrium
- displacement and body dominance
- breaks, reclaims and sweeps
- equal highs/lows with tick tolerance
- round-number derivation from tick size
- bar references and timestamp-safe windows
- impulse legs and retracement levels

No setup engine may copy these algorithms.

---

## 8. Setup engines A–I

Every engine returns:

```python
EngineResult(
    engine_id: str,
    verdict: ACTIVE | WATCHING | INVALID | NOT_PRESENT,
    strength: float,
    direction: LONG | SHORT | NONE,
    reasons: list[Reason],
    evidence: EvidencePayload,
    timeframes_used: list[TimeframeRef],
    computed_at: datetime,
    spec_version: str,
)
```

Strength is decomposed into visible reasons and weights. Disabled or unevaluated engines are shown as such, never coerced to zero.

### A. Structure / PO3

- HH/HL, LH/LL, range.
- Break of structure and reclaim.
- Weekly and daily prior-high/low close and sweep rules.
- Higher/setup/execution alignment.
- Output bias cards and evidence levels.

### B. Supply and Demand

- Base detection by candle body/range thresholds.
- Impulsive departure using ATR and body dominance.
- Zone proximal/distal bounds.
- Structure-break validation.
- Freshness, retest count and age.
- Higher-timeframe nesting.
- STRONG, WEAK, TESTED, PRISTINE tags.

### C. Liquidity

- Prior week/day/session highs and lows.
- Equal highs/lows.
- Swing liquidity.
- Buy-side/sell-side target map.

### D. FVG / iFVG

- Three-candle bullish and bearish imbalances.
- 50% equilibrium.
- Fill and mitigation state.
- Inverse conversion after violation and reaction.

### E. Order blocks

- Last opposing candle before validated displacement.
- Fresh, mitigation and breaker lifecycle.
- Timeframe and directional alignment.

### F. 71% / OTE

- Levels: 0, 23.6, 38.2, 50, 61.8, 70.5, 71, 78.6, 100.
- Primary 70.5–71 band and broader OTE zone.
- Auto leg and user-marked leg.
- Visible confluence checklist.

### G. CRT

- Prior-candle range sweep.
- Current close back inside prior range.
- Configurable tolerance and timeframe.
- Bar references and direction.

### H. Signature / SnDTV

- Versioned JSON/YAML rule DSL.
- Ordered conditions over shared primitives.
- Editor, validator, test runner and import/export.
- Default rule marked `OWNER-CONFIRM`; never presented as canonical.

### I. Divergence

- Price pivots against RSI and/or MACD pivots.
- Regular and hidden divergence.
- Configurable lookback and separation.
- Evidence line pairs.

---

## 9. Ranking, thesis and lifecycle

### 9.1 Least-resistance groups

- Structure
- Location
- Liquidity
- Zones
- Macro
- Timing

Display Clean, Moderate or Poor plus evidence. Weights are editable and visible. No unexplained composite score.

### 9.2 Lifecycle

```text
SCANNING → WATCHING → THESIS → WAITING → TRIGGERED
         → OPEN → MANAGING → CLOSED → REVIEW
```

Transitions are validated. Human-confirmed transitions cannot occur automatically. Persist every transition with timestamp, actor and reason.

### 9.3 Wait Engine

For an unmet entry condition, display:

> Your idea is valid. Your timing isn't here yet.

Then list concrete outstanding conditions with live values and countdowns.

---

## 10. Contract-aware risk and execution

### 10.1 Sizing

```text
loss_per_lot = stop_distance_price × trade_tick_value / trade_tick_size
risk_amount = account_equity × risk_percent / 100
raw_volume = risk_amount / loss_per_lot
volume = floor_to_volume_step(raw_volume)
volume = clamp(volume_min, volume_max)
actual_risk = volume × loss_per_lot
```

Display requested and actual risk. Never infer generic pip value.

### 10.2 Validation

- min/max/step volume
- stop and freeze levels
- market state
- trade mode
- filling and expiration mode
- margin required and remaining
- configurable policy warnings
- event blackout warning
- minimum R:R warning
- final broker `order_check`

### 10.3 Dispatch safety

- Default release starts in **paper/validation mode**.
- Live dispatch requires explicit enablement in Settings and a confirmation dialog displaying account, broker, symbol, side, volume, entry, stop, targets and maximum loss.
- Demo-account acceptance must pass before production enablement.
- Journal request and full broker response.
- Bulk actions require typed confirmation.

---

## 11. Native chart specification

Use pyqtgraph with a custom candlestick item and a timestamp-aware bottom axis.

### 11.1 Required interactions

- smooth pan and zoom
- crosshair
- OHLC/timestamp tooltip
- timeframe selector populated from discovery
- symbol selector bound to active market context
- fit/reset
- screenshot export
- drawing tool for impulse/range/zone
- layer manager
- visible data freshness timestamp

### 11.2 Evidence contract

Every drawable includes:

```python
producer_engine
rule_key
label
style_token
price/time geometry
source_bar_refs
computed_at
```

No UI-side duplicate calculations.

### 11.3 Performance

- Render only visible-window candles at high counts.
- Cache QPicture batches.
- Update current bar incrementally.
- Do not rebuild every overlay on every tick.

---

## 12. Time, sessions, calendar and macro

### 12.1 Sessions

Persist `{label, canonical_tz, start_local, end_local, weekdays, color, priority}`. Defaults:

- New York Setup 08:30–11:30 America/New_York
- New York Kill Zone 08:30–11:00 America/New_York
- London Kill Zone 08:00–10:00 Europe/London
- London Close 10:00–12:00 America/New_York
- Asian Range 20:00–00:00 America/New_York

Compute display values dynamically. Include DST transition tests for New York and London.

### 12.2 Calendar providers

- Offline CSV/JSON default.
- One configurable HTTP provider.
- FRED macro provider.
- Cache with fetch timestamp and stale badge.
- Provider failure never blocks core analysis.
- Map events to actually discovered canonical instruments.

---

## 13. Journal and Performance Lab

SQLite WAL schema includes:

- accounts and broker snapshots
- symbol mappings
- plans
- lifecycle transitions
- engine snapshots
- order intents/checks/results
- position snapshots
- deals
- journal reviews
- behavior observations
- alerts and alert deliveries
- calendar cache
- session definitions
- server-time samples
- application settings and migrations

Analytics:

- setup type
- market and asset class
- session/window
- entry type
- timeframe stack
- win rate, expectancy, average R, hold time, MAE/MFE
- behavior flags
- equity and R curves

Never recalculate historical engine evidence with future bars; use stored snapshots.

---

## 14. Alert service

Rules:

- price touch
- close above/below
- zone entry
- retracement reach
- session open/close
- event imminent
- thesis state change

Delivery:

- in-app toast
- system tray
- optional sound
- persisted log

Alerts are deterministic templates with actual state values.

---

## 15. UI design system

### 15.1 Visual direction

Use the included Edge Ledger reference language:

- fixed left sidebar
- quiet near-black canvas
- graphite panels
- warm ivory text
- muted-gold accents
- Georgia or equivalent serif hierarchy for page and card titles
- system sans for controls and body
- tabular/monospace numerals
- restrained borders instead of heavy shadows
- animated orbiting conic-gradient brand frame

Implement the orbit effect natively in Qt with a tested `QPainter` widget. The HTML CSS reference is not production code.

### 15.2 Themes

- Obsidian — default.
- Paper — warm daylight.
- Terminal — dense monochrome/professional.

### 15.3 Density

- Comfort
- Compact
- Terminal

Density changes spacing and type only.

### 15.4 Navigation implementation

Use a real `QStackedWidget` or router. Each nav button must:

- have a connected signal
- switch to a constructed page
- update active style
- preserve or intentionally reset page state
- pass a pytest-qt click test

No inert navigation controls are permitted.

### 15.5 Required pages

1. **Radar** — ranked opportunities, filters, active thesis, window and scorecard.
2. **Markets** — All/Market Watch/Mapped/Setups scopes, search and bulk enablement.
3. **Evidence** — selected market chart, layers and evidence list.
4. **Plans** — lifecycle board, plan editor and Wait Engine.
5. **Positions** — MT5 mirror, thesis monitor and confirmation-gated management.
6. **Journal** — open/closed plan reviews and screenshots.
7. **Performance** — analytics and curves.
8. **Calendar** — cached events and dual-clock views.
9. **Alerts** — rules, delivery settings and history.
10. **Weekly Board** — events, markets, plan counts and export.
11. **Broker** — connection, terminal path chooser, account, discovery and normalization.
12. **Settings** — small approved personalization surface.

### 15.6 Empty, loading and error states

Every page implements:

- loading skeleton or progress
- empty state with next action
- degraded/offline state
- recoverable error with retry
- permission or configuration state

---

## 16. Threading and responsiveness

- GUI thread performs rendering only.
- Bridge communication uses worker objects/threads or asynchronous sockets.
- Analysis uses QThreadPool with cancellation/generation IDs.
- SQLite has a single writer queue and concurrent readers.
- User changing symbol cancels stale chart/analysis requests.
- App close waits briefly for workers and then terminates safely.

Targets:

- shell visible under 3 seconds
- usable local mode under 5 seconds
- selected-symbol first chart under 2 seconds when cached
- interaction response under 100 ms

---

## 17. Local storage, security and diagnostics

```text
%LOCALAPPDATA%\SwingDesk\
├─ swingdesk.db
├─ logs\
├─ cache\
├─ exports\
├─ crash\
├─ bridge.token
└─ release.json
```

- Rotating logs, 14-day retention.
- Redact account identifiers and secrets from support export unless user opts in.
- Global Python and Qt exception hooks.
- Startup failures show a copyable dialog and write crash log.
- “Export diagnostics” bundles logs, version, dependency report and sanitized discovery metadata.

---

## 18. Clean repository architecture

```text
SwingDesk/
├─ BUILD_SWINGDESK.cmd
├─ build.ps1
├─ run_dev.ps1
├─ pyproject.toml
├─ requirements.in
├─ requirements-lock-win311.txt
├─ requirements-dev-lock-win311.txt
├─ README.md
├─ BUILD_REPORT.md
├─ ACCEPTANCE_TESTS.md
├─ CHANGELOG.md
├─ LICENSE
├─ build/
│  ├─ SwingDesk.spec
│  ├─ installer.iss
│  ├─ version_info.txt
│  ├─ app.manifest
│  └─ assets/
├─ src/swingdesk/
│  ├─ main.py
│  ├─ app.py
│  ├─ config/
│  ├─ core/primitives/
│  ├─ mt5/
│  ├─ normalize/
│  ├─ engines/
│  ├─ planning/
│  ├─ risk/
│  ├─ execution/
│  ├─ calendar/
│  ├─ journal/
│  ├─ services/
│  ├─ ui/
│  │  ├─ pages/
│  │  ├─ widgets/
│  │  ├─ charts/
│  │  └─ theme/
│  └─ resources/
└─ tests/
   ├─ unit/
   ├─ integration/
   ├─ ui/
   ├─ packaging/
   └─ fixtures/
```

No page class named only `View: pass`. No placeholder module counts as implementation.

---

## 19. Build and packaging contract

### 19.1 Production format

Use PyInstaller **one-folder**, then Inno Setup. A small launcher EXE beside `_internal` is expected in the raw build. The distributable is one setup EXE.

One-file PyInstaller is not the default because it extracts on each launch, slows bridge startup and complicates diagnostics.

### 19.2 Valid manifest

Use the tested manifest included in `build-contract/app.manifest`. Never use the malformed `<dpiaware:PerMonitorV2>` element from an earlier build.

### 19.3 Spec-path rule

If the spec is in `project/build/SwingDesk.spec` and `SPECPATH` is the build directory:

```python
project = Path(SPECPATH).parent
```

Never use `.parent.parent` without an automated assertion that the entry script exists.

### 19.4 Asset naming

The exact required icon path is:

```text
build/assets/app.ico
```

Build preflight must assert every asset before PyInstaller starts.

### 19.5 PowerShell native-process rule

PyInstaller writes normal information to stderr. The builder must not treat stderr text as failure. Determine failure only from the process exit code. Use `Start-Process -Wait -PassThru` with separate stdout/stderr logs.

### 19.6 One-click builder behavior

`BUILD_SWINGDESK.cmd`:

- starts PowerShell with ExecutionPolicy Bypass
- preserves the window
- writes logs
- calls `build.ps1`
- pauses on success or failure

`build.ps1`:

1. Windows/x64 and disk-space preflight.
2. Resolve Python 3.11 x64 without capturing package-manager prose as the executable path.
3. Create/reuse `.venv`.
4. Install from lock file only when lock hash changed.
5. Run tests and quality gates.
6. Assert source entry, manifest, version resource and assets.
7. Run PyInstaller through a native-process helper based on exit code.
8. Smoke-test `--self-test` and normal GUI startup.
9. Verify bridge child process.
10. Build Inno installer.
11. Install silently into a clean test directory.
12. Launch installed app and run smoke checks.
13. Uninstall and verify user data remains.
14. Write SHA-256 hashes and resolved versions.

### 19.7 Windows CI

A Windows Server 2022 workflow produces artifacts on every release tag. Do not call a release “ship-ready” until CI publishes:

- one-folder artifact ZIP
- Inno Setup installer
- build report
- test reports
- hashes

---

## 20. Previous-failure prevention checklist

The new builder must have automated tests for each earlier failure:

- Python 3.11 installed but not registered with `py` launcher.
- Package-manager output captured as executable path.
- PowerShell treating PyInstaller INFO stderr as fatal.
- `SPECPATH` project root one directory too high.
- Missing `build/assets/app.ico`.
- Malformed Windows manifest causing side-by-side failure.
- Frozen EXE separated from `_internal`.
- Status label stale after MT5 reconnect.
- Full broker universe confused with Market Watch.
- Market table arbitrarily limited without pagination or visible count.
- Nav controls drawn but not connected.
- Hard-coded thesis, event, countdown and score values shown as live.
- Chart bound to first discovered symbol instead of selected symbol.
- Flat/incorrect chart because index/time axis and visible ranges are wrong.
- Placeholder modules accepted as completed pages.

---

## 21. Testing strategy

### 21.1 Unit tests

- primitives and every engine
- normalization and overrides
- contract parsing and precision
- FX/gold/index sizing
- lifecycle transitions
- sessions and DST
- calendar mapping
- repository migrations
- alert rules

### 21.2 Bridge integration tests

Use a fake MT5 adapter and test every RPC, authentication, serialization, timeout, restart and error mapping.

### 21.3 Real MT5 demo tests

- terminal auto-discovery and manual path
- account and symbols
- hidden-symbol enablement
- bars on several asset classes
- orders/positions/deals
- accepted and rejected `order_check`
- demo order lifecycle only after explicit test authorization

### 21.4 UI tests

For every page:

- nav click changes current page
- filters work
- buttons produce observable results
- empty/loading/error states render
- keyboard navigation and focus
- no overlap at 1366×768, 1440×900 and 1920×1080
- theme and density persist

### 21.5 Packaging tests

- clean Windows VM
- build from fresh clone
- one-folder EXE with `_internal`
- bridge spawn in frozen mode
- startup with and without MT5
- installer and shortcuts
- uninstall preserves local database

---

## 22. Delivery milestones and gates

### M0 — Contract and skeleton

Exit: architecture, schema, fake MT5 adapter, CI and page router tests.

### M1 — Discovery and chart

Exit: full scopes, mapping, selected-symbol chart, timeframe probe, real status updates.

### M2 — Engines and Radar

Exit: engines A–I on fixtures and real bars, evidence chart, transparent ranking.

### M3 — Planner and lifecycle

Exit: persisted plans, Wait Engine, targets, risk and lifecycle board.

### M4 — Execution and positions

Exit: broker checks, demo dispatch, reconciliation and thesis monitor.

### M5 — Journal, performance, calendar and alerts

Exit: end-to-end review loop and provider degradation.

### M6 — UI hardening

Exit: every page functional, accessibility, themes, density and responsive desktop layouts.

### M7 — Release candidate

Exit: clean Windows build, installer, acceptance matrix, demo-account soak and signed artifacts.

No milestone advances with disabled tests, placeholder pages or fabricated production data.

---

## 23. Sellable-release requirements

- Semantic versioning.
- Signed installer and executable when certificate is available.
- End-user license and risk disclaimer reviewed by owner/legal counsel.
- Privacy statement explaining local storage and optional providers.
- Backup/export/restore workflow.
- Update-check mechanism that never self-installs without consent.
- Support diagnostics export.
- Demo-account-first onboarding.
- Explicit warning that software is a planning/execution tool, not financial advice.

---

## 24. Final acceptance matrix

A release fails if any item is false.

### Startup and packaging

- [ ] Installer works on clean Windows 10 x64.
- [ ] Installer works on clean Windows 11 x64.
- [ ] No Python installation required on target machine.
- [ ] App opens without MT5.
- [ ] App opens with broker MT5.
- [ ] Bridge restarts after forced termination.
- [ ] Startup and crash diagnostics are visible and persisted.

### Navigation and UI

- [ ] Every navigation button changes page.
- [ ] Every page has real content and empty/loading/error states.
- [ ] No example values presented as live.
- [ ] Theme/density work on all pages.
- [ ] Chart is bound to selected market and timeframe.

### MT5 and data

- [ ] Full broker universe count matches `symbols_get()`.
- [ ] Market Watch count matches `visible` symbols.
- [ ] Canonical and broker symbols round-trip.
- [ ] Contracts and sessions display from MT5.
- [ ] Bars and timestamps are correct.
- [ ] Connection status updates after reconnect.

### Analysis and planning

- [ ] Engines A–I return explainable results.
- [ ] Radar filters and ranks real engine output.
- [ ] Planner stores engine snapshots.
- [ ] Wait conditions update.
- [ ] Lifecycle persists.

### Risk and execution

- [ ] Calibration fixtures pass.
- [ ] Contract constraints are shown.
- [ ] Rejected `order_check` blocks dispatch.
- [ ] Accepted demo dispatch journals request/result.
- [ ] Positions and deals reconcile.

### Review

- [ ] Closed trade reaches review.
- [ ] Plan-vs-actual delta is correct.
- [ ] Performance metrics derive from stored records.
- [ ] Backup/export/restore pass.

---

## 25. Required deliverables from the next builder

Return a single release ZIP containing:

1. Complete source repository.
2. Windows lock files.
3. All tests and fixtures.
4. PyInstaller one-folder spec.
5. Valid manifest and version resource.
6. Inno Setup script.
7. One-click builder and dev launcher.
8. Exact brand assets from this handoff.
9. `SwingDeskSetup-<version>.exe` built on Windows.
10. One-folder artifact ZIP.
11. Test reports and build report.
12. SHA-256 hashes.
13. Known limitations with no concealed failures.

The builder must not return only an HTML prototype, screenshots, loose snippets or an untested scaffold.
