# Swing Desk — next-builder handoff

This package is the clean, implementation-ready handoff for rebuilding Swing Desk as a production Windows desktop application.

## Read in this order

1. `SwingDesk-Production-Build-Plan.md` — authoritative product, architecture, UX, testing, packaging, and acceptance specification.
2. `SwingDesk-Master-Build-Prompt-v2.md` — paste this into the new coding agent together with this full ZIP.
3. `ASSET-MANIFEST.md` — explains every supplied visual asset and where it belongs.
4. `build-contract/BUILD-SAFETY.md` — mandatory Windows build protections based on prior failures.
5. `build-contract/app.manifest` — validated manifest template for PyInstaller/Inno Setup.

## Important status

- This is a **handoff/specification and asset pack**, not another partial application build.
- The earlier prototype source is deliberately excluded so a new builder does not inherit inert navigation, sample data, packaging defects, or architectural shortcuts.
- `reference/SwingDeskTerminal-BuildPlan-v1-SUPERSEDED.md` is included only for traceability. If it conflicts with the production plan, the production plan wins.
- Files in `reference/html/` are visual interaction references only. The shipped product must be native PySide6, not an HTML wrapper.
- Files in `reference/screenshots/` define the desired visual direction: restrained luxury terminal, serif display headings, dense usable layouts, muted gold, cyan accents, visible evidence.

## Required final result

The next builder must return a source ZIP, a tested PyInstaller **one-folder** application, and an Inno Setup installer. The installed user launches Swing Desk from a normal shortcut; internal runtime files remain hidden in the installation directory. A tiny EXE beside a required `_internal` folder is normal for the build output and must be wrapped by the installer.

## Ownership of truth

The production plan and its acceptance matrix are the definition of done. A polished shell with dead tabs, static thesis data, a fake connected state, or incomplete broker discovery is a failed delivery.
