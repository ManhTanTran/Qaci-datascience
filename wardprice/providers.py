"""Price-provider contracts. V1 deliberately ships with external calls disabled."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


@dataclass
class ProviderResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    retrieval_time: str = ""
    status: str = "NOT_CONFIGURED"
    error: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


class PriceProvider(Protocol):
    async def fetch(self, ward: dict[str, Any], property_type: str | None) -> ProviderResult:
        """Fetch records from a specifically authorized provider."""


class DisabledProvider:
    """Safe default provider: reports that external retrieval is not configured."""

    async def fetch(self, ward: dict[str, Any], property_type: str | None) -> ProviderResult:
        del ward, property_type
        return ProviderResult(
            retrieval_time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status="EXTERNAL_PROVIDER_NOT_CONFIGURED",
            error="No authorized external price provider is configured.",
            provenance={"network_called": False},
        )


async def fetch_with_provider(
    provider: PriceProvider,
    ward: dict[str, Any],
    property_type: str | None,
    *,
    timeout_seconds: float = 5.0,
) -> ProviderResult:
    """Bound one explicitly selected provider call; callers choose whether to persist."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    try:
        result = await asyncio.wait_for(
            provider.fetch(ward, property_type), timeout=timeout_seconds
        )
    except TimeoutError:
        return ProviderResult(
            retrieval_time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status="TIMEOUT",
            error=f"Provider exceeded {timeout_seconds:g} second timeout.",
            provenance={"network_called": True},
        )
    if not isinstance(result, ProviderResult):
        raise TypeError("PriceProvider.fetch must return ProviderResult")
    return result


async def fetch_with_policy(
    db: sqlite3.Connection,
    provider: PriceProvider,
    ward: dict[str, Any],
    property_type: str | None,
    *,
    unit_id: int,
    provider_name: str,
    timeout_seconds: float = 5.0,
    cooldown_seconds: int = 60,
    negative_cache_seconds: int = 86400,
    now: datetime | None = None,
) -> ProviderResult:
    """Apply per-unit/property cooldown and negative caching to one provider."""
    current = now or datetime.now(timezone.utc)
    current_text = current.astimezone(timezone.utc).isoformat(timespec="seconds")
    row = db.execute(
        """SELECT next_allowed_attempt,negative_cache_until FROM provider_fetch_state
           WHERE administrative_unit_id=? AND property_type=? AND provider=?""",
        (unit_id, property_type or "*", provider_name),
    ).fetchone()
    if row:
        negative_until = row["negative_cache_until"]
        if negative_until and negative_until > current_text:
            return ProviderResult(
                retrieval_time=current_text,
                status="NEGATIVE_CACHE_HIT",
                error="A recent provider lookup returned no usable records.",
                provenance={"network_called": False},
            )
        next_allowed = row["next_allowed_attempt"]
        if next_allowed and next_allowed > current_text:
            return ProviderResult(
                retrieval_time=current_text,
                status="COOLDOWN",
                error="Provider cooldown is active for this ward and property type.",
                provenance={"network_called": False},
            )
    next_allowed = (current + timedelta(seconds=max(0, cooldown_seconds))).isoformat(
        timespec="seconds"
    )
    with db:
        db.execute(
            """INSERT INTO provider_fetch_state(
               administrative_unit_id,property_type,provider,last_attempt,last_success,
               next_allowed_attempt,status,error,negative_cache_until,updated_at
               ) VALUES(?,?,?, ?,NULL,?,'RUNNING',NULL,NULL,?)
               ON CONFLICT(administrative_unit_id,property_type,provider) DO UPDATE SET
               last_attempt=excluded.last_attempt,next_allowed_attempt=excluded.next_allowed_attempt,
               status='RUNNING',error=NULL,updated_at=excluded.updated_at""",
            (unit_id, property_type or "*", provider_name, current_text, next_allowed, current_text),
        )
    result = await fetch_with_provider(
        provider, ward, property_type, timeout_seconds=timeout_seconds
    )
    network_called = bool(result.provenance.get("network_called"))
    negative_until = None
    last_success = None
    if result.status in {"NO_DATA", "EMPTY", "NO_LISTINGS"}:
        negative_until = (current + timedelta(seconds=max(0, negative_cache_seconds))).isoformat(
            timespec="seconds"
        )
    elif result.status in {"SUCCESS", "OK"} and result.records:
        last_success = result.retrieval_time or current_text
    elif result.status == "EXTERNAL_PROVIDER_NOT_CONFIGURED":
        negative_until = None
    error = result.error or ""
    with db:
        db.execute(
            """UPDATE provider_fetch_state SET last_success=COALESCE(?,last_success),
               status=?,error=?,negative_cache_until=?,updated_at=?
               WHERE administrative_unit_id=? AND property_type=? AND provider=?""",
            (
                last_success,
                result.status,
                error[:1000],
                negative_until,
                current_text,
                unit_id,
                property_type or "*",
                provider_name,
            ),
        )
    result.provenance.setdefault("network_called", network_called)
    return result

