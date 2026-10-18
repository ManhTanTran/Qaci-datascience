"""Provider contract tests use in-process mocks and never access the network."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from wardprice.database import connect
from wardprice.providers import (
    DisabledProvider,
    ProviderResult,
    fetch_with_policy,
)


class MockProvider:
    def __init__(self, result=None, delay=0):
        self.result = result or ProviderResult(
            records=[{"price_vnd": 100}],
            source="mock",
            status="SUCCESS",
            provenance={"network_called": True, "source_url": "https://mock.example/listing/1"},
        )
        self.delay = delay
        self.calls = 0

    async def fetch(self, ward, property_type):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


def test_disabled_provider_never_reports_network_call():
    result = asyncio.run(DisabledProvider().fetch({"unit_id": 1}, "DAT_O"))
    assert result.status == "EXTERNAL_PROVIDER_NOT_CONFIGURED"
    assert result.provenance["network_called"] is False


def test_mock_provider_uses_cooldown_and_returns_structured_result(tmp_path):
    db = connect(tmp_path / "provider.sqlite3")
    provider = MockProvider()
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    try:
        first = asyncio.run(
            fetch_with_policy(
                db,
                provider,
                {"unit_id": 1},
                "DAT_O",
                unit_id=1,
                provider_name="mock",
                now=now,
            )
        )
        second = asyncio.run(
            fetch_with_policy(
                db,
                provider,
                {"unit_id": 1},
                "DAT_O",
                unit_id=1,
                provider_name="mock",
                now=now,
            )
        )
        assert first.status == "SUCCESS"
        assert first.records == [{"price_vnd": 100}]
        assert second.status == "COOLDOWN"
        assert second.provenance["network_called"] is False
        assert provider.calls == 1
    finally:
        db.close()


def test_mock_provider_timeout_and_negative_cache_are_bounded(tmp_path):
    db = connect(tmp_path / "provider.sqlite3")
    timeout_provider = MockProvider(delay=0.05)
    no_data_provider = MockProvider(
        result=ProviderResult(status="NO_DATA", provenance={"network_called": True})
    )
    base = datetime(2026, 10, 13, tzinfo=timezone.utc)
    try:
        timeout = asyncio.run(
            fetch_with_policy(
                db,
                timeout_provider,
                {},
                "DAT_O",
                unit_id=1,
                provider_name="timeout",
                timeout_seconds=0.001,
                now=base,
            )
        )
        empty = asyncio.run(
            fetch_with_policy(
                db,
                no_data_provider,
                {},
                "DAT_O",
                unit_id=2,
                provider_name="mock-empty",
                now=base,
            )
        )
        cached = asyncio.run(
            fetch_with_policy(
                db,
                no_data_provider,
                {},
                "DAT_O",
                unit_id=2,
                provider_name="mock-empty",
                now=base,
            )
        )
        assert timeout.status == "TIMEOUT"
        assert empty.status == "NO_DATA"
        assert cached.status == "NEGATIVE_CACHE_HIT"
        assert no_data_provider.calls == 1
    finally:
        db.close()
