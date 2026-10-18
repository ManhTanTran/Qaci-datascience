"""Offline import of saved Gemini JSON into the isolated candidate warehouse.

Imported candidates never enter the canonical listings, observations, or
statistics tables. Batch bytes and per-row dispositions are retained for audit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .core import VALID_TYPES, geo_check, norm, parse_json_text

_CONFLICT_TERMS = ("conflict", "xung dot", "mau thuan", "khong khop")
_CATEGORY_PATHS = {
    "bat-dong-san",
    "mua-ban-bat-dong-san",
    "mua-ban-nha-dat",
    "nha-dat",
    "real-estate",
}
_DETAIL_PATH_MARKERS = ("/pr", "/tin-", "/listing/", "/detail/", "/p/")


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "")
        if re.fullmatch(r"[+-]?\d+", cleaned):
            return int(cleaned)
        if re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", cleaned):
            return int(cleaned.replace(",", "").replace(".", ""))
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return parsed


def _parse_run_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def classify_source_url_type(source_url: Any, declared_type: Any = None) -> str:
    """Classify URL shape conservatively; a category URL is never an identity key."""
    url = _as_text(source_url)
    if not url:
        return "UNKNOWN"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "UNKNOWN"
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        return "UNKNOWN"
    path = parts.path.casefold().rstrip("/")
    segments = [segment for segment in path.split("/") if segment]
    declared = _as_text(declared_type).upper()
    first = segments[0] if segments else ""
    if declared == "CATEGORY":
        return "CATEGORY"
    has_listing_id = bool(segments and re.search(r"(?:^|[-_/])(?:id)?\d{5,}$", segments[-1]))
    if any(marker in path for marker in _DETAIL_PATH_MARKERS) or has_listing_id:
        return "DIRECT_LISTING"
    if first in _CATEGORY_PATHS and len(segments) <= 2:
        return "CATEGORY"
    if declared == "DIRECT_LISTING":
        return "DIRECT_LISTING"
    return "UNKNOWN"


def _identity_fingerprint(item: dict[str, Any]) -> str:
    """Use listing ID when present, otherwise a composite content identity."""
    rank = item["target_rank"]
    kind = item["property_type"]
    listing_id = _as_text(item.get("external_listing_id"))
    if listing_id:
        identity = ["source-id", rank, kind, norm(item.get("source_website")), norm(listing_id)]
    else:
        identity = [
            "content",
            rank,
            kind,
            norm(item.get("title")),
            norm(item.get("address")),
            item["price_vnd"],
            round(float(item["area_m2"]), 4),
        ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _warning_text(item: dict[str, Any], batch_warnings: list[str]) -> str:
    for key in ("source_conflict_warning", "conflict_warning", "review_warning", "warning"):
        value = item.get(key)
        if isinstance(value, list):
            value = "; ".join(_as_text(part) for part in value if _as_text(part))
        if _as_text(value):
            return _as_text(value)
    if item.get("possible_duplicate"):
        title = norm(item.get("title"))
        relevant = [
            warning
            for warning in batch_warnings
            if any(term in norm(warning) for term in _CONFLICT_TERMS)
            and (
                not title
                or any(token in norm(warning) for token in title.split() if len(token) > 2)
            )
        ]
        if relevant:
            return "; ".join(relevant)
        conflict_warnings = [
            warning
            for warning in batch_warnings
            if any(term in norm(warning) for term in _CONFLICT_TERMS)
        ]
        if len(conflict_warnings) == 1:
            return conflict_warnings[0]
        if len(batch_warnings) == 1:
            return batch_warnings[0]
    return ""


def _geo_status_for_whitelist(
    address: str, target_rank: int, target: dict[str, Any], targets: dict[int, dict[str, Any]]
) -> str:
    status = geo_check(address, target["ward"])
    if status != "REVIEW":
        return status
    normalized_address = norm(address)
    for rank, other in targets.items():
        if rank == target_rank:
            continue
        other_ward = norm(other["ward"])
        other_name = re.sub(r"^(?:phuong|xa|thi tran)\s+", "", other_ward)
        if other_name and re.search(
            r"\b(?:phuong|xa|thi tran)\s+" + re.escape(other_name) + r"\b",
            normalized_address,
        ):
            return "MISMATCH"
    return status


def _prepare_item(
    item: Any,
    *,
    row_index: int,
    batch_rank: int,
    batch_ward: str,
    run_date: str,
    targets: dict[int, dict[str, Any]],
    batch_warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "not_an_object",
            "raw_payload": json.dumps(item, ensure_ascii=False),
        }

    raw = dict(item)
    raw.setdefault("target_rank", batch_rank)
    raw.setdefault("original_ward", batch_ward)
    raw.setdefault("collected_at", run_date)

    try:
        rank = _as_int(raw.get("target_rank"))
        target = targets.get(rank) if rank is not None else None
    except (TypeError, ValueError):
        rank, target = None, None
    if target is None or rank != batch_rank:
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "target_rank_not_in_batch_whitelist",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }
    if norm(raw.get("original_ward")) != norm(target["ward"]):
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "target_ward_disagrees_with_registry",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }

    property_type = _as_text(raw.get("property_type")).upper()
    if property_type not in VALID_TYPES:
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "bad_property_type",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }

    title = _as_text(raw.get("title"))
    address = _as_text(raw.get("address"))
    price = _as_int(raw.get("price_vnd"))
    area_value = raw.get("area_m2")
    if isinstance(area_value, str):
        area_value = (
            area_value.strip().replace(",", ".")
            if "," in area_value and "." not in area_value
            else area_value
        )
    try:
        area = float(area_value)
    except (TypeError, ValueError, OverflowError):
        area = 0.0
    if len(title) < 5 or len(address) < 4:
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "missing_title_or_address",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }
    if price is None or price <= 0 or price > 10**16 or not (0 < area < 10_000_000):
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "bad_price_or_area",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }

    requested_evidence = _as_text(raw.get("evidence_status")).upper()
    if requested_evidence == "DEMO_SYNTHETIC":
        return {
            "row_index": row_index,
            "disposition": "REJECTED",
            "reason": "demo_synthetic_not_allowed_in_candidate_import",
            "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
        }
    # No saved Gemini claim can promote an imported record to source-verified.
    evidence_status = (
        "SEARCH_SNIPPET_ONLY" if requested_evidence == "SEARCH_SNIPPET_ONLY" else "UNVERIFIED"
    )

    source_url = _as_text(raw.get("source_url") or raw.get("listing_url") or raw.get("url")) or None
    source_url_type = classify_source_url_type(source_url, raw.get("source_url_type"))
    source_website = _as_text(raw.get("source_website")) or None
    try:
        source_domain = urlsplit(source_url).hostname if source_url else None
    except ValueError:
        source_domain = None
    source_domain = source_domain.casefold().removeprefix("www.") if source_domain else None
    geo_status = _geo_status_for_whitelist(address, rank, target, targets)
    possible_duplicate = raw.get("possible_duplicate") is True
    review_warning = _warning_text(raw, batch_warnings)
    warning_has_conflict = any(term in norm(review_warning) for term in _CONFLICT_TERMS)
    if geo_status == "MISMATCH":
        disposition, reason = "QUARANTINED", "GEO_MISMATCH"
        review_status = "GEO_QUARANTINE"
    else:
        disposition, reason = "ACCEPTED", None
        review_status = (
            "SOURCE_CONFLICT"
            if warning_has_conflict and possible_duplicate
            else "NEEDS_REVIEW"
            if possible_duplicate
            else "NEEDS_SOURCE_REVIEW"
        )

    prepared = {
        "row_index": row_index,
        "disposition": disposition,
        "reason": reason,
        "target_rank": rank,
        "original_ward": target["ward"],
        "original_district": target["district"],
        "original_province": target["province"],
        "property_type": property_type,
        "title": title,
        "address": address,
        "price_vnd": price,
        "area_m2": area,
        "price_per_m2": price / area,
        "source_website": source_website,
        "source_url": source_url,
        "source_domain": source_domain,
        "source_url_type": source_url_type,
        "external_listing_id": next(
            (
                _as_text(raw.get(key))
                for key in ("listing_id", "source_listing_id", "listing_code", "ad_id")
                if _as_text(raw.get(key))
            ),
            None,
        ),
        "listed_date": _parse_run_date(raw.get("listed_date") or raw.get("published_at")),
        "run_date": run_date,
        "evidence_status": evidence_status,
        "requested_evidence_status": requested_evidence,
        "verification_label": "Chưa xác minh nguồn",
        "geo_status": geo_status,
        "possible_duplicate": possible_duplicate,
        "review_status": review_status,
        "review_warning": review_warning,
        "source_page_read": False,
        "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
    }
    prepared["candidate_fingerprint"] = _identity_fingerprint(prepared)
    return prepared


def prepare_batch(
    raw_text: str,
    targets: dict[int, dict[str, Any]],
    *,
    expected_rank: int | None = None,
) -> dict[str, Any]:
    payload = parse_json_text(raw_text)
    if not isinstance(payload, dict):
        raise TypeError("Gemini batch must be a JSON object containing a listings array")
    listings = payload.get("listings")
    if not isinstance(listings, list):
        raise TypeError("Gemini batch is missing a listings array")
    if len(listings) > 500:
        raise ValueError("Candidate batch is too large (>500)")

    raw_rank = payload.get("target_rank")
    if raw_rank is None:
        ranks = {_as_int(item.get("target_rank")) for item in listings if isinstance(item, dict)}
        ranks.discard(None)
        if len(ranks) == 1:
            raw_rank = next(iter(ranks))
    batch_rank = _as_int(raw_rank)
    if batch_rank is None or batch_rank not in targets:
        raise ValueError("Batch needs a target_rank present in ward_target_legacy")
    if expected_rank is not None and batch_rank != expected_rank:
        raise ValueError(f"Batch rank {batch_rank} does not match requested rank {expected_rank}")

    target = targets[batch_rank]
    batch_ward = _as_text(payload.get("original_ward")) or _as_text(target["ward"])
    if norm(batch_ward) != norm(target["ward"]):
        raise ValueError("Batch original_ward disagrees with ward_target_legacy")
    raw_date = payload.get("run_date") or payload.get("collected_at") or payload.get("date")
    if raw_date is None:
        dates = {
            _parse_run_date(item.get("collected_at") or item.get("published_at"))
            for item in listings
            if isinstance(item, dict)
        }
        dates.discard(None)
        if len(dates) == 1:
            raw_date = next(iter(dates))
    run_date = _parse_run_date(raw_date)
    if not run_date:
        raise ValueError("Batch needs a valid run_date or collected_at date")

    batch_warnings: list[str] = []
    for warning_key in (
        "warnings",
        "warning",
        "source_conflict_warnings",
        "source_conflict_warning",
        "conflicts",
    ):
        raw_warnings = payload.get(warning_key)
        if not raw_warnings:
            continue
        values = raw_warnings if isinstance(raw_warnings, list) else [raw_warnings]
        batch_warnings.extend(_as_text(value) for value in values if _as_text(value))

    prepared_rows = [
        _prepare_item(
            item,
            row_index=index,
            batch_rank=batch_rank,
            batch_ward=batch_ward,
            run_date=run_date,
            targets=targets,
            batch_warnings=batch_warnings,
        )
        for index, item in enumerate(listings, start=1)
    ]
    seen: set[str] = set()
    for row in prepared_rows:
        fingerprint = row.get("candidate_fingerprint")
        if row["disposition"] == "ACCEPTED" and fingerprint:
            if fingerprint in seen:
                row["disposition"] = "DUPLICATE"
                row["reason"] = "duplicate_within_batch_composite_identity"
            else:
                seen.add(fingerprint)

    batch_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    actual_collected = _as_int(payload.get("actual_collected"))
    return {
        "batch_sha256": batch_sha256,
        "target": target,
        "target_rank": batch_rank,
        "run_date": run_date,
        "target_count": _as_int(payload.get("target_count")),
        "actual_collected": actual_collected if actual_collected is not None else len(listings),
        "received": len(listings),
        "raw_batch_json": raw_text,
        "batch_metadata": payload,
        "batch_warnings": batch_warnings,
        "rows": prepared_rows,
        "rejected_count": sum(row["disposition"] == "REJECTED" for row in prepared_rows),
        "quarantined_count": sum(row["disposition"] == "QUARANTINED" for row in prepared_rows),
        "duplicate_count": sum(row["disposition"] == "DUPLICATE" for row in prepared_rows),
        "accepted_count": sum(row["disposition"] == "ACCEPTED" for row in prepared_rows),
        "statistics_eligible_count": 0,
        "network_attempted": False,
        "production_database_written": False,
        "demo_database_written": False,
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone()
        is not None
    )


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS webpilot_candidate_batches (
            batch_sha256 TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            target_rank INTEGER NOT NULL,
            original_ward TEXT NOT NULL,
            run_date TEXT NOT NULL,
            target_count INTEGER,
            actual_collected INTEGER NOT NULL,
            received_count INTEGER NOT NULL,
            accepted_count INTEGER NOT NULL,
            quarantined_count INTEGER NOT NULL,
            duplicate_count INTEGER NOT NULL,
            rejected_count INTEGER NOT NULL,
            observations_added INTEGER NOT NULL DEFAULT 0,
            raw_batch_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS webpilot_batch_candidates (
            candidate_fingerprint TEXT PRIMARY KEY,
            target_rank INTEGER NOT NULL,
            original_ward TEXT NOT NULL,
            original_district TEXT NOT NULL,
            original_province TEXT NOT NULL,
            property_type TEXT NOT NULL,
            title TEXT NOT NULL,
            address TEXT NOT NULL,
            price_vnd INTEGER NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            source_website TEXT,
            source_url TEXT,
            source_domain TEXT,
            source_url_type TEXT NOT NULL,
            external_listing_id TEXT,
            listed_date TEXT,
            first_run_date TEXT NOT NULL,
            last_seen_date TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            verification_label TEXT NOT NULL,
            geo_status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            review_warning TEXT NOT NULL,
            possible_duplicate INTEGER NOT NULL,
            quarantine_reason TEXT,
            source_page_read INTEGER NOT NULL,
            raw_payload TEXT NOT NULL,
            first_batch_sha256 TEXT NOT NULL,
            FOREIGN KEY(first_batch_sha256) REFERENCES webpilot_candidate_batches(batch_sha256)
        );
        CREATE INDEX IF NOT EXISTS ix_webpilot_batch_candidates_rank
            ON webpilot_batch_candidates(target_rank, property_type, first_run_date);
        CREATE TABLE IF NOT EXISTS webpilot_candidate_batch_rows (
            batch_sha256 TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            candidate_fingerprint TEXT,
            disposition TEXT NOT NULL,
            reason TEXT,
            raw_payload TEXT NOT NULL,
            PRIMARY KEY(batch_sha256, row_index),
            FOREIGN KEY(batch_sha256) REFERENCES webpilot_candidate_batches(batch_sha256)
        );
        CREATE TABLE IF NOT EXISTS webpilot_batch_observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_fingerprint TEXT NOT NULL,
            target_rank INTEGER NOT NULL,
            run_date TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            price_vnd INTEGER NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            evidence_status TEXT NOT NULL,
            batch_sha256 TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            UNIQUE(candidate_fingerprint, run_date),
            FOREIGN KEY(candidate_fingerprint) REFERENCES webpilot_batch_candidates(candidate_fingerprint),
            FOREIGN KEY(batch_sha256) REFERENCES webpilot_candidate_batches(batch_sha256)
        );
        """
    )
    connection.commit()


def _existing_fingerprints(connection: sqlite3.Connection) -> set[str]:
    fingerprints: set[str] = set()
    if _table_exists(connection, "webpilot_batch_candidates"):
        fingerprints.update(
            str(row[0])
            for row in connection.execute(
                "SELECT candidate_fingerprint FROM webpilot_batch_candidates"
            )
        )
    if _table_exists(connection, "webpilot_candidates"):
        legacy_rows = connection.execute(
            """SELECT target_rank,property_type,title,address,price_vnd,area_m2,
                      source_website,raw_payload FROM webpilot_candidates"""
        ).fetchall()
        for row in legacy_rows:
            try:
                raw = json.loads(row["raw_payload"] or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            external_id = next(
                (
                    _as_text(raw.get(key))
                    for key in ("listing_id", "source_listing_id", "listing_code", "ad_id")
                    if _as_text(raw.get(key))
                ),
                None,
            )
            fingerprints.add(
                _identity_fingerprint(
                    {
                        "target_rank": row["target_rank"],
                        "property_type": row["property_type"],
                        "title": row["title"],
                        "address": row["address"],
                        "price_vnd": row["price_vnd"],
                        "area_m2": row["area_m2"],
                        "source_website": row["source_website"],
                        "external_listing_id": external_id,
                    }
                )
            )
    return fingerprints


def preview_against_database(
    prepared: dict[str, Any], connection: sqlite3.Connection | None
) -> dict[str, Any]:
    report = dict(prepared)
    rows = [dict(row) for row in prepared["rows"]]
    already_imported = False
    existing: set[str] = set()
    if connection is not None:
        if _table_exists(connection, "webpilot_candidate_batches"):
            already_imported = (
                connection.execute(
                    "SELECT 1 FROM webpilot_candidate_batches WHERE batch_sha256=?",
                    (prepared["batch_sha256"],),
                ).fetchone()
                is not None
            )
        existing = _existing_fingerprints(connection)
    if already_imported:
        for row in rows:
            if row["disposition"] == "ACCEPTED":
                row["disposition"] = "DUPLICATE"
                row["reason"] = "batch_already_imported"
    else:
        new_candidates = 0
        for row in rows:
            fingerprint = row.get("candidate_fingerprint")
            if row["disposition"] == "ACCEPTED" and fingerprint in existing:
                row["disposition"] = "DUPLICATE"
                row["reason"] = "candidate_exists_in_warehouse"
            elif row["disposition"] == "ACCEPTED":
                if len(existing) + new_candidates >= 500:
                    row["disposition"] = "REJECTED"
                    row["reason"] = "candidate_limit_reached"
                else:
                    new_candidates += 1
    report["rows"] = rows
    report["already_imported"] = already_imported
    report["accepted_count"] = sum(row["disposition"] == "ACCEPTED" for row in rows)
    report["duplicate_count"] = sum(row["disposition"] == "DUPLICATE" for row in rows)
    report["quarantined_count"] = sum(row["disposition"] == "QUARANTINED" for row in rows)
    report["rejected_count"] = sum(row["disposition"] == "REJECTED" for row in rows)
    report["source_url_type_counts"] = dict(
        Counter(
            row.get("source_url_type", "UNKNOWN")
            for row in rows
            if row.get("candidate_fingerprint")
        )
    )
    report["evidence_status_counts"] = dict(
        Counter(
            row.get("evidence_status", "UNVERIFIED")
            for row in rows
            if row.get("candidate_fingerprint")
        )
    )
    report["review_status_counts"] = dict(
        Counter(
            row.get("review_status", "REJECTED") for row in rows if row.get("candidate_fingerprint")
        )
    )
    report["tracked_candidate_count_before_import"] = len(existing)
    return report


def apply_batch(
    connection: sqlite3.Connection,
    prepared: dict[str, Any],
    *,
    source_file: str,
) -> dict[str, Any]:
    ensure_schema(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        if connection.execute(
            "SELECT 1 FROM webpilot_candidate_batches WHERE batch_sha256=?",
            (prepared["batch_sha256"],),
        ).fetchone():
            connection.rollback()
            return preview_against_database(prepared, connection) | {
                "status": "ALREADY_IMPORTED",
                "inserted_candidates": 0,
                "observations_added": 0,
            }

        result = preview_against_database(prepared, connection)
        rows = result["rows"]
        result["source_file"] = source_file
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result_json = json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"rows", "raw_batch_json", "batch_metadata", "batch_warnings"}
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        connection.execute(
            """INSERT INTO webpilot_candidate_batches(
                batch_sha256,source_file,target_rank,original_ward,run_date,target_count,
                actual_collected,received_count,accepted_count,quarantined_count,duplicate_count,
                rejected_count,observations_added,raw_batch_json,result_json,imported_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                prepared["batch_sha256"],
                source_file,
                prepared["target_rank"],
                prepared["target"]["ward"],
                prepared["run_date"],
                prepared["target_count"],
                prepared["actual_collected"],
                prepared["received"],
                result["accepted_count"],
                result["quarantined_count"],
                result["duplicate_count"],
                result["rejected_count"],
                0,
                prepared["raw_batch_json"],
                result_json,
                now,
            ),
        )

        inserted = observations_added = 0
        for row in rows:
            raw_payload = row.get("raw_payload", "null")
            connection.execute(
                """INSERT INTO webpilot_candidate_batch_rows(
                    batch_sha256,row_index,candidate_fingerprint,disposition,reason,raw_payload
                ) VALUES(?,?,?,?,?,?)""",
                (
                    prepared["batch_sha256"],
                    row["row_index"],
                    row.get("candidate_fingerprint"),
                    row["disposition"],
                    row.get("reason"),
                    raw_payload,
                ),
            )
            if row["disposition"] not in {"ACCEPTED", "DUPLICATE"}:
                continue
            fingerprint = row["candidate_fingerprint"]
            if row["disposition"] == "ACCEPTED":
                connection.execute(
                    """INSERT INTO webpilot_batch_candidates(
                        candidate_fingerprint,target_rank,original_ward,original_district,
                        original_province,property_type,title,address,price_vnd,area_m2,
                        price_per_m2,source_website,source_url,source_domain,source_url_type,
                        external_listing_id,listed_date,first_run_date,last_seen_date,evidence_status,
                        verification_label,geo_status,review_status,review_warning,possible_duplicate,
                        quarantine_reason,source_page_read,raw_payload,first_batch_sha256
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        fingerprint,
                        row["target_rank"],
                        row["original_ward"],
                        row["original_district"],
                        row["original_province"],
                        row["property_type"],
                        row["title"],
                        row["address"],
                        row["price_vnd"],
                        row["area_m2"],
                        row["price_per_m2"],
                        row["source_website"],
                        row["source_url"],
                        row["source_domain"],
                        row["source_url_type"],
                        row["external_listing_id"],
                        row["listed_date"],
                        row["run_date"],
                        row["run_date"],
                        row["evidence_status"],
                        row["verification_label"],
                        row["geo_status"],
                        row["review_status"],
                        row["review_warning"],
                        int(row["possible_duplicate"]),
                        row["reason"],
                        0,
                        raw_payload,
                        prepared["batch_sha256"],
                    ),
                )
                inserted += 1
            elif not connection.execute(
                "SELECT 1 FROM webpilot_batch_candidates WHERE candidate_fingerprint=?",
                (fingerprint,),
            ).fetchone():
                # A matching candidate may live in the original live-pilot table.
                # Keep the batch row audit, but do not create an orphan observation.
                continue
            cursor = connection.execute(
                """INSERT OR IGNORE INTO webpilot_batch_observations(
                    candidate_fingerprint,target_rank,run_date,observed_at,price_vnd,area_m2,
                    price_per_m2,evidence_status,batch_sha256,raw_payload
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    fingerprint,
                    row["target_rank"],
                    row["run_date"],
                    now,
                    row["price_vnd"],
                    row["area_m2"],
                    row["price_per_m2"],
                    row["evidence_status"],
                    prepared["batch_sha256"],
                    raw_payload,
                ),
            )
            observations_added += cursor.rowcount

        result["inserted_candidates"] = inserted
        result["observations_added"] = observations_added
        result["status"] = "IMPORTED"
        connection.execute(
            "UPDATE webpilot_candidate_batches SET observations_added=?,result_json=? WHERE batch_sha256=?",
            (
                observations_added,
                json.dumps(
                    {
                        key: value
                        for key, value in result.items()
                        if key not in {"rows", "raw_batch_json", "batch_metadata", "batch_warnings"}
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
                prepared["batch_sha256"],
            ),
        )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def backup_before_candidate_schema(database_path: Path) -> Path | None:
    """Take a SQLite-consistent snapshot before batch tables are created."""
    if not database_path.is_file():
        return None
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = backup_dir / f"{database_path.stem}.before_candidate_import_{stamp}.sqlite3"
    backup_path = base
    suffix = 1
    while backup_path.exists():
        backup_path = base.with_name(f"{base.stem}_{suffix}{base.suffix}")
        suffix += 1
    with sqlite3.connect(str(database_path)) as source, sqlite3.connect(str(backup_path)) as target:
        source.backup(target)
    with sqlite3.connect(f"file:{backup_path.resolve().as_posix()}?mode=ro", uri=True) as check:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            backup_path.unlink(missing_ok=True)
            raise sqlite3.DatabaseError(f"Sidecar backup integrity check failed: {integrity}")
    return backup_path


def open_existing_readonly(database_path: Path) -> sqlite3.Connection | None:
    if not database_path.is_file():
        return None
    connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def assert_isolated_audit_database(database_path: Path, targets_database: Path) -> None:
    if database_path.resolve() == targets_database.resolve():
        raise ValueError("Refusing to import candidate batch into the production target database")
    if not database_path.is_file():
        return
    connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    if "demo_meta" in names:
        raise ValueError("Refusing to import real Gemini candidates into a DEMO_MODE database")
    if "ward_target_legacy" in names and "webpilot_candidates" not in names:
        raise ValueError(
            "Refusing to import candidate batch into a canonical WardPriceDaily database"
        )
