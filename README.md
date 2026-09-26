# Swing Desk — working application build

Built from the **SwingDesk-Next-Builder-Handoff** specification pack
(`SwingDesk-Production-Build-Plan.md` v2.0). This is a **native PySide6 desktop
application** — not the HTML reference — implementing the plan's M0–M2
foundation with **every navigation control and action button wired and
test-verified**.

| | |
|---|---|
| Status | M0–M2 foundation: router, 12 functional pages, engines A–I on demo data, persistence, risk math, tests |
| Runs on | Windows 10/11 (target), macOS, Linux — Python 3.10+ |
| Data source | **Deterministic demo adapter** (clearly labelled). Real MT5 integration point included (`Broker → Try real MT5`, Windows only) |
| Tests | **85 collected** — original UI coverage plus targeted validation/regression tests; GitHub Actions runs the full suite |
| Persistence | SQLite (WAL) at `%LOCALAPPDATA%\SwingDesk\swingdesk.db` (or `~/.local/share/SwingDesk`) |

The complete button → behaviour map: [`BUTTON-MAP.md`](BUTTON-MAP.md).

---

## How to execute

### Windows (the product's target platform)

```powershell
# 1. From PowerShell in the SwingDesk folder:
powershell -ExecutionPolicy Bypass -File .\run_dev.ps1
```

That script creates a `.venv`, installs `PySide6`, and launches the GUI.
To do it manually instead:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
pip install -e .
python -m swingdesk
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m swingdesk          # or: python run_dev.py
```

### Headless smoke test (no GUI needed — used by build scripts)

```bash
python -m swingdesk --self-test
```

### Launcher flags

`run_dev.ps1` / `run_dev.py` forward extra arguments to the app:

```powershell
.\run_dev.ps1 --self-test      # headless validation of router + pages
```

---

## Troubleshooting

**"No suitable Python runtime found"** (from the `py` launcher)
The original launcher hard-required Python 3.11. The current one accepts any
**Python 3.10+** — it probes `py -3.11/-3.12/-3.13/-3.14/-3.10/-3`, then
`python` / `python3`. If nothing is installed:

```powershell
winget install -e --id Python.Python.3.11
# ...then close and reopen PowerShell and run the launcher again
```

`py -0p` lists every Python the launcher can see.

**"This folder does not contain the Swing Desk application"**
Your checkout is missing the application source. A valid repaired checkout contains
`src/`, `tests/`, `pyproject.toml` and `run_dev.py` alongside the original handoff
documents. Pull the `arena/01a0de62-swingdesk-next-builder-handoff` branch again.

**Linux/macOS CI or headless machines** — export `QT_QPA_PLATFORM=offscreen`
before launching.

**Verify the installation without a GUI:** `.\run_dev.ps1 --self-test` should
print `SELF-TEST OK — 12 pages routed...`.

### Run the test suite

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest          # Linux/macOS CI
pytest                                    # Windows (real display)
```

85 collected tests cover: every navigation button switches pages, every action
button produces an observable result, lifecycle transitions are validated, alerts
fire on price crosses and event timestamps, exports create files, malformed/
over-risked orders are blocked, repeated UI renders stay bounded, and MT5 probing
never mislabels demo data as live.

---

## Validation hardening in this branch

- Pre-flight rejects non-finite/invalid prices, same-side SL/TP levels, broker
  stop-distance violations, invalid contract metadata and broker-minimum sizing
  that would exceed the requested risk cap.
- Saved legacy plans are revalidated before TRIGGERED/OPEN transitions, including
  checking the stored volume against the plan risk cap.
- Rebuilt cards recursively clear nested layouts, preventing duplicate controls.
- Calendar alerts use the event UTC timestamp; alert price inputs support FX,
  metals, indices and crypto prices above 99.99.
- The MT5 button is a connectivity probe only and cannot imply the demo adapter
  has switched to live data.
- `--self-test` uses an isolated temporary SQLite database and does not touch the
  user's persisted SwingDesk database.
- The lifecycle board has its own horizontal viewport and the sidebar brand has a
  stable minimum size, preventing layout collapse.

## What works right now

**Navigation & shell** — 12-page router (`QStackedWidget`), active-state
styling, keyboard shortcuts (Ctrl+1…9), live dual/tri clocks (NY/London/SAST,
IANA zones), orbiting brand frame painted natively in QPainter, three themes
(Obsidian/Paper/Terminal) and three densities applied live, in-app toasts.

**Analysis** — engines A–I (structure, supply/demand, liquidity, FVG, order
blocks, 71%/OTE, CRT, RSI divergence) computed from real bar arrays with
explainable verdicts, reasons and evidence levels; transparent group scorecard
(STRUCTURE/LOCATION/LIQUIDITY/ZONES/TIMING; MACRO honestly unknown until a
provider is connected).

**Chart** — custom QPainter candlestick chart bound to the *selected* market
and timeframe (never a default), wheel zoom, drag pan, crosshair with OHLC
tooltip, evidence layers drawn from engine payloads, fit/reset, PNG export,
honest DEMO watermark.

**Planning & risk** — contract-aware sizing exactly per §10.1 (tick value /
tick size math, volume step flooring, min/max clamps), `order_check` gate
displayed before any dispatch concept, full validated lifecycle board
(SCANNING→…→REVIEW), plans persist across restarts, engine snapshots stored.

**Positions / journal / performance** — demo positions with confirmation-gated
close and typed-confirmation bulk close, closed plans reconciled to positions,
plan-vs-actual deltas, behaviour flags, review completion, CSV/Markdown exports
of journal, performance and weekly board (only from stored, auditable records —
empty states when there is nothing, never fabricated numbers).

**Alerts** — deterministic price-cross and event-time rules persisted in SQLite,
pause/resume/delete, high-priced symbols supported, fired alerts logged and
toasted by the demo tick loop.

**Broker** — connection status with *precise next action* messaging, terminal
path chooser, separate universe scopes (all broker symbols vs Market Watch
counts), contract display, and a real `MetaTrader5` connectivity probe on Windows. A
successful probe explicitly leaves the active adapter in DEMO mode until the
real bridge is implemented.

## What is deliberately NOT done yet (per the handoff roadmap)

- The `SwingDesk.exe --bridge` child process with JSONL RPC (the integration
  point exists; the adapter interface is in place).
- Real MT5 discovery/order dispatch (demo adapter provides the same surface).
- PyInstaller one-folder + Inno Setup installer (`build/` scaffolding started).
- pyqtgraph high-performance chart (current chart is a correct QPainter
  implementation sufficient for 2,000 bars).

## Project layout

```
SwingDesk/
├─ run_dev.py / run_dev.ps1      launchers
├─ pyproject.toml                package + deps
├─ src/swingdesk/
│  ├─ main.py                    entry (GUI / --self-test)
│  ├─ app.py                     MainWindow: router, timers, dialogs, theming
│  ├─ context.py                 AppContext + EventHub (testability seam)
│  ├─ core/
│  │  ├─ models.py               domain contracts (Plan, Bar, EngineResult…)
│  │  ├─ engines.py              shared primitives + engines A–I
│  │  ├─ demo_data.py            deterministic demo MT5 adapter
│  │  ├─ risk.py                 sizing formula + order_check gate
│  │  └─ store.py                SQLite WAL repository + migrations
│  └─ ui/
│     ├─ theme.py                themes, densities, orbit brand widget
│     ├─ widgets.py              Card/Stat/Badge/Toast/EmptyState
│     ├─ chart.py                native candlestick chart
│     └─ pages/                  12 pages, one module each
└─ tests/                        85 collected pytest/pytest-qt tests
```
