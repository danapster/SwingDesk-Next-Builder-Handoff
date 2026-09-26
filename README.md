# Swing Desk — live MT5 application build

Swing Desk is a native **PySide6 desktop trading decision workstation** built
from the SwingDesk production handoff. The current branch uses a logged-in
**MetaTrader 5 terminal as its live market-data source** and a **local Forex
Factory weekly JSON cache** for the economic calendar.

| | |
|---|---|
| Status | 12 functional pages, live MT5 market data, engines A–I, local Forex Factory calendar cache, persistence, risk controls |
| Target | Windows 10/11, Python 3.10+ |
| Market data | **Live MetaTrader 5**: broker symbols, Market Watch, bid/ask, contract metadata, candles, account equity and open positions |
| Calendar | Local `ff_calendar_thisweek.json`; online content is used only to refresh that local file |
| Tests | **90 collected** pytest/pytest-qt tests plus the isolated 12-page self-test |
| Persistence | SQLite WAL at `%LOCALAPPDATA%\SwingDesk\swingdesk.db` |
| Broker execution | **Disabled in this build** — live MT5 positions are mirrored read-only |

The deterministic demo adapter is retained only as an explicitly labelled
fallback and for automated tests. The UI never labels fallback data as live.

## Windows quick start

```powershell
cd C:\FX_Projects\SwingDesk-Git

git fetch origin
git switch arena/01a0de62-swingdesk-next-builder-handoff
git pull --ff-only origin arena/01a0de62-swingdesk-next-builder-handoff

powershell -ExecutionPolicy Bypass -File .\run_dev.ps1
```

The Windows install automatically includes the current `MetaTrader5` Python
package. Open your broker's MetaTrader 5 terminal and log in before launching
Swing Desk. If MT5 auto-detection selects the wrong terminal, use
**Broker & Discovery → Choose terminal64.exe**.

Manual installation:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e .
python -m swingdesk
```

## Live MetaTrader 5 data

When connected, Swing Desk reads directly from the terminal for:

- the broker's complete symbol universe and Market Watch visibility;
- live bid/ask ticks and broker symbol names/suffixes;
- digits, point/tick size, tick value, contract size, volume limits,
  stop/freeze levels and trade/filling metadata;
- M15, H1, H4, D1 and W1 candles used by the analysis engines;
- account balance/equity metadata; and
- currently open broker positions and P/L.

There is **no per-symbol demo substitution while the MT5 provider is live**.
If a live symbol or candle request is unavailable, that live request remains
missing instead of silently inserting synthetic bars.

Live order submission, modification and closing are intentionally not enabled.
The Positions page becomes read-only when the source is LIVE MT5.

## Forex Factory calendar cache

Swing Desk uses Forex Factory's weekly JSON export:

`https://nfs.faireconomy.media/ff_calendar_thisweek.json`

The normal Windows cache location is:

```text
%LOCALAPPDATA%\SwingDesk\calendar\ff_calendar_thisweek.json
```

Runtime calendar rendering reads **only this local JSON file**. The updater:

1. validates that the online response is real JSON and contains valid events;
2. rejects HTML/rate-limit/error responses so they cannot replace the last
   known-good cache;
3. compares a SHA-256 digest and replaces the local file atomically only when
   the content changed;
4. checks online no more than once per hour during normal operation; and
5. forces a fresh download on the first run after **Monday 00:00
   Africa/Johannesburg (SAST)**.

If Swing Desk is not running exactly at Monday 00:00, the forced refresh is
performed on the next launch/timer cycle after that boundary. A failed forced
attempt is then throttled back to the hourly retry cadence.

The Calendar page also has **Refresh Forex Factory cache** for an explicit
manual refresh and shows the local path, event count, last successful download
and last error.

Optional overrides:

```text
SWINGDESK_DATA_DIR
SWINGDESK_CALENDAR_PATH
SWINGDESK_SCAN_LIMIT
SWINGDESK_FORCE_DEMO
```

## Validation

Run the full Windows test suite:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m swingdesk --self-test
```

The suite covers the existing router/actions/lifecycle/risk regressions plus
live-provider mapping and calendar-cache behavior: local-only reads, timezone
conversion, Monday SAST refresh logic, rejection of invalid HTML responses,
live broker metadata/candles/equity/positions, and the LIVE MT5 UI state.

## Current safety boundaries

Pre-flight and lifecycle validation remain enforced. Saved plans are
revalidated before trigger/open transitions, broker minimum-volume rounding is
bounded, invalid SL/TP geometry is rejected, calendar alerts use real event UTC
timestamps, and high-priced instruments are supported.

This change is a **market-data integration**, not an automatic-trading change.
Swing Desk does not call MT5 order-send/order-close functions in this build.

## Project layout

```text
SwingDesk/
├─ run_dev.py / run_dev.ps1
├─ pyproject.toml
├─ src/swingdesk/
│  ├─ main.py
│  ├─ app.py
│  ├─ context.py
│  ├─ core/
│  │  ├─ models.py
│  │  ├─ engines.py
│  │  ├─ mt5_live.py          read-only live MT5 provider
│  │  ├─ calendar_cache.py    local Forex Factory weekly cache
│  │  ├─ demo_data.py         provider router + deterministic fallback
│  │  ├─ risk.py
│  │  └─ store.py
│  └─ ui/
│     ├─ chart.py
│     └─ pages/
└─ tests/
```
