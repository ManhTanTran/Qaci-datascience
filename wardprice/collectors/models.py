"""Models shared by the policy-gated public listing collector."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CollectionTarget:
    rank: int
    ward: str
    district: str
    province: str
    mapping_status: str
    administrative_unit_id: int | None = None
    administrative_code: str | None = None
    current_ward: str | None = None
    current_province: str | None = None

    @classmethod
    def from_row(cls, row: Any) -> CollectionTarget:
        keys = set(row.keys()) if hasattr(row, "keys") else set(row)
        return cls(
            int(row["rank"]),
            row["old_ward"],
            row["old_district"],
            row["old_province"],
            row["status"] if "status" in keys else "PENDING_ADMIN_MAPPING",
            None,
            (row["current_ward_code"] or None) if "current_ward_code" in keys else None,
            row["current_ward"] if "current_ward" in keys and row["current_ward"] else None,
            row["current_province"] if "current_province" in keys and row["current_province"] else None,
        )

    def as_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveredUrl:
    url: str
    canonical_url: str
    url_type: str


@dataclass(frozen=True)
class ListingEvidence:
    target_rank: int
    original_ward: str
    original_district: str
    original_province: str
    property_type: str | None
    title: str
    address: str
    price_vnd: float | None
    area_m2: float | None
    area_basis: str
    source_listing_id: str | None
    source_url: str
    canonical_url: str
    source_domain: str
    listed_date: str | None
    expires_at: str | None
    evidence_status: str
    validity_status: str
    evidence: dict[str, Any]
    raw_payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    fetched_at: str
    retry_after: str | None = None


@dataclass(slots=True)
class CollectorResult:
    """Auditable result of one source/target collection attempt."""

    source_name: str
    target_rank: int
    collected_at: str
    listing_candidates: list[dict[str, Any]]
    discovered_urls: list[DiscoveredUrl]
    extraction_errors: list[dict[str, str]]
    collection_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "target_rank": self.target_rank,
            "collected_at": self.collected_at,
            "listing_candidates": self.listing_candidates,
            "discovered_urls": [
                {"url": row.url, "canonical_url": row.canonical_url, "url_type": row.url_type}
                for row in self.discovered_urls
            ],
            "extraction_errors": self.extraction_errors,
            "collection_status": self.collection_status,
        }
