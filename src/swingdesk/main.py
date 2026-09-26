"""Swing Desk — entry point.

    python -m swingdesk            normal GUI
    python -m swingdesk --self-test   headless smoke test (build contract §19.6)
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        return _self_test()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .app import create_app
    app, win = create_app()
    win.show()
    if "--quit-after" in argv:  # used by smoke checks
        try:
            ms = int(argv[argv.index("--quit-after") + 1])
        except Exception:
            ms = 1500
        QTimer.singleShot(ms, app.quit)
    return app.exec()


def _self_test() -> int:
    """Headless validation used by build scripts: router, pages, buttons.

    The smoke test must never open or mutate the user's real SwingDesk DB.
    """
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from swingdesk.app import create_app
    from swingdesk.core.store import Store
    from swingdesk.ui.pages import ALL_PAGES

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="swingdesk-self-test-") as td:
        store = Store(Path(td) / "self-test.db")
        _app, win = create_app(store)
        failures: list[str] = []
        try:
            for key in ALL_PAGES:
                try:
                    win.navigate(key)
                    current = win.stack.currentWidget()
                    assert current is win.pages[key], f"navigate({key}) did not switch page"
                    active_btn = win.nav_buttons[key].property("active")
                    assert active_btn, f"nav button for {key} not marked active"
                except Exception as exc:  # pragma: no cover
                    failures.append(f"{key}: {exc}")
        finally:
            win.close()
            app.processEvents()
            store.close()
        if failures:
            print("SELF-TEST FAILED:")
            for f in failures:
                print("  -", f)
            return 1
        print(f"SELF-TEST OK — {len(ALL_PAGES)} pages routed, all nav buttons active-checked, "
              "deterministic test data route online, isolated temporary store writable.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
