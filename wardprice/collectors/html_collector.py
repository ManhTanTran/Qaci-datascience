"""Configured HTML/JSON-LD adapter shared by explicitly reviewed source sites."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .base import BaseCollector
from .models import CollectionTarget, DiscoveredUrl
from .parsing import discover_listing_urls, extract_listing_detail
from .policy import RobotsAwareClient
from .source_registry import format_search_url


class ConfiguredHTMLCollector(BaseCollector):
    """Generic adapter driven by one source's reviewed URL rules and page evidence."""

    def __init__(self, source: dict[str, Any], target: CollectionTarget, client: RobotsAwareClient):
        self.source = source
        self.target = target
        self.client = client
        self.source_name = str(source["display_name"])

    def discover(
        self, target: CollectionTarget, property_type: str, limit: int
    ) -> list[DiscoveredUrl]:
        response = self.client.fetch(
            format_search_url(self.source, target, property_type), purpose="search"
        )
        return discover_listing_urls(
            response.body,
            page_url=response.url,
            domains=[self.client.host.removeprefix("www.")],
            detail_path_regex=self.source["detail_path_regex"],
            limit=limit,
        )

    def extract(self, listing_url: str) -> dict[str, Any]:
        response = self.client.fetch(listing_url, purpose="listing_detail")
        listing_id = None
        pattern = str(self.source.get("listing_id_regex") or "")
        if pattern:
            match = re.search(pattern, listing_url)
            if match:
                listing_id = match.group(1) if match.groups() else match.group(0)
        candidate = extract_listing_detail(
            response.body,
            target_rank=self.target.rank,
            target_ward=self.target.current_ward or self.target.ward,
            target_district=self.target.district,
            target_province=self.target.current_province or self.target.province,
            source_url=response.url,
            source_id=listing_id,
            fetched_at=datetime.fromisoformat(response.fetched_at)
            .astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
            .isoformat(timespec="seconds"),
        )
        return candidate

    def health_check(self) -> dict[str, Any]:
        return self.client.health_check()
