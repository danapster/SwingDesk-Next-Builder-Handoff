"""§15.4 acceptance: every navigation button switches to its constructed page,
updates the active style, and survives a pytest-qt click test."""
from __future__ import annotations

import pytest

from swingdesk.ui.pages import ALL_PAGES


def test_every_page_registered_and_constructed(make_app):
    win = make_app()
    assert set(win.pages) == set(ALL_PAGES)
    for key, page in win.pages.items():
        assert win.stack.indexOf(page) >= 0, f"{key} page not in stack"


@pytest.mark.parametrize("key", list(ALL_PAGES))
def test_nav_button_click_switches_page(make_app, key):
    win = make_app()
    win.navigate("settings")  # start somewhere else
    btn = win.nav_buttons[key]
    btn.click()
    assert win.stack.currentWidget() is win.pages[key]
    assert btn.property("active") is True
    for other, ob in win.nav_buttons.items():
        if other != key:
            assert ob.property("active") in (False, None)


def test_no_inert_navigation_buttons(make_app):
    """Every nav button must have a connected receiver (no dead controls)."""
    win = make_app()
    for key, btn in win.nav_buttons.items():
        assert btn.receivers("2clicked()") >= 1, \
            f"nav button {key} has no connected slot"


def test_navigate_via_context(make_app):
    win = make_app()
    win.ctx.navigate("journal")
    assert win.stack.currentWidget() is win.pages["journal"]


def test_start_page_setting_respected(make_app, tmp_path):
    from swingdesk.core.store import Store
    store = Store(tmp_path / "start-page.db")
    store.set_setting("start_page", "performance")
    win = make_app(store=store)
    assert win.stack.currentWidget() is win.pages["performance"]


def test_keyboard_shortcuts_bound(make_app):
    from PySide6.QtGui import QShortcut
    win = make_app()
    # Ctrl+1..Ctrl+9 were registered for the first nine pages
    shortcuts = win.findChildren(QShortcut)
    assert len(shortcuts) >= 9
