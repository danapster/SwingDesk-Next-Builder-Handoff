from __future__ import annotations

import json

import pytest

from swingdesk.core.macro_policy import MacroPolicyCache


SAMPLE = [
    {
        "Country": "United States",
        "Category": "Interest Rate",
        "LatestValue": 4.0,
        "PreviousValue": 3.75,
        "LatestValueDate": "2026-09-17T00:00:00",
        "PreviousValueDate": "2026-07-30T00:00:00",
        "Source": "Federal Reserve",
        "SourceURL": "https://www.federalreserve.gov/",
    },
    {
        "Country": "Euro Area",
        "Category": "Interest Rate",
        "LatestValue": 2.5,
        "PreviousValue": 2.75,
        "LatestValueDate": "2026-09-10T00:00:00",
        "PreviousValueDate": "2026-07-24T00:00:00",
        "Source": "European Central Bank",
        "SourceURL": "https://www.ecb.europa.eu/",
    },
]


def test_macro_normalizes_rates_and_stance():
    rates = MacroPolicyCache._normalize_payload(SAMPLE)
    by_ccy = {r.currency: r for r in rates}
    assert by_ccy["USD"].rate == pytest.approx(4.0)
    assert by_ccy["USD"].stance == "HIKING"
    assert by_ccy["EUR"].stance == "EASING"


def test_macro_runtime_reads_local_json_and_computes_differential(tmp_path):
    path = tmp_path / "policy_rates.json"
    rates = MacroPolicyCache._normalize_payload(SAMPLE)
    path.write_text(json.dumps([r.__dict__ for r in rates]), encoding="utf-8")

    cache = MacroPolicyCache(path)
    loaded = cache.load_rates()
    assert len(loaded) == 2
    assert cache.differential("USD", "EUR") == pytest.approx(1.5)
    assert cache.differential("GBP", "EUR") is None


def test_macro_refresh_updates_local_cache(tmp_path, monkeypatch):
    path = tmp_path / "policy_rates.json"
    cache = MacroPolicyCache(path)
    raw = json.dumps(SAMPLE).encode("utf-8")

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self):
            return raw

    monkeypatch.setattr("swingdesk.core.macro_policy.urlopen",
                        lambda *_a, **_k: Response())
    changed, message = cache.refresh(force=True, api_key="test-key")
    assert changed is True
    assert "updated" in message
    assert path.exists()
    assert {r.currency for r in cache.load_rates()} == {"USD", "EUR"}


def test_macro_missing_key_preserves_existing_cache(tmp_path, monkeypatch):
    path = tmp_path / "policy_rates.json"
    rates = MacroPolicyCache._normalize_payload(SAMPLE)
    original = json.dumps([r.__dict__ for r in rates])
    path.write_text(original, encoding="utf-8")
    cache = MacroPolicyCache(path)
    monkeypatch.delenv("SWINGDESK_TE_API_KEY", raising=False)

    changed, message = cache.refresh(force=True)
    assert changed is False
    assert "not configured" in message
    assert path.read_text(encoding="utf-8") == original
    assert len(cache.load_rates()) == 2
