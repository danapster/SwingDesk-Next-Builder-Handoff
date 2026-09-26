"""Timezone helper with graceful degradation.

Windows ships no system IANA tz database, so `zoneinfo` there requires the
`tzdata` package (a declared dependency). If tz data is missing anyway, we
fall back to fixed-offset stand-ins so clocks keep working instead of
crashing the app (§0.1-4: report degradation, never crash).
"""
from __future__ import annotations

import datetime as dt

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - very old Python
    ZoneInfo = None  # type: ignore[assignment]

# Fixed-offset stand-ins, used ONLY when the tz database is unavailable.
# They approximate standard time; the asterisk marks degraded mode.
_FIXED_FALLBACKS = {
    "America/New_York": dt.timezone(dt.timedelta(hours=-5), "NY*"),
    "Europe/London": dt.timezone(dt.timedelta(hours=0), "LON*"),
    "Europe/Berlin": dt.timezone(dt.timedelta(hours=1), "FRA*"),
    "Africa/Johannesburg": dt.timezone(dt.timedelta(hours=2), "SAST*"),
}

_DEGRADED: set[str] = set()


def zone(name: str):
    """ZoneInfo for `name`, or a fixed-offset fallback. Never raises."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    _DEGRADED.add(name)
    return _FIXED_FALLBACKS.get(name, dt.timezone.utc)


def degraded() -> bool:
    """True when at least one zone fell back to a fixed offset."""
    return bool(_DEGRADED)


def degraded_names() -> list[str]:
    return sorted(_DEGRADED)
