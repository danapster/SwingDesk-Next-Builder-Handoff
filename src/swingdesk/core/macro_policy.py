"""Local-first central-bank policy-rate cache backed by Trading Economics.

The Calendar & Macro UI reads only the local JSON cache. Network access is
isolated in this module and refreshes the cache at a conservative cadence.
Trading Economics requires an API key, supplied through SWINGDESK_TE_API_KEY.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

CHECK_INTERVAL = timedelta(hours=6)
API_BASE = "https://api.tradingeconomics.com"

CURRENCY_COUNTRY = {
    "USD": "United States",
    "EUR": "Euro Area",
    "GBP": "United Kingdom",
    "JPY": "Japan",
    "CHF": "Switzerland",
    "CAD": "Canada",
    "AUD": "Australia",
    "NZD": "New Zealand",
    "ZAR": "South Africa",
}

CENTRAL_BANK = {
    "USD": "Federal Reserve",
    "EUR": "European Central Bank",
    "GBP": "Bank of England",
    "JPY": "Bank of Japan",
    "CHF": "Swiss National Bank",
    "CAD": "Bank of Canada",
    "AUD": "Reserve Bank of Australia",
    "NZD": "Reserve Bank of New Zealand",
    "ZAR": "South African Reserve Bank",
}


def _app_data_dir() -> Path:
    override = os.environ.get("SWINGDESK_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "SwingDesk"
    return Path.home() / ".local" / "share" / "SwingDesk"


def default_policy_path() -> Path:
    override = os.environ.get("SWINGDESK_MACRO_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _app_data_dir() / "macro" / "policy_rates.json"


def api_key_configured() -> bool:
    return bool(os.environ.get("SWINGDESK_TE_API_KEY", "").strip())


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PolicyRate:
    currency: str
    country: str
    central_bank: str
    rate: float
    previous_rate: float
    effective_date: str
    previous_date: str
    stance: str
    source: str
    source_url: str


@dataclass(frozen=True)
class MacroPolicyStatus:
    path: Path
    exists: bool
    rate_count: int
    last_checked: str
    last_download: str
    content_sha256: str
    last_error: str
    provider: str = "Trading Economics"
    api_key_configured: bool = False


class MacroPolicyCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_policy_path()
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

    def refresh_due(self, now_utc: datetime | None = None) -> bool:
        last = _parse_iso(str(self._read_meta().get("last_checked", "")))
        now = now_utc or datetime.now(timezone.utc)
        return last is None or now - last >= CHECK_INTERVAL

    @staticmethod
    def _stance(rate: float, previous: float) -> str:
        if rate > previous + 1e-9:
            return "HIKING"
        if rate < previous - 1e-9:
            return "EASING"
        return "HOLDING"

    @classmethod
    def _normalize_payload(cls, payload: Any) -> list[PolicyRate]:
        if not isinstance(payload, list):
            raise ValueError("Trading Economics response must be a JSON array")

        by_country = {v.casefold(): k for k, v in CURRENCY_COUNTRY.items()}
        rates: list[PolicyRate] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            country = str(row.get("Country", "")).strip()
            currency = by_country.get(country.casefold())
            if not currency:
                continue
            category = str(row.get("Category", "")).strip().casefold()
            if category and category != "interest rate":
                continue
            try:
                rate = float(row.get("LatestValue"))
                previous = float(row.get("PreviousValue"))
            except (TypeError, ValueError):
                continue
            rates.append(PolicyRate(
                currency=currency,
                country=country,
                central_bank=CENTRAL_BANK[currency],
                rate=rate,
                previous_rate=previous,
                effective_date=str(row.get("LatestValueDate", "") or ""),
                previous_date=str(row.get("PreviousValueDate", "") or ""),
                stance=cls._stance(rate, previous),
                source=str(row.get("Source", "") or "").strip(),
                source_url=str(row.get("SourceURL", "") or "").strip(),
            ))

        if not rates:
            raise ValueError("Trading Economics response contained no policy rates")
        rates.sort(key=lambda r: r.currency)
        return rates

    def load_rates(self) -> list[PolicyRate]:
        """Read the local policy-rate JSON only. Never performs network I/O."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            out: list[PolicyRate] = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                out.append(PolicyRate(
                    currency=str(row["currency"]),
                    country=str(row["country"]),
                    central_bank=str(row["central_bank"]),
                    rate=float(row["rate"]),
                    previous_rate=float(row["previous_rate"]),
                    effective_date=str(row.get("effective_date", "")),
                    previous_date=str(row.get("previous_date", "")),
                    stance=str(row.get("stance", "HOLDING")),
                    source=str(row.get("source", "")),
                    source_url=str(row.get("source_url", "")),
                ))
            return sorted(out, key=lambda r: r.currency)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return []

    def by_currency(self) -> dict[str, PolicyRate]:
        return {r.currency: r for r in self.load_rates()}

    def differential(self, base_currency: str, quote_currency: str) -> float | None:
        rates = self.by_currency()
        base = rates.get((base_currency or "").upper())
        quote_rate = rates.get((quote_currency or "").upper())
        if base is None or quote_rate is None:
            return None
        return base.rate - quote_rate.rate

    def _request_url(self, api_key: str) -> str:
        countries = ",".join(CURRENCY_COUNTRY.values())
        path = quote(countries, safe=",")
        query = urlencode({"c": api_key, "f": "json"})
        return f"{API_BASE}/country/{path}/interest%20rate?{query}"

    def refresh(self, force: bool = False, timeout: float = 12.0,
                api_key: str | None = None) -> tuple[bool, str]:
        with self._refresh_lock:
            now = datetime.now(timezone.utc)
            meta = self._read_meta()
            if not force and not self.refresh_due(now):
                return False, "macro policy check not due"

            key = (api_key or os.environ.get("SWINGDESK_TE_API_KEY", "")).strip()
            if not key:
                msg = "Trading Economics API key is not configured"
                meta["last_checked"] = now.isoformat(timespec="seconds")
                meta["last_error"] = msg
                self._write_meta(meta)
                return False, msg

            try:
                req = Request(
                    self._request_url(key),
                    headers={"Accept": "application/json", "User-Agent": "SwingDesk/0.1"},
                    method="GET",
                )
                with urlopen(req, timeout=timeout) as response:
                    raw = response.read()
                if raw.lstrip().startswith(b"<"):
                    raise ValueError("provider returned HTML instead of JSON")
                payload = json.loads(raw.decode("utf-8"))
                rates = self._normalize_payload(payload)
                normalized = json.dumps(
                    [asdict(r) for r in rates],
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                digest = sha256(normalized).hexdigest()
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
                    tmp.write_bytes(normalized)
                    tmp.replace(self.path)

                meta.update({
                    "provider": "Trading Economics",
                    "last_checked": now.isoformat(timespec="seconds"),
                    "last_download": now.isoformat(timespec="seconds"),
                    "content_sha256": digest,
                    "rate_count": len(rates),
                    "last_error": "",
                })
                self._write_meta(meta)
                return changed, ("macro policy cache updated" if changed
                                 else "macro policy checked; no content changes")
            except HTTPError as exc:
                msg = f"HTTP {exc.code}: {exc.reason}"
            except (URLError, TimeoutError, OSError, ValueError,
                    json.JSONDecodeError) as exc:
                msg = f"{type(exc).__name__}: {exc}"

            meta["last_checked"] = now.isoformat(timespec="seconds")
            meta["last_error"] = msg
            self._write_meta(meta)
            return False, f"macro policy refresh failed: {msg}"

    def ensure_local(self) -> bool:
        if self.load_rates():
            self.maybe_refresh_async()
            return True
        if api_key_configured():
            self.refresh(force=True)
        return bool(self.load_rates())

    def maybe_refresh_async(self) -> bool:
        if not api_key_configured() or not self.refresh_due():
            return False
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return False

        def worker() -> None:
            self.refresh(force=False)

        self._refresh_thread = threading.Thread(
            target=worker, name="SwingDeskMacroPolicyRefresh", daemon=True)
        self._refresh_thread.start()
        return True

    def status(self) -> MacroPolicyStatus:
        meta = self._read_meta()
        rates = self.load_rates()
        return MacroPolicyStatus(
            path=self.path,
            exists=self.path.exists(),
            rate_count=len(rates),
            last_checked=str(meta.get("last_checked", "")),
            last_download=str(meta.get("last_download", "")),
            content_sha256=str(meta.get("content_sha256", "")),
            last_error=str(meta.get("last_error", "")),
            api_key_configured=api_key_configured(),
        )


_CACHE: MacroPolicyCache | None = None
_CACHE_KEY: str | None = None


def shared_macro_policy_cache() -> MacroPolicyCache:
    global _CACHE, _CACHE_KEY
    path = default_policy_path()
    key = str(path)
    if _CACHE is None or _CACHE_KEY != key:
        _CACHE = MacroPolicyCache(path)
        _CACHE_KEY = key
    return _CACHE
