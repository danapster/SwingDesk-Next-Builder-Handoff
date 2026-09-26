# Swing Desk Asset Manifest

## Production assets

- `assets/app.ico` — required PyInstaller and installer icon; multi-size Windows icon.
- `assets/app-icon.svg` — editable master vector.
- `assets/app-icon-1024.png` — raster master.
- `assets/logo-wordmark.svg` — Obsidian wordmark.
- `assets/logo-wordmark-light.svg` — Paper-theme wordmark.
- `assets/installer-banner.bmp` — Inno Setup wizard image reference.
- `assets/installer-small.bmp` — Inno Setup small wizard image.
- `assets/splash.png` — startup/splash artwork.
- `assets/theme-tokens.json` — canonical colors and type direction.

## Reference only

- `reference/html/edge-ledger-admin.html` — owner-provided visual-language reference.
- `reference/html/SwingDesk-UI-Preview.html` — Swing Desk layout reference; not production code.
- `reference/screenshots/*` — visual QA references.

## Required build paths

Copy production assets to:

```text
build/assets/app.ico
build/assets/installer-banner.bmp
build/assets/installer-small.bmp
build/assets/splash.png
src/swingdesk/resources/icons/app-icon.svg
```

Build preflight must fail with a clear message if any required asset is absent.
