"""Swing Desk — page registry.

Every page registers a KEY and a label. The router builds pages from this
registry; a navigation button exists for exactly each entry (§15.4).
"""
from __future__ import annotations

from .alerts import AlertsPage
from .broker import BrokerPage
from .calendar_page import CalendarPage
from .evidence import EvidencePage
from .journal import JournalPage
from .markets import MarketsPage
from .performance import PerformancePage
from .plans import PlansPage
from .positions import PositionsPage
from .radar import RadarPage
from .settings import SettingsPage
from .weekly import WeeklyPage

ALL_PAGES: dict[str, tuple[str, type]] = {
    "radar": ("Radar", RadarPage),
    "markets": ("Markets", MarketsPage),
    "evidence": ("Evidence", EvidencePage),
    "plans": ("Plans", PlansPage),
    "positions": ("Positions", PositionsPage),
    "journal": ("Journal", JournalPage),
    "performance": ("Performance", PerformancePage),
    "calendar": ("Calendar", CalendarPage),
    "alerts": ("Alerts", AlertsPage),
    "weekly": ("Weekly Board", WeeklyPage),
    "broker": ("Broker", BrokerPage),
    "settings": ("Settings", SettingsPage),
}

# convenience: key -> human label (used by Settings start-page combo)
LABELS = {k: v[0] for k, v in ALL_PAGES.items()}
