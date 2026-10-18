"""Load and evaluate the explicit source authorization registry."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from wardprice.config import PROJECT_ROOT

from .storage import collection_settings, source_rows, sync_source_registry

DEFAULT_SOURCE_REGISTRY = PROJECT_ROOT / "config" / "collector_sources.json"
REQUIRED_TEMPLATE_FIELDS = {"query", "property_type"}


def load_source_registry(path: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("version") != 1 or not isinstance(data.get("sources"), list):
        raise ValueError("collector source registry must have version=1 and sources[]")
    ids: set[str] = set()
    for source in data["sources"]:
        source_id = str(source.get("source_id", "")).strip().casefold()
        if not source_id or source_id in ids:
            raise ValueError("source_id values must be present and unique")
        ids.add(source_id)
        base = urlsplit(str(source.get("base_url", "")))
        robots = urlsplit(str(source.get("robots_url", "")))
        if (
            base.scheme != "https"
            or not base.hostname
            or base.username
            or base.password
            or base.port not in {None, 443}
            or robots.scheme != "https"
            or robots.hostname != base.hostname
            or robots.username
            or robots.password
            or robots.port not in {None, 443}
        ):
            raise ValueError(f"{source_id}: base and robots URLs must use the same public HTTPS host")
        if source.get("enabled") and source.get("policy_status") != "APPROVED":
            raise ValueError(f"{source_id}: enabled sources must have policy_status=APPROVED")
        if source.get("enabled") and not str(source.get("permission_reference", "")).strip():
            raise ValueError(f"{source_id}: enabled source needs permission_reference")
        if source.get("enabled") and not source.get("search_url_template"):
            raise ValueError(f"{source_id}: enabled source needs a reviewed search_url_template")
        pattern = source.get("detail_path_regex", "")
        if pattern:
            re.compile(pattern)
        for key in ("crawl_delay_seconds", "daily_request_budget"):
            if float(source.get(key, 0)) < 0:
                raise ValueError(f"{source_id}: {key} cannot be negative")
    return data


def sync_registry(db, path: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, Any]:
    load_source_registry(path)
    return sync_source_registry(db, path)


def cooldown_is_active(value: str | None, *, now: datetime | None = None) -> bool:
    if not value:
        return False
    try:
        until = datetime.fromisoformat(value)
    except ValueError:
        return True
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return until > now


def source_readiness(db) -> dict[str, Any]:
    settings = collection_settings(db)
    sources = source_rows(db)
    ready = []
    blocked = []
    for source in sources:
        reasons = []
        if not settings.get("global_live_enabled"):
            reasons.append("GLOBAL_LIVE_DISABLED")
        if not source["enabled"]:
            reasons.append("SOURCE_DISABLED")
        if source["policy_status"] != "APPROVED":
            reasons.append("PERMISSION_NOT_APPROVED")
        if not source.get("permission_reference"):
            reasons.append("PERMISSION_REFERENCE_MISSING")
        if not source.get("search_url_template"):
            reasons.append("SEARCH_TEMPLATE_MISSING")
        if not source.get("detail_path_regex"):
            reasons.append("DIRECT_LISTING_PATTERN_MISSING")
        if cooldown_is_active(source.get("cooldown_until")):
            reasons.append("SOURCE_COOLDOWN_RECORDED")
        item = {"source_id": source["source_id"], "display_name": source["display_name"], "reasons": reasons}
        (blocked if reasons else ready).append(item)
    return {
        "global_live_enabled": bool(settings.get("global_live_enabled")),
        "auto_ingest_verified": bool(settings.get("auto_ingest_verified")),
        "ready_sources": ready,
        "blocked_sources": blocked,
        "ready_count": len(ready),
    }


def format_search_url(source: dict[str, Any], target, property_type: str) -> str:
    from urllib.parse import quote_plus

    template = str(source.get("search_url_template") or "")
    if not template:
        raise ValueError("source has no search URL template")
    query = " ".join(part for part in (target.ward, target.district, target.province) if part)
    values = {
        "query": quote_plus(query),
        "ward": quote_plus(target.current_ward or target.ward),
        "district": quote_plus(target.district),
        "province": quote_plus(target.current_province or target.province),
        "property_type": quote_plus(property_type),
        "target_rank": str(target.rank),
    }
    try:
        return template.format(**values)
    except KeyError as exc:
        raise ValueError(f"unknown search template placeholder: {exc.args[0]}") from exc
