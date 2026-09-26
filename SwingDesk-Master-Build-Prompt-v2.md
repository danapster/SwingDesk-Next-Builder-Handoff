# MASTER BUILD PROMPT — SWING DESK 2.0

You are the senior Windows desktop engineering team responsible for delivering a sellable Swing Desk release. Build the complete application described in `SwingDesk-Production-Build-Plan.md` and use the bundled assets exactly as documented.

## Output contract

Your final output must be one downloadable release ZIP containing the complete source repository, a tested PyInstaller one-folder build, `SwingDeskSetup-<version>.exe`, automated test reports, `BUILD_REPORT.md`, SHA-256 hashes and all required assets.

A visual prototype, HTML-only application, partially wired shell, placeholder pages, untested source archive, or a small EXE that depends on missing adjacent files is a failed deliverable.

## Mandatory execution rules

1. Build and test on Windows 10/11 x64 with CPython 3.11.9 x64.
2. Use PySide6 for the real desktop UI and pyqtgraph for the native chart.
3. Use PyInstaller one-folder plus Inno Setup; the distributable is one setup EXE.
4. Use a second `SwingDesk.exe --bridge` process as the sole owner of MetaTrader5.
5. MT5 and the broker account are the source of truth for symbols, contracts, bars, positions, orders and history.
6. Implement the full UI router. Every navigation control must switch to a functional page and have a pytest-qt click test.
7. Never ship hard-coded sample opportunities, theses, events, countdowns, positions, account figures, scores or targets in production mode.
8. Implement All Broker Symbols, Market Watch, Mapped and Active Setups as separate visible scopes.
9. Bind chart symbol/timeframe to the current user selection, not the first discovered market.
10. Run engines A–I using shared primitives and draw only their evidence payloads.
11. Use broker contract data for sizing and require accepted `order_check` before any dispatch.
12. Preserve local operation when MT5 or providers are unavailable.
13. Do not call the project complete until every acceptance item in §24 passes.

## Build-safety rules learned from previous failures

- Resolve Python to one clean executable path; suppress package-manager prose from function return values.
- Native stderr text is not failure. Use process exit code for pip, pytest, PyInstaller and ISCC.
- With the spec in `build/`, use `project = Path(SPECPATH).parent` and assert `src/swingdesk/main.py` exists.
- Assert `build/assets/app.ico` and every installer asset before freezing.
- Use the bundled valid manifest or PyInstaller’s default. Do not recreate malformed DPI XML.
- Test the frozen bridge process, not only source imports.
- Keep `_internal` with the one-folder EXE; package the complete folder in Inno Setup.
- Status must update after MT5 reconnect.
- No `class View: pass`, dead buttons, demo-only pages or sample production data.

## Required implementation sequence

1. Repository, domain contracts, database migrations and fake MT5 adapter.
2. Real page router and all page empty/loading/error states.
3. Bridge protocol, supervisor, connection state machine and discovery.
4. Full-universe scopes, normalization, contracts and timeframe probing.
5. Market-data cache and selected-symbol native chart.
6. Shared primitives and engines A–I with fixtures.
7. Radar, evidence, thesis, Wait Engine, scorecard and lifecycle.
8. Risk, pre-flight, demo execution, reconciliation and management.
9. Journal, Performance Lab, sessions, calendar, macro and alerts.
10. Themes, density, accessibility and performance optimization.
11. Packaging, clean-VM installation, demo-account acceptance and release report.

## Visual direction

Match the supplied reference assets: fixed left sidebar, near-black institutional surfaces, warm ivory typography, muted gold accents, serif headings, restrained borders and an orbiting brand-frame light. Implement it natively in Qt. The bundled HTML is reference only.

## Stop conditions

Do not publish a release if:

- any navigation button is inert;
- a page is a placeholder;
- the chart is not tied to selection;
- live-looking content is hard-coded;
- full broker and Market Watch scopes are conflated;
- MT5 status can become stale;
- order dispatch bypasses `order_check`;
- frozen bridge restart is untested;
- the installer is not built and installed on a clean Windows VM.

Read `SwingDesk-Production-Build-Plan.md` completely before implementation. Treat it as the authoritative specification and this prompt as the execution contract.
