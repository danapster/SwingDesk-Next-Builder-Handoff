"""Forex Factory weekly calendar cache.

SwingDesk reads calendar events only from the local JSON file. Network access is
isolated here and only refreshes that file. Ordinary checks are limited to once
per hour; after each Monday 00:00 Africa/Johannesburg boundary a fresh download
is forced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import CalendarEvent

FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CHECK_INTERVAL = timedelta(hours=1)
SAST = ZoneInfo("Africa/Johannesburg")


def _app_data_dir() -> Path:
    override = os.environ.get("SWINGDESK_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "SwingDesk"
    return Path.home() / ".local" / "share" / "SwingDesk"


def default_calendar_path() -> Path:
    override = os.environ.get("SWINGDESK_CALENDAR_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _app_data_dir() / "calendar" / "ff_calendar_thisweek.json"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CalendarCacheStatus:
    path: Path
    exists: bool
    event_count: int
    last_checked: str
    last_download: str
    content_sha256: str
    last_error: str
    source_url: str = FOREX_FACTORY_URL


class CalendarCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_calendar_path()
        self.meta_path = self.path.with_suffix(self.path.suffix + ".meta.json")
        self._refresh_lock = threading.Lock()
        self._refresh_thread: threading.Thread | None = None

    def _read_meta(self) -> dict[str, Any]:
        try:
            data = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_meta(self, meta: dict[str, Any]) -> None:
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.meta_path.with_suffix(self.meta_path.suffix + ".tmp")
        tmp.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.meta_path)

    @staticmethod
    def _week_anchor(now_utc: datetime | None = None) -> datetime:
        local = (now_utc or datetime.now(timezone.utc)).astimezone(SAST)
        monday = local - timedelta(days=local.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)

    def weekly_refresh_due(self, now_utc: datetime | None = None) -> bool:
        last = _parse_iso(str(self._read_meta().get("last_download", "")))
        if last is None:
            return True
        return last.astimezone(SAST) < self._week_anchor(now_utc)

    def hourly_check_due(self, now_utc: datetime | None = None) -> bool:
        last = _parse_iso(str(self._read_meta().get("last_checked", "")))
        now = now_utc or datetime.now(timezone.utc)
        return last is None or now - last >= CHECK_INTERVAL

    @staticmethod
    def _validate_payload(raw: bytes) -> list[dict[str, Any]]:
        if raw.lstrip().startswith(b"<"):
            raise ValueError("calendar endpoint returned HTML instead of JSON")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, list):
            raise ValueError("calendar JSON root must be an array")
        rows: list[dict[str, Any]] = []
        for row in parsed:
            if not isinstance(row, dict):
                continue
            if not row.get("title") or not row.get("country") or not row.get("date"):
                continue
            if _parse_iso(str(row.get("date"))) is None:
                continue
            rows.append(row)
        if not rows:
            raise ValueError("calendar JSON contained no valid events")
        return rows

    def load_rows(self) -> list[dict[str, Any]]:
        """Read the local cache only. This method never performs network IO."""
        try:
            return self._validate_payload(self.path.read_bytes())
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def load_events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for row in self.load_rows():
            dt = _parse_iso(str(row.get("date", "")))
            if dt is None:
                continue
            events.append(CalendarEvent(
                time_utc=dt,
                title=str(row.get("title", "")).strip(),
                currency=str(row.get("country", "")).strip().upper(),
                impact=(str(row.get("impact", "Low")).strip().upper() or "LOW"),
                zone="Forex Factory",
                affects=(),
            ))
        events.sort(key=lambda e: e.time_utc)
        return events

    def refresh(self, force: bool = False, timeout: float = 10.0) -> tuple[bool, str]:
        with self._refresh_lock:
            meta = self._read_meta()
            now = datetime.now(timezone.utc)
            if not force and not self.hourly_check_due(now):
                return False, "calendar check not due"

            headers = {
                "Accept": "application/json",
                "User-Agent": "SwingDesk/0.1 local-calendar-cache",
                "Cache-Control": "no-cache" if force else "max-age=0",
            }
            if not force:
                if meta.get("etag"):
                    headers["If-None-Match"] = str(meta["etag"])
                if meta.get("last_modified"):
                    headers["If-Modified-Since"] = str(meta["last_modified"])

            try:
                req = Request(FOREX_FACTORY_URL, headers=headers, method="GET")
                with urlopen(req, timeout=timeout) as response:
                    raw = response.read()
                    rows = self._validate_payload(raw)
                    digest = sha256(raw).hexdigest()
                    old_digest = str(meta.get("content_sha256", ""))
                    if not old_digest and self.path.exists():
                        try:
                            old_digest = sha256(self.path.read_bytes()).hexdigest()
                        except OSError:
                            old_digest = ""
                    changed = digest != old_digest or not self.path.exists()
                    if changed:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                        tmp.write_bytes(raw)
                        tmp.replace(self.path)
                    meta.update({
                        "source_url": FOREX_FACTORY_URL,
                        "last_checked": now.isoformat(timespec="seconds"),
                        "last_download": now.isoformat(timespec="seconds"),
                        "content_sha256": digest,
                        "event_count": len(rows),
                        "etag": response.headers.get("ETag", ""),
                        "last_modified": response.headers.get("Last-Modified", ""),
                        "last_error": "",
                    })
                    self._write_meta(meta)
                    return changed, ("calendar cache updated" if changed
                                     else "calendar checked; no content changes")
            except HTTPError as exc:
                if exc.code == 304:
                    meta["last_checked"] = now.isoformat(timespec="seconds")
                    meta["last_error"] = ""
                    self._write_meta(meta)
                    return False, "calendar unchanged (HTTP 304)"
                msg = f"HTTP {exc.code}: {exc.reason}"
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                msg = f"{type(exc).__name__}: {exc}"

            meta["last_checked"] = now.isoformat(timespec="seconds")
            meta["last_error"] = msg
            self._write_meta(meta)
            return False, f"calendar refresh failed: {msg}"

    def ensure_local(self) -> bool:
        if self.load_rows():
            self.maybe_refresh_async()
            return True
        self.refresh(force=True)
        return bool(self.load_rows())

    def maybe_refresh_async(self) -> bool:
        force = self.weekly_refresh_due()
        hourly_due = self.hourly_check_due()
        # The first run after the Monday 00:00 SAST boundary bypasses the normal
        # hourly cadence. If that forced attempt fails, last_checked is now
        # inside the new week and subsequent retries are throttled to hourly.
        last_checked = _parse_iso(str(self._read_meta().get("last_checked", "")))
        checked_this_week = (
            last_checked is not None
            and last_checked.astimezone(SAST) >= self._week_anchor()
        )
        if force:
            if checked_this_week and not hourly_due:
                return False
        elif not hourly_due:
            return False
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return False

        def worker() -> None:
            self.refresh(force=force)

        self._refresh_thread = threading.Thread(
            target=worker, name="SwingDeskCalendarRefresh", daemon=True)
        self._refresh_thread.start()
        return True

    def status(self) -> CalendarCacheStatus:
        meta = self._read_meta()
        rows = self.load_rows()
        return CalendarCacheStatus(
            path=self.path,
            exists=self.path.exists(),
            event_count=len(rows),
            last_checked=str(meta.get("last_checked", "")),
            last_download=str(meta.get("last_download", "")),
            content_sha256=str(meta.get("content_sha256", "")),
            last_error=str(meta.get("last_error", "")),
        )


_CACHE: CalendarCache | None = None
_CACHE_KEY: str | None = None


def shared_calendar_cache() -> CalendarCache:
    global _CACHE, _CACHE_KEY
    path = default_calendar_path()
    key = str(path)
    if _CACHE is None or _CACHE_KEY != key:
        _CACHE = CalendarCache(path)
        _CACHE_KEY = key
    return _CACHE
