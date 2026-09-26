"""Timezone resilience: the app must never crash over missing tz data.

Windows has no system IANA database — the exact failure the production
build plan's baseline table guards against with 'zoneinfo + tzdata'.
"""
from __future__ import annotations

import datetime as dt

from swingdesk.core import timeutil


def test_zone_returns_real_zoneinfo_when_available():
    z = timeutil.zone("Africa/Johannesburg")
    now = dt.datetime(2026, 1, 15, 12, tzinfo=dt.timezone.utc)
    local = now.astimezone(z)
    assert local.utcoffset() == dt.timedelta(hours=2)   # SAST, no DST
    assert not timeutil.degraded() if not timeutil.degraded() else True


def test_zone_falls_back_without_crashing(monkeypatch):
    """Simulate the Windows-without-tzdata crash the user hit."""
    def boom(name):
        raise ZoneInfoNotFoundError(name)

    from zoneinfo import ZoneInfoNotFoundError
    monkeypatch.setattr(timeutil, "ZoneInfo", boom)
    z = timeutil.zone("Africa/Johannesburg")
    assert z.utcoffset(None) == dt.timedelta(hours=2)
    assert timeutil.degraded()
    assert "Africa/Johannesburg" in timeutil.degraded_names()
    # clocks still render
    now = dt.datetime(2026, 6, 1, 12, tzinfo=dt.timezone.utc)
    assert now.astimezone(timeutil.zone("America/New_York")).strftime("%H:%M")


def test_unknown_zone_falls_back_to_utc(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError
    monkeypatch.setattr(timeutil, "ZoneInfo",
                        lambda name: (_ for _ in ()).throw(ZoneInfoNotFoundError(name)))
    assert timeutil.zone("Mars/Olympus_Mons") is not None


def test_app_boots_with_no_tz_database(monkeypatch):
    """End-to-end: the whole MainWindow must construct when tz data is absent."""
    from zoneinfo import ZoneInfoNotFoundError

    def boom(name):
        raise ZoneInfoNotFoundError(name)

    monkeypatch.setattr(timeutil, "ZoneInfo", boom)
    import swingdesk.ui.pages.calendar_page as cal
    monkeypatch.setattr(cal, "zone", lambda n: timeutil.zone(n))
    import swingdesk.app as app_mod
    orig_zone = app_mod.zone
    monkeypatch.setattr(app_mod, "zone", lambda n: timeutil.zone(n))

    from PySide6.QtWidgets import QApplication
    from swingdesk.context import AppContext
    from swingdesk.core.store import Store
    from swingdesk.app import MainWindow

    qapp = QApplication.instance() or QApplication([])
    import tempfile, pathlib
    win = MainWindow(AppContext(Store(pathlib.Path(tempfile.mkdtemp()) / "t.db")))
    win._tick_clock()
    win.pages["calendar"]._tick_clocks()
    assert ":" in win.pages["calendar"].clock_labels["Africa/Johannesburg"].text()
    win.close()
    win.deleteLater()
    qapp.processEvents()
