"""Verified-only import bridge into WardPriceDaily's canonical listing tables."""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter, defaultdict
from typing import Any

from wardprice.database import now_utc, record_listing, tracked_listing_count
from wardprice.registry import Ward
from wardprice.validate import LISTING_EVIDENCE_STATUSES, normalize_listing

from .core import geo_check


def _prepare_handoff(
    connection: sqlite3.Connection, payload: dict[str, Any]
) -> tuple[list[tuple[dict[str, Any], Ward]], list[dict[str, Any]]]:
    listings = payload.get("listings") if isinstance(payload, dict) else None
    if not isinstance(listings, list):
        raise TypeError("Handoff must be an object with a listings array")
    if len(listings) > 500:
        raise ValueError("Handoff batch exceeds 500 records")

    legacy_targets = {
        row["rank"]: dict(row)
        for row in connection.execute(
            """SELECT rank,old_ward,old_district,old_province
               FROM ward_target_legacy ORDER BY rank"""
        )
    }
    active_wards = [
        Ward(row["ward_code"], row["ward_name"], row["province"], row["source"], row["district"])
        for row in connection.execute(
            """SELECT ward_code,ward_name,province,COALESCE(admin_source,'') AS source,district
               FROM ward_registry WHERE active=1"""
        )
    ]

    prepared: list[tuple[dict[str, Any], Ward]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(listings):
        if not isinstance(item, dict):
            rejected.append({"index": index, "reason": "listing is not an object"})
            continue
        try:
            rank = int(item["target_rank"])
            target = legacy_targets[rank]
        except (KeyError, TypeError, ValueError):
            rejected.append({"index": index, "reason": "target rank not in legacy registry"})
            continue
        if (
            str(item.get("original_ward", "")).casefold() != target["old_ward"].casefold()
            or str(item.get("original_district", "")).casefold()
            != target["old_district"].casefold()
            or str(item.get("original_province", "")).casefold()
            != target["old_province"].casefold()
        ):
            rejected.append({"index": index, "reason": "target labels disagree with legacy registry"})
            continue
        if geo_check(str(item.get("address", "")), target["old_ward"]) != "MATCH":
            rejected.append({"index": index, "reason": "address is mismatched or ambiguous"})
            continue

        matching_wards = [
            ward
            for ward in active_wards
            if ward.name.casefold() == target["old_ward"].casefold()
            and ward.province.casefold() == target["old_province"].casefold()
        ]
        if len(matching_wards) != 1:
            rejected.append(
                {"index": index, "reason": "no unique active whitelist match for legacy target"}
            )
            continue
        if item.get("evidence_status") not in LISTING_EVIDENCE_STATUSES:
            rejected.append({"index": index, "reason": "listing has no source evidence"})
            continue

        grounded_urls = item.get("grounded_urls")
        if not isinstance(grounded_urls, list):
            rejected.append({"index": index, "reason": "wrapper citation URLs are missing"})
            continue
        raw = {
            "ward_code": matching_wards[0].code,
            "ward_name": matching_wards[0].name,
            "province": matching_wards[0].province,
            "property_type": item.get("property_type"),
            "price_vnd": item.get("price_vnd"),
            "area_m2": item.get("area_m2"),
            "address": item.get("address"),
            "source_url": item.get("source_url"),
            "listed_date": item.get("published_at"),
            "evidence_status": item.get("evidence_status"),
            "source_page_read": item.get("source_page_read") is True,
            "price_evidence": item.get("price_evidence"),
            "area_evidence": item.get("area_evidence"),
            "evidence_excerpt": item.get("evidence_excerpt"),
            "webpilot_target_rank": rank,
            "webpilot_title": item.get("title"),
            "webpilot_wrapper": "gemini_webapi",
            "webpilot_grounded_urls": grounded_urls,
        }
        try:
            candidate = normalize_listing(raw, matching_wards[0], grounded_urls=grounded_urls)
        except (TypeError, ValueError) as exc:
            rejected.append({"index": index, "reason": str(exc)})
            continue
        if candidate["identity_key"] in seen_urls:
            rejected.append({"index": index, "reason": "duplicate canonical source URL in handoff"})
            continue
        seen_urls.add(candidate["identity_key"])
        prepared.append((candidate, matching_wards[0]))
    return prepared, rejected


def preview_webpilot_handoff(
    connection: sqlite3.Connection, payload: dict[str, Any]
) -> dict[str, Any]:
    prepared, rejected = _prepare_handoff(connection, payload)
    return {
        "mode": "DRY_RUN",
        "eligible_count": len(prepared),
        "tracked_listings": tracked_listing_count(connection),
        "eligible": [
            {
                "ward_code": ward.code,
                "ward_name": ward.name,
                "property_type": candidate["property_type"],
                "source_domain": candidate["source_domain"],
                "evidence_status": candidate["evidence_status"],
                "price_vnd": candidate["price_vnd"],
                "area_m2": candidate["area_m2"],
            }
            for candidate, ward in prepared
        ],
        "rejected_count": len(rejected),
        "rejected": rejected,
        "production_database_written": False,
        "note": "Only evidence-backed, whitelist-matched rows are eligible for import.",
    }


def import_webpilot_handoff(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    max_total: int = 500,
) -> dict[str, Any]:
    """Import eligible handoff rows through WardPriceDaily's canonical validator."""
    prepared, rejected = _prepare_handoff(connection, payload)
    if not prepared:
        return {
            "mode": "APPLY",
            "inserted": 0,
            "updated": 0,
            "rejected": len(rejected),
            "rejected_rows": rejected,
            "tracked_listings": tracked_listing_count(connection),
        }

    run_id = "webpilot-import-" + uuid.uuid4().hex[:16]
    started_at = now_utc().isoformat(timespec="seconds")
    per_ward = defaultdict(Counter)
    for ward in {ward.code: ward for _, ward in prepared}.values():
        connection.execute(
            """INSERT INTO listing_search_runs(run_id,ward_code,started_at,status,grounding_used,
               search_queries) VALUES(?,?,?,?,0,0)""",
            (run_id, ward.code, started_at, "IMPORTING_WEBPILOT"),
        )
    connection.commit()

    for candidate, ward in prepared:
        outcome = record_listing(connection, candidate, run_id, max_total=max_total)
        per_ward[ward.code][outcome] += 1
        if outcome in {"WARD_CONFLICT", "LIMIT_REACHED"}:
            rejected.append(
                {
                    "ward_code": ward.code,
                    "reason": "source URL belongs to another ward"
                    if outcome == "WARD_CONFLICT"
                    else "500-listing cap reached",
                    "raw_payload": candidate["raw_payload"],
                }
            )

    finished_at = now_utc().isoformat(timespec="seconds")
    for ward_code, counts in per_ward.items():
        inserted = counts["INSERTED"]
        updated = counts["UPDATED"]
        status = "IMPORTED_WEBPILOT" if inserted or updated else "REJECTED"
        connection.execute(
            """UPDATE listing_search_runs SET finished_at=?,status=?,accepted_count=?,
               updated_count=?,rejected_count=?,limit_skipped_count=?,grounding_used=0,
               search_queries=0 WHERE run_id=? AND ward_code=?""",
            (
                finished_at,
                status,
                inserted,
                updated,
                counts["WARD_CONFLICT"],
                counts["LIMIT_REACHED"],
                run_id,
                ward_code,
            ),
        )
    for item in rejected:
        connection.execute(
            """INSERT INTO listing_rejections(run_id,ward_code,rejected_at,reason,raw_payload)
               VALUES(?,?,?,?,?)""",
            (
                run_id,
                item.get("ward_code", ""),
                finished_at,
                item["reason"],
                json.dumps(item.get("raw_payload", item), ensure_ascii=False, sort_keys=True),
            ),
        )
    connection.commit()
    return {
        "mode": "APPLY",
        "run_id": run_id,
        "inserted": sum(counts["INSERTED"] for counts in per_ward.values()),
        "updated": sum(counts["UPDATED"] for counts in per_ward.values()),
        "rejected": len(rejected),
        "rejected_rows": rejected,
        "tracked_listings": tracked_listing_count(connection),
        "grounding_used": False,
        "note": "Wrapper citations are recorded in raw payload; this is not Google Search API grounding.",
    }
