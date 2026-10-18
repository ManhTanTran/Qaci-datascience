"""Source-agnostic file ingestion into an isolated listing-candidate pilot.

This module deliberately has no network client. API/feed/crawler adapters must
produce the same listing payload and call :func:`ingest_payload` only after their
own source permission gate has passed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
import time
import tracemalloc
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .config import PROJECT_ROOT
from .national_registry import PROPERTY_TYPES, normalize_admin_name
from .price_warehouse import canonicalize_source_url, load_listing_payload

DEFAULT_PILOT_DB = PROJECT_ROOT / "state" / "ward_prices.ingestion_pilot.sqlite3"
DEFAULT_TARGETS_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_SOURCE_REGISTRY = PROJECT_ROOT / "config" / "ingestion_sources.json"
DEFAULT_INBOX = PROJECT_ROOT / "data" / "inbox"
DEFAULT_PROCESSING = PROJECT_ROOT / "data" / "processing"
DEFAULT_PROCESSED = PROJECT_ROOT / "data" / "processed"
DEFAULT_QUARANTINE = PROJECT_ROOT / "data" / "quarantine"
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DAILY_LISTING_GOAL = 500
TARGET_DAILY_LISTING_GOAL = 10
MAX_INPUT_ROWS = 10_000

SOURCE_TYPES = {
    "AUTHORIZED_API",
    "AUTHORIZED_FEED",
    "PARTNER_CSV",
    "PARTNER_JSON",
    "USER_SUPPLIED",
    "REVIEW_REQUIRED",
    "DISABLED",
}
PERMISSION_STATUSES = {"AUTHORIZED", "REVIEW_REQUIRED", "DISABLED"}
URL_TYPES = {"CATEGORY", "DIRECT_LISTING", "UNKNOWN"}
TRANSACTION_TYPES = {"SALE", "RENT", "UNKNOWN"}
EVIDENCE_STATUSES = {
    "SOURCE_PAGE_CONFIRMED",
    "SOURCE_PARTIAL",
    "SEARCH_SNIPPET_ONLY",
    "CATEGORY_ONLY",
    "UNVERIFIED",
    "WEB_SEARCH_UNAVAILABLE",
}
FRESHNESS_STATUSES = {
    "NEWLY_POSTED_LAST_24H",
    "NEWLY_DISCOVERED",
    "PREVIOUSLY_SEEN",
    "UPDATED_LISTING",
    "EXPIRED",
    "UNKNOWN",
}

PILOT_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS ingestion_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    permission_status TEXT NOT NULL,
    permission_evidence TEXT NOT NULL DEFAULT '',
    permitted_scope TEXT NOT NULL DEFAULT '',
    permitted_frequency TEXT NOT NULL DEFAULT '',
    storage_permission INTEGER NOT NULL DEFAULT 0,
    attribution_requirements TEXT NOT NULL DEFAULT '',
    last_reviewed_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_targets (
    target_rank INTEGER PRIMARY KEY CHECK(target_rank BETWEEN 1 AND 50),
    original_ward TEXT NOT NULL,
    original_district TEXT NOT NULL,
    original_province TEXT NOT NULL,
    source_reference TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('FILE_IMPORT','INBOX_IMPORT','SCHEDULER_DRY_RUN')),
    status TEXT NOT NULL,
    source_file TEXT NOT NULL DEFAULT '',
    file_sha256 TEXT NOT NULL DEFAULT '',
    received INTEGER NOT NULL DEFAULT 0,
    accepted INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    newly_posted INTEGER NOT NULL DEFAULT 0,
    newly_discovered INTEGER NOT NULL DEFAULT 0,
    previously_seen INTEGER NOT NULL DEFAULT 0,
    expired INTEGER NOT NULL DEFAULT 0,
    quarantined INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(source_id) REFERENCES ingestion_sources(source_id)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_date ON ingestion_runs(run_date, started_at DESC);
CREATE TABLE IF NOT EXISTS ingestion_files (
    source_id TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    original_name TEXT NOT NULL,
    first_imported_at TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    last_run_id TEXT NOT NULL,
    PRIMARY KEY(source_id, file_sha256),
    FOREIGN KEY(source_id) REFERENCES ingestion_sources(source_id)
);
CREATE TABLE IF NOT EXISTS ingestion_listings (
    listing_uid TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    content_fingerprint TEXT NOT NULL,
    location_fingerprint TEXT NOT NULL,
    primary_source_id TEXT NOT NULL,
    source_listing_id TEXT,
    source_url TEXT NOT NULL DEFAULT '',
    source_url_type TEXT NOT NULL CHECK(source_url_type IN ('CATEGORY','DIRECT_LISTING','UNKNOWN')),
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    target_rank INTEGER NOT NULL CHECK(target_rank BETWEEN 1 AND 50),
    original_ward TEXT NOT NULL,
    original_district TEXT NOT NULL,
    original_province TEXT NOT NULL,
    property_type TEXT,
    transaction_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    price_vnd REAL,
    area_m2 REAL,
    price_per_m2 REAL,
    area_basis TEXT NOT NULL DEFAULT 'UNKNOWN',
    address TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    expires_at TEXT,
    evidence_status TEXT NOT NULL,
    validity_status TEXT NOT NULL,
    freshness_status TEXT NOT NULL,
    possible_duplicate INTEGER NOT NULL DEFAULT 0,
    stats_eligible INTEGER NOT NULL DEFAULT 0,
    review_reasons TEXT NOT NULL DEFAULT '[]',
    ingestion_run_id TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(primary_source_id) REFERENCES ingestion_sources(source_id),
    FOREIGN KEY(target_rank) REFERENCES ingestion_targets(target_rank),
    FOREIGN KEY(ingestion_run_id) REFERENCES ingestion_runs(run_id)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_listing_target ON ingestion_listings(target_rank, property_type, stats_eligible);
CREATE INDEX IF NOT EXISTS ix_ingestion_listing_source_id ON ingestion_listings(primary_source_id, source_listing_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_listing_fingerprint ON ingestion_listings(content_fingerprint);
CREATE TABLE IF NOT EXISTS ingestion_listing_sources (
    listing_uid TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_listing_id TEXT,
    source_url TEXT NOT NULL DEFAULT '',
    canonical_url TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    attribution TEXT NOT NULL DEFAULT '',
    raw_payload TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(listing_uid, source_id),
    FOREIGN KEY(listing_uid) REFERENCES ingestion_listings(listing_uid),
    FOREIGN KEY(source_id) REFERENCES ingestion_sources(source_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_source_listing_id
    ON ingestion_listing_sources(source_id, source_listing_id)
    WHERE source_listing_id IS NOT NULL AND source_listing_id<>'';
CREATE INDEX IF NOT EXISTS ix_ingestion_source_canonical_url
    ON ingestion_listing_sources(canonical_url);
CREATE TABLE IF NOT EXISTS ingestion_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_uid TEXT NOT NULL,
    source_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    observed_price_vnd REAL,
    observed_area_m2 REAL,
    price_per_m2 REAL,
    evidence_status TEXT NOT NULL,
    freshness_status TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    observation_key TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    UNIQUE(listing_uid, source_id, observation_date),
    FOREIGN KEY(listing_uid) REFERENCES ingestion_listings(listing_uid),
    FOREIGN KEY(source_id) REFERENCES ingestion_sources(source_id),
    FOREIGN KEY(source_run_id) REFERENCES ingestion_runs(run_id)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_observation_date ON ingestion_observations(observation_date, evidence_status);
CREATE TABLE IF NOT EXISTS ingestion_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_uid TEXT NOT NULL,
    change_date TEXT NOT NULL,
    old_price_vnd REAL,
    new_price_vnd REAL NOT NULL,
    source_run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(listing_uid, change_date),
    FOREIGN KEY(listing_uid) REFERENCES ingestion_listings(listing_uid),
    FOREIGN KEY(source_run_id) REFERENCES ingestion_runs(run_id)
);
CREATE TABLE IF NOT EXISTS ingestion_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    quarantined_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES ingestion_runs(run_id)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_quarantine_run ON ingestion_quarantine(run_id, row_index);
CREATE TABLE IF NOT EXISTS ingestion_daily_statistics (
    snapshot_date TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    property_type TEXT NOT NULL,
    listing_count INTEGER NOT NULL,
    mean_price_per_m2 REAL,
    median_price_per_m2 REAL,
    min_price_per_m2 REAL,
    max_price_per_m2 REAL,
    data_quality TEXT NOT NULL,
    last_updated TEXT,
    PRIMARY KEY(snapshot_date,target_rank,property_type)
);
"""

ALIASES = {
    "rank": "target_rank",
    "ward": "original_ward",
    "ward_name": "original_ward",
    "old_ward": "original_ward",
    "district": "original_district",
    "legacy_district": "original_district",
    "old_district": "original_district",
    "province": "original_province",
    "old_province": "original_province",
    "price": "price_vnd",
    "area": "area_m2",
    "url": "source_url",
    "listing_url": "source_url",
    "published_date": "published_at",
    "listed_date": "published_at",
    "transaction": "transaction_type",
    "type": "property_type",
    "source_listing_code": "source_listing_id",
}

CONTACT_KEY = re.compile(r"phone|mobile|contact|email|zalo|whatsapp|telegram|seller.?name|owner.?name", re.IGNORECASE)
EMAIL_VALUE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_VALUE = re.compile(r"(?<!\w)(?:\+?84|0)(?:[ .()-]*\d){8,10}(?!\w)")


class IngestionError(ValueError):
    """A safe, user-facing ingestion failure that excludes listing content."""


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ).replace(microsecond=0)


def _safe_pilot_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    protected = {
        (PROJECT_ROOT / "state" / name).resolve()
        for name in (
            "ward_prices.sqlite3",
            "ward_prices.demo.sqlite3",
            "ward_prices.historical_pilot.sqlite3",
            "wardprice_webpilot.sqlite3",
        )
    }
    if resolved in protected:
        raise IngestionError("Ingestion pilot must use its own isolated SQLite file.")
    if resolved.suffix.casefold() not in {".sqlite3", ".db"}:
        raise IngestionError("Pilot database path must end in .sqlite3 or .db.")
    return resolved


def connect_pilot(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = _safe_pilot_path(path)
    if readonly:
        if not path.is_file():
            raise FileNotFoundError(path)
        db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    if not readonly:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
    return db


def _load_targets(targets_db: Path) -> list[dict[str, Any]]:
    if not Path(targets_db).is_file():
        raise FileNotFoundError(f"Target database not found: {targets_db}")
    source = sqlite3.connect(f"{Path(targets_db).resolve().as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        has_priority = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='priority_targets'"
        ).fetchone()
        has_legacy = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ward_target_legacy'"
        ).fetchone()
        rows: list[dict[str, Any]] = []
        if has_priority:
            rows = [dict(row) for row in source.execute(
                """SELECT target_rank,original_ward,original_district,original_province,
                          source_reference FROM priority_targets ORDER BY target_rank"""
            )]
        if len(rows) != 50 and has_legacy:
            rows = [
                {
                    "target_rank": row["rank"],
                    "original_ward": row["old_ward"],
                    "original_district": row["old_district"],
                    "original_province": row["old_province"],
                    "source_reference": row["source_url"],
                }
                for row in source.execute("SELECT * FROM ward_target_legacy ORDER BY rank")
            ]
        ranks = {int(row["target_rank"]) for row in rows}
        if len(rows) != 50 or ranks != set(range(1, 51)):
            raise IngestionError(f"Expected 50 Top 50 targets; found {len(rows)}.")
        return rows
    finally:
        source.close()


def load_source_registry(path: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestionError("Could not read ingestion source registry.") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise IngestionError("Unsupported ingestion source registry version.")
    entries = payload.get("sources")
    if not isinstance(entries, list):
        raise IngestionError("Ingestion source registry must contain sources[].")
    sources: dict[str, dict[str, Any]] = {}
    required = (
        "source_id", "source_name", "source_type", "permission_status",
        "permission_evidence", "permitted_scope", "permitted_frequency",
        "storage_permission", "attribution_requirements", "last_reviewed_at", "enabled",
    )
    for item in entries:
        if not isinstance(item, dict) or any(key not in item for key in required):
            raise IngestionError("Each ingestion source requires complete permission metadata.")
        source_id = str(item["source_id"]).strip()
        source_type = str(item["source_type"]).strip().upper()
        permission_status = str(item["permission_status"]).strip().upper()
        if not source_id or source_id in sources:
            raise IngestionError("Source ids must be nonempty and unique.")
        if source_type not in SOURCE_TYPES or permission_status not in PERMISSION_STATUSES:
            raise IngestionError(f"Unsupported source classification for {source_id}.")
        if not isinstance(item["storage_permission"], bool) or not isinstance(item["enabled"], bool):
            raise IngestionError(f"Permission flags for {source_id} must be JSON booleans.")
        sources[source_id] = {**item, "source_id": source_id,
                              "source_type": source_type,
                              "permission_status": permission_status}
    return sources


def source_readiness(source: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if source["source_type"] in {"REVIEW_REQUIRED", "DISABLED"}:
        reasons.append(f"SOURCE_TYPE_{source['source_type']}")
    if source["permission_status"] != "AUTHORIZED":
        reasons.append("PERMISSION_NOT_AUTHORIZED")
    if not source["enabled"]:
        reasons.append("SOURCE_DISABLED")
    for field, reason in (
        ("permission_evidence", "MISSING_PERMISSION_EVIDENCE"),
        ("permitted_scope", "MISSING_PERMITTED_SCOPE"),
        ("permitted_frequency", "MISSING_PERMITTED_FREQUENCY"),
        ("attribution_requirements", "MISSING_ATTRIBUTION_REQUIREMENTS"),
    ):
        if not str(source.get(field) or "").strip():
            reasons.append(reason)
    if source["storage_permission"] is not True:
        reasons.append("STORAGE_NOT_PERMITTED")
    return not reasons, reasons


def sync_pilot_registry(db: sqlite3.Connection, *, targets_db: Path,
                        source_registry: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, int]:
    targets = _load_targets(targets_db)
    sources = load_source_registry(source_registry)
    at = now_local().isoformat()
    with db:
        db.executescript(PILOT_SCHEMA)
        for target in targets:
            db.execute(
                """INSERT INTO ingestion_targets(target_rank,original_ward,original_district,
                   original_province,source_reference,updated_at) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(target_rank) DO UPDATE SET original_ward=excluded.original_ward,
                   original_district=excluded.original_district,original_province=excluded.original_province,
                   source_reference=excluded.source_reference,updated_at=excluded.updated_at""",
                (int(target["target_rank"]), target["original_ward"], target["original_district"],
                 target["original_province"], target.get("source_reference") or "", at),
            )
        for source in sources.values():
            db.execute(
                """INSERT INTO ingestion_sources(source_id,source_name,source_type,permission_status,
                   permission_evidence,permitted_scope,permitted_frequency,storage_permission,
                   attribution_requirements,last_reviewed_at,enabled,capabilities_json,metadata_json,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET
                   source_name=excluded.source_name,source_type=excluded.source_type,
                   permission_status=excluded.permission_status,permission_evidence=excluded.permission_evidence,
                   permitted_scope=excluded.permitted_scope,permitted_frequency=excluded.permitted_frequency,
                   storage_permission=excluded.storage_permission,attribution_requirements=excluded.attribution_requirements,
                   last_reviewed_at=excluded.last_reviewed_at,enabled=excluded.enabled,
                   capabilities_json=excluded.capabilities_json,metadata_json=excluded.metadata_json,
                   updated_at=excluded.updated_at""",
                (source["source_id"], source["source_name"], source["source_type"],
                 source["permission_status"], source.get("permission_evidence") or "",
                 source.get("permitted_scope") or "", source.get("permitted_frequency") or "",
                 int(source["storage_permission"]), source.get("attribution_requirements") or "",
                 source.get("last_reviewed_at") or None, int(source["enabled"]),
                 json.dumps(source.get("capabilities") or {}, ensure_ascii=False, sort_keys=True),
                 json.dumps(source.get("metadata") or {}, ensure_ascii=False, sort_keys=True), at),
            )
    return {"targets_synced": len(targets), "sources_synced": len(sources)}


def init_pilot_db(pilot_db: Path = DEFAULT_PILOT_DB, *, targets_db: Path = DEFAULT_TARGETS_DB,
                  source_registry: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, Any]:
    path = _safe_pilot_path(pilot_db)
    db = connect_pilot(path)
    try:
        result = sync_pilot_registry(db, targets_db=targets_db, source_registry=source_registry)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError("Pilot database integrity check failed.")
    finally:
        db.close()
    return {"status": "INITIALIZED", "pilot_database": str(path), **result,
            "production_database_written": False, "network_attempted": False}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if CONTACT_KEY.search(str(key)):
                continue
            safe[str(key)] = _sanitize_value(item)
        return safe
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        value = EMAIL_VALUE.sub("[redacted email]", value)
        return PHONE_VALUE.sub("[redacted phone]", value)
    return value


def _canonical_fields(raw: dict[str, Any]) -> dict[str, Any]:
    fields = {str(key).strip(): value for key, value in raw.items()}
    lowered = {key.casefold(): value for key, value in fields.items()}
    result = {}
    for key, value in lowered.items():
        canonical = ALIASES.get(key, key)
        result[canonical] = value
    return result


def _str_value(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _positive_number(value: Any, field: str) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise TypeError(f"INVALID_{field.upper()}")
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_{field.upper()}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"INVALID_{field.upper()}")
    return number


def _parse_time(value: Any) -> datetime | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("INVALID_DATE_FIELD") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ).replace(microsecond=0)


def _normalize_transaction(value: Any) -> str:
    normalized = normalize_admin_name(_str_value(value))
    if normalized in {"sale", "sell", "ban", "ban ra", "for sale", "mua ban"}:
        return "SALE"
    if normalized in {"rent", "rental", "cho thue", "thue", "for rent"}:
        return "RENT"
    return "UNKNOWN"


def _normalize_property_type(value: Any) -> str | None:
    text = _str_value(value).upper()
    aliases = {
        "DAT O": "DAT_O", "DAT": "DAT_O", "LAND": "DAT_O", "RESIDENTIAL_LAND": "DAT_O",
        "NHA RIENG": "NHA_RIENG", "HOUSE": "NHA_RIENG", "PRIVATE_HOUSE": "NHA_RIENG",
        "CHUNG CU": "CHUNG_CU", "APARTMENT": "CHUNG_CU", "CONDO": "CHUNG_CU",
    }
    normalized = aliases.get(normalize_admin_name(text).upper(), text.replace(" ", "_"))
    return normalized if normalized in PROPERTY_TYPES else None


def _match_target(db: sqlite3.Connection, row: dict[str, Any]) -> sqlite3.Row:
    rank_value = row.get("target_rank")
    if rank_value not in (None, ""):
        try:
            rank = int(rank_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_TARGET_RANK") from exc
        target = db.execute("SELECT * FROM ingestion_targets WHERE target_rank=?", (rank,)).fetchone()
        if not target:
            raise ValueError("TARGET_NOT_IN_TOP50")
        supplied = (
            ("original_ward", target["original_ward"]),
            ("original_district", target["original_district"]),
            ("original_province", target["original_province"]),
        )
        for key, expected in supplied:
            actual = _str_value(row.get(key))
            if actual and normalize_admin_name(actual) != normalize_admin_name(expected):
                raise ValueError("WARD_WHITELIST_MISMATCH")
        return target
    names = tuple(_str_value(row.get(key)) for key in (
        "original_ward", "original_district", "original_province"
    ))
    if not all(names):
        raise ValueError("MISSING_TARGET_IDENTITY")
    matches = db.execute("SELECT * FROM ingestion_targets").fetchall()
    exact = [target for target in matches if tuple(
        normalize_admin_name(names[index]) == normalize_admin_name(target[key])
        for index, key in enumerate(("original_ward", "original_district", "original_province"))
    ) == (True, True, True)]
    if len(exact) != 1:
        raise ValueError("TARGET_NOT_IN_TOP50" if not exact else "AMBIGUOUS_TARGET")
    return exact[0]


def _url_fields(row: dict[str, Any]) -> tuple[str, str, str]:
    source_url = _str_value(row.get("source_url"))
    url_type = _str_value(row.get("source_url_type")).upper() or "UNKNOWN"
    if url_type not in URL_TYPES:
        raise ValueError("INVALID_SOURCE_URL_TYPE")
    canonical = ""
    if source_url:
        parts = urlsplit(source_url)
        if parts.scheme.casefold() != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("INVALID_SOURCE_URL")
        if url_type == "DIRECT_LISTING":
            canonical = canonicalize_source_url(source_url)
    elif url_type == "DIRECT_LISTING":
        url_type = "UNKNOWN"
    return source_url, url_type, canonical


def _source_page_proof_valid(proof: dict[str, Any] | None, row: dict[str, Any],
                             canonical_url: str) -> bool:
    if not isinstance(proof, dict):
        return False
    return bool(
        proof.get("retrieved_direct") is True
        and proof.get("detail_url") == canonical_url
        and re.fullmatch(r"[a-f0-9]{64}", str(proof.get("content_sha256", "")))
        and proof.get("visible_price_match") is True
        and proof.get("visible_area_match") is True
        and proof.get("address_verified") is True
        and all(_str_value(row.get(field)) for field in (
            "price_evidence", "area_evidence", "address_evidence"
        ))
    )


def _fingerprints(*, target_rank: int, property_type: str | None, title: str,
                  address: str, area: float | None) -> tuple[str, str]:
    normalized_address = normalize_admin_name(address)
    normalized_title = normalize_admin_name(title)
    property_value = property_type or "UNKNOWN"
    location = "|".join((str(target_rank), property_value, normalized_address, str(area or "")))
    content = f"{location}|{normalized_title}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest(), hashlib.sha256(
        location.encode("utf-8")
    ).hexdigest()


def _candidate_from_row(db: sqlite3.Connection, raw_record: Any, *, source_id: str,
                        at: datetime, operator_verified: bool, verified_by: str | None,
                        verification_reference: str | None,
                        capabilities: dict[str, Any],
                        collector_proof: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(raw_record, dict):
        raise TypeError("ROW_NOT_OBJECT")
    row = _canonical_fields(raw_record)
    target = _match_target(db, row)
    title = _str_value(row.get("title"))
    address = _str_value(row.get("address"))
    source_listing_id = _str_value(row.get("source_listing_id")) or None
    source_url, source_url_type, canonical_url = _url_fields(row)
    if not title and not source_listing_id and not canonical_url:
        raise ValueError("MISSING_LISTING_IDENTITY")
    if not address:
        raise ValueError("MISSING_ADDRESS")

    property_type = _normalize_property_type(row.get("property_type"))
    transaction_type = _normalize_transaction(row.get("transaction_type"))
    price = _positive_number(row.get("price_vnd"), "price_vnd")
    area = _positive_number(row.get("area_m2"), "area_m2")
    area_basis = _str_value(row.get("area_basis")).upper() or "UNKNOWN"
    if area_basis not in {"LAND_AREA", "FLOOR_AREA", "USABLE_AREA", "OTHER", "UNKNOWN"}:
        raise ValueError("INVALID_AREA_BASIS")
    if price is not None and area is not None:
        price_per_m2 = price / area
    else:
        price_per_m2 = None

    published_at = _parse_time(row.get("published_at"))
    expires_at = _parse_time(row.get("expires_at"))
    published_date_trusted = bool(capabilities.get("published_at_authoritative"))
    expire_date_trusted = bool(capabilities.get("expires_at_authoritative"))
    published_evidence = _str_value(row.get("published_at_evidence"))
    evidence_fields = all(_str_value(row.get(field)) for field in (
        "price_evidence", "area_evidence", "address_evidence"
    ))
    claimed_evidence = _str_value(row.get("evidence_status")).upper()
    collector_confirmed = bool(
        canonical_url and _source_page_proof_valid(collector_proof, row, canonical_url)
    )
    operator_confirmed = bool(
        operator_verified and verified_by and verification_reference and evidence_fields
        and source_url_type == "DIRECT_LISTING" and canonical_url
    )
    if source_url_type == "CATEGORY":
        evidence_status = "CATEGORY_ONLY"
    elif collector_confirmed or operator_confirmed:
        evidence_status = "SOURCE_PAGE_CONFIRMED"
    elif claimed_evidence == "SEARCH_SNIPPET_ONLY":
        evidence_status = "SEARCH_SNIPPET_ONLY"
    elif any(_str_value(row.get(field)) for field in (
        "price_evidence", "area_evidence", "address_evidence"
    )):
        evidence_status = "SOURCE_PARTIAL"
    else:
        evidence_status = "UNVERIFIED"

    reasons: list[str] = []
    if evidence_status != "SOURCE_PAGE_CONFIRMED":
        reasons.append("EVIDENCE_NOT_INDEPENDENTLY_CONFIRMED")
    if source_url_type != "DIRECT_LISTING" or not canonical_url:
        reasons.append("DIRECT_LISTING_URL_UNAVAILABLE")
    if property_type is None:
        reasons.append("PROPERTY_TYPE_UNMAPPED")
    if transaction_type == "UNKNOWN":
        reasons.append("TRANSACTION_TYPE_UNCONFIRMED")
    if price is None:
        reasons.append("PRICE_MISSING")
    if area is None:
        reasons.append("AREA_MISSING")
    if not _address_contains_target(address, target["original_ward"]):
        reasons.append("ADDRESS_WARD_NOT_CONFIRMED")
    if published_at and not (published_date_trusted and published_evidence):
        reasons.append("PUBLISHED_DATE_NOT_VERIFIED")

    content_fingerprint, location_fingerprint = _fingerprints(
        target_rank=int(target["target_rank"]), property_type=property_type,
        title=title, address=address, area=area,
    )
    if source_listing_id:
        identity_key = f"source-id:{source_id}:{source_listing_id}"
    elif canonical_url:
        identity_key = f"direct-url:{canonical_url}"
    else:
        identity_key = f"content:{content_fingerprint}"

    safe_raw = _sanitize_value(raw_record)
    # Retain the AI/source claim for audit, but do not let it establish evidence.
    if isinstance(safe_raw, dict) and claimed_evidence:
        safe_raw["claimed_evidence_status"] = claimed_evidence
    raw_payload = json.dumps(safe_raw, ensure_ascii=False, sort_keys=True, default=str)
    validity_status = "VALID" if not reasons else "NEEDS_REVIEW"
    stats_eligible = bool(
        evidence_status == "SOURCE_PAGE_CONFIRMED"
        and source_url_type == "DIRECT_LISTING"
        and property_type in PROPERTY_TYPES
        and transaction_type == "SALE"
        and price is not None
        and area is not None
        and _address_contains_target(address, target["original_ward"])
        and not (published_at and (not published_date_trusted or not published_evidence))
    )
    if expires_at and expire_date_trusted and expires_at <= at:
        freshness_status = "EXPIRED"
        validity_status = "EXPIRED"
        stats_eligible = False
        reasons.append("SOURCE_CONFIRMED_EXPIRED")
    else:
        freshness_status = "UNKNOWN"

    return {
        "source_id": source_id,
        "source_listing_id": source_listing_id,
        "source_url": source_url,
        "canonical_url": canonical_url,
        "source_url_type": source_url_type,
        "title": title,
        "description": _str_value(row.get("description")),
        "target_rank": int(target["target_rank"]),
        "original_ward": target["original_ward"],
        "original_district": target["original_district"],
        "original_province": target["original_province"],
        "property_type": property_type,
        "transaction_type": transaction_type,
        "price_vnd": price,
        "area_m2": area,
        "price_per_m2": price_per_m2,
        "area_basis": area_basis,
        "address": address,
        "published_at": published_at.isoformat() if published_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "evidence_status": evidence_status,
        "validity_status": validity_status,
        "freshness_status": freshness_status,
        "possible_duplicate": 0,
        "stats_eligible": int(stats_eligible),
        "review_reasons": reasons,
        "content_fingerprint": content_fingerprint,
        "location_fingerprint": location_fingerprint,
        "identity_key": identity_key,
        "raw_payload": raw_payload,
        "source_attribution": _str_value(row.get("attribution")),
        "published_date_trusted": published_date_trusted and bool(published_evidence),
        "collected_at": at.isoformat(),
        "record": safe_raw,
    }


def _address_contains_target(address: str, ward: str) -> bool:
    normalized_address = normalize_admin_name(address)
    normalized_ward = normalize_admin_name(ward)
    tokens = normalized_ward.split()
    if tokens and tokens[0] in {"phuong", "xa", "thi tran"}:
        tokens = tokens[1:] if tokens[0] != "thi" else tokens[2:]
    needle = " ".join(tokens)
    return bool(needle and needle in normalized_address)


def _records_and_metadata(payload: Any) -> tuple[list[Any], dict[str, Any]]:
    if isinstance(payload, list):
        return payload, {}
    if isinstance(payload, dict):
        records = payload.get("listings", payload.get("records"))
        if isinstance(records, list):
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            return records, {**metadata, **{
                key: payload[key] for key in ("source_id", "snapshot_date", "collected_at", "run_date")
                if key in payload
            }}
    raise IngestionError("Input must be a JSON array or contain listings[]/records[].")


def _file_source_id(records: list[Any], metadata: dict[str, Any], override: str | None) -> str:
    if override:
        return override.strip()
    ids = set()
    if metadata.get("source_id"):
        ids.add(str(metadata["source_id"]).strip())
    for record in records:
        if isinstance(record, dict) and record.get("source_id"):
            ids.add(str(record["source_id"]).strip())
    if len(ids) != 1:
        raise IngestionError("Provide one source_id in file metadata/rows or --source-id.")
    return next(iter(ids))


def _local_day(value: Any, fallback: date | None = None) -> str:
    parsed = _parse_time(value)
    if parsed:
        return parsed.date().isoformat()
    return (fallback or now_local().date()).isoformat()


def _current_listing(db: sqlite3.Connection, candidate: dict[str, Any]) -> sqlite3.Row | None:
    row = db.execute("SELECT * FROM ingestion_listings WHERE identity_key=?",
                     (candidate["identity_key"],)).fetchone()
    if row:
        return row
    if candidate["source_listing_id"]:
        row = db.execute(
            """SELECT l.* FROM ingestion_listing_sources s JOIN ingestion_listings l
               ON l.listing_uid=s.listing_uid WHERE s.source_id=? AND s.source_listing_id=? LIMIT 1""",
            (candidate["source_id"], candidate["source_listing_id"]),
        ).fetchone()
        if row:
            return row
    if candidate["canonical_url"]:
        row = db.execute(
            """SELECT l.* FROM ingestion_listing_sources s JOIN ingestion_listings l
               ON l.listing_uid=s.listing_uid WHERE s.canonical_url=? LIMIT 1""",
            (candidate["canonical_url"],),
        ).fetchone()
        if row:
            return row
    # Exact content match can collapse cross-source reposts; location-only matches
    # are flagged for review and never merged automatically.
    return db.execute(
        "SELECT * FROM ingestion_listings WHERE content_fingerprint=? ORDER BY first_seen_at LIMIT 1",
        (candidate["content_fingerprint"],),
    ).fetchone()


def _make_uid(identity_key: str) -> str:
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:32]


def _refresh_daily_statistics(db: sqlite3.Connection, snapshot_date: str) -> int:
    rows = db.execute(
        """SELECT target_rank,property_type,price_per_m2,MAX(last_seen_at) AS last_updated
           FROM ingestion_listings WHERE stats_eligible=1 AND validity_status='VALID'
             AND evidence_status='SOURCE_PAGE_CONFIRMED' AND transaction_type='SALE'
             AND property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU') AND price_per_m2 IS NOT NULL
           GROUP BY listing_uid ORDER BY target_rank,property_type"""
    ).fetchall()
    groups: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((int(row["target_rank"]), row["property_type"]), []).append(row)
    with db:
        db.execute("DELETE FROM ingestion_daily_statistics WHERE snapshot_date=?", (snapshot_date,))
        for (rank, property_type), values in groups.items():
            prices = [float(row["price_per_m2"]) for row in values]
            db.execute(
                """INSERT INTO ingestion_daily_statistics(snapshot_date,target_rank,property_type,
                   listing_count,mean_price_per_m2,median_price_per_m2,min_price_per_m2,
                   max_price_per_m2,data_quality,last_updated) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_date, rank, property_type, len(prices), mean(prices), median(prices),
                 min(prices), max(prices), "SOURCE_VERIFIED", max(row["last_updated"] for row in values)),
            )
    return len(groups)


def _preview_rows(db: sqlite3.Connection, records: list[Any], *, source: dict[str, Any],
                  source_id: str, at: datetime, operator_verified: bool,
                  verified_by: str | None, verification_reference: str | None,
                  file_hash: str,
                  trusted_collector_proofs: list[dict[str, Any] | None] | None = None
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    capabilities = source.get("capabilities") or {}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    counts = {key: 0 for key in (
        "received", "accepted", "inserted", "updated", "duplicates", "verified",
        "newly_posted", "newly_discovered", "previously_seen", "expired", "quarantined", "rejected",
        "category_urls", "direct_listing_urls", "newly_discovered_urls",
    )}
    counts["received"] = len(records)
    for index, raw in enumerate(records, start=1):
        try:
            if isinstance(raw, dict) and (
                str(raw.get("source_website", "")).upper() == "DEMO_SYNTHETIC"
                or bool(raw.get("synthetic"))
            ):
                raise ValueError("SYNTHETIC_DATA_BLOCKED")
            candidate = _candidate_from_row(
                db, raw, source_id=source_id, at=at,
                operator_verified=operator_verified, verified_by=verified_by,
                verification_reference=verification_reference, capabilities=capabilities,
                collector_proof=(trusted_collector_proofs[index - 1]
                                  if trusted_collector_proofs and index <= len(trusted_collector_proofs)
                                  else None),
            )
            aliases = {candidate["identity_key"], "fp:" + candidate["content_fingerprint"]}
            if candidate["canonical_url"]:
                aliases.add("url:" + candidate["canonical_url"])
            if candidate["source_listing_id"]:
                aliases.add("sid:" + source_id + ":" + candidate["source_listing_id"])
            if aliases & seen_keys:
                counts["duplicates"] += 1
                rejected.append({"row_index": index, "reason": "DUPLICATE_IN_BATCH", "raw": candidate["raw_payload"]})
                continue
            seen_keys.update(aliases)
            existing = _current_listing(db, candidate)
            if existing:
                candidate["existing"] = dict(existing)
                candidate["listing_uid"] = existing["listing_uid"]
                if existing["primary_source_id"] != source_id:
                    candidate["possible_duplicate"] = 1
                    candidate["stats_eligible"] = 0
                    candidate["validity_status"] = "NEEDS_REVIEW"
                    candidate["freshness_status"] = "PREVIOUSLY_SEEN"
                    candidate["review_reasons"].append("CROSS_SOURCE_DUPLICATE_REVIEW")
                    counts["previously_seen"] += 1
                elif candidate["freshness_status"] == "EXPIRED":
                    candidate["validity_status"] = "EXPIRED"
                    candidate["stats_eligible"] = 0
                    counts["expired"] += 1
                else:
                    changed = any(
                        existing[field] != candidate.get(field)
                        for field in (
                            "price_vnd", "area_m2", "address", "title", "property_type",
                            "transaction_type", "source_url", "evidence_status", "validity_status",
                            "expires_at",
                        )
                        if candidate.get(field) not in (None, "")
                    )
                    candidate["freshness_status"] = "UPDATED_LISTING" if changed else "PREVIOUSLY_SEEN"
                    if changed:
                        counts["updated"] += 1
                        if candidate.get("price_vnd") is not None and candidate.get("price_vnd") != existing["price_vnd"]:
                            candidate["previous_price_vnd"] = existing["price_vnd"]
                    else:
                        counts["previously_seen"] += 1
            elif candidate["freshness_status"] == "EXPIRED":
                counts["expired"] += 1
            else:
                published = _parse_time(candidate.get("published_at"))
                pub_trusted = bool(candidate.get("published_date_trusted"))
                if published and pub_trusted:
                    age = at - published
                    candidate["freshness_status"] = (
                        "NEWLY_POSTED_LAST_24H" if timedelta(0) <= age <= timedelta(hours=24)
                        else "NEWLY_DISCOVERED" if age > timedelta(hours=24)
                        else "UNKNOWN"
                    )
                else:
                    candidate["freshness_status"] = "NEWLY_DISCOVERED"
                if candidate["freshness_status"] == "NEWLY_POSTED_LAST_24H":
                    counts["newly_posted"] += 1
                elif candidate["freshness_status"] == "NEWLY_DISCOVERED":
                    counts["newly_discovered"] += 1
            if candidate["source_url_type"] == "CATEGORY":
                counts["category_urls"] += 1
            elif candidate["source_url_type"] == "DIRECT_LISTING":
                counts["direct_listing_urls"] += 1
            if candidate["evidence_status"] == "SOURCE_PAGE_CONFIRMED":
                counts["verified"] += 1
            if candidate.get("listing_uid"):
                pass
            else:
                candidate["listing_uid"] = _make_uid(candidate["identity_key"])
            accepted.append(candidate)
        except (TypeError, ValueError, OverflowError) as exc:
            reason = str(exc) if str(exc).isupper() and re.fullmatch(r"[A-Z0-9_]+", str(exc)) else "INVALID_RECORD"
            raw_safe = json.dumps(_sanitize_value(raw), ensure_ascii=False, sort_keys=True, default=str)
            rejected.append({"row_index": index, "reason": reason, "raw": raw_safe})
    counts["accepted"] = len(accepted)
    counts["rejected"] = len(rejected)
    counts["quarantined"] = len(rejected)
    counts["inserted"] = sum(1 for item in accepted if not item.get("existing"))
    return accepted, rejected, counts


def _upsert_candidate(db: sqlite3.Connection, candidate: dict[str, Any], *, run_id: str,
                      observation_date: str, at: datetime, source: dict[str, Any],
                      file_hash: str) -> tuple[str, bool]:
    existing = candidate.get("existing")
    listing_uid = candidate["listing_uid"]
    previous_price = existing["price_vnd"] if existing else None
    source_id = candidate["source_id"]
    reasons = list(candidate["review_reasons"])
    possible_duplicate = int(candidate.get("possible_duplicate", 0))
    if possible_duplicate:
        reasons.append("CROSS_SOURCE_DUPLICATE_REVIEW")
    stats_eligible = int(candidate["stats_eligible"] and not possible_duplicate)
    if existing:
        db.execute(
            """UPDATE ingestion_listings SET source_url=CASE WHEN ?<>'' THEN ? ELSE source_url END,
               source_url_type=?,title=CASE WHEN ?<>'' THEN ? ELSE title END,
               description=CASE WHEN ?<>'' THEN ? ELSE description END,
               property_type=COALESCE(?,property_type),transaction_type=?,
               price_vnd=COALESCE(?,price_vnd),area_m2=COALESCE(?,area_m2),
               price_per_m2=COALESCE(?,price_per_m2),area_basis=?,address=CASE WHEN ?<>'' THEN ? ELSE address END,
               published_at=COALESCE(?,published_at),last_seen_at=?,collected_at=?,expires_at=COALESCE(?,expires_at),
               evidence_status=?,validity_status=?,freshness_status=?,possible_duplicate=MAX(possible_duplicate,?),
               stats_eligible=?,review_reasons=?,ingestion_run_id=?,raw_payload=?
               WHERE listing_uid=?""",
            (candidate["source_url"], candidate["source_url"], candidate["source_url_type"],
             candidate["title"], candidate["title"], candidate["description"], candidate["description"],
             candidate["property_type"], candidate["transaction_type"], candidate["price_vnd"],
             candidate["area_m2"], candidate["price_per_m2"], candidate["area_basis"],
             candidate["address"], candidate["address"], candidate["published_at"], at.isoformat(),
             at.isoformat(), candidate["expires_at"], candidate["evidence_status"],
             candidate["validity_status"], candidate["freshness_status"], possible_duplicate,
             stats_eligible, json.dumps(sorted(set(reasons)), ensure_ascii=False), run_id,
             candidate["raw_payload"], listing_uid),
        )
        outcome = "UPDATED"
    else:
        db.execute(
            """INSERT INTO ingestion_listings(listing_uid,identity_key,content_fingerprint,
               location_fingerprint,primary_source_id,source_listing_id,source_url,source_url_type,
               title,description,target_rank,original_ward,original_district,original_province,
               property_type,transaction_type,price_vnd,area_m2,price_per_m2,area_basis,address,
               published_at,first_seen_at,last_seen_at,collected_at,expires_at,evidence_status,
               validity_status,freshness_status,possible_duplicate,stats_eligible,review_reasons,
               ingestion_run_id,raw_payload)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (listing_uid, candidate["identity_key"], candidate["content_fingerprint"],
             candidate["location_fingerprint"], source_id, candidate["source_listing_id"],
             candidate["source_url"], candidate["source_url_type"], candidate["title"],
             candidate["description"], candidate["target_rank"], candidate["original_ward"],
             candidate["original_district"], candidate["original_province"], candidate["property_type"],
             candidate["transaction_type"], candidate["price_vnd"], candidate["area_m2"],
             candidate["price_per_m2"], candidate["area_basis"], candidate["address"],
             candidate["published_at"], at.isoformat(), at.isoformat(), at.isoformat(),
             candidate["expires_at"], candidate["evidence_status"], candidate["validity_status"],
             candidate["freshness_status"], possible_duplicate, stats_eligible,
             json.dumps(sorted(set(reasons)), ensure_ascii=False), run_id, candidate["raw_payload"]),
        )
        outcome = "INSERTED"

    canonical = candidate["canonical_url"]
    attribution = candidate.get("source_attribution") or source["attribution_requirements"]
    db.execute(
        """INSERT INTO ingestion_listing_sources(listing_uid,source_id,source_listing_id,source_url,
           canonical_url,first_seen_at,last_seen_at,evidence_status,attribution,raw_payload)
           VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(listing_uid,source_id) DO UPDATE SET
           source_listing_id=COALESCE(excluded.source_listing_id,source_listing_id),
           source_url=CASE WHEN excluded.source_url<>'' THEN excluded.source_url ELSE source_url END,
           canonical_url=CASE WHEN excluded.canonical_url<>'' THEN excluded.canonical_url ELSE canonical_url END,
           last_seen_at=excluded.last_seen_at,evidence_status=excluded.evidence_status,
           attribution=excluded.attribution,raw_payload=excluded.raw_payload""",
        (listing_uid, source_id, candidate["source_listing_id"], candidate["source_url"], canonical,
         at.isoformat(), at.isoformat(), candidate["evidence_status"], attribution,
         candidate["raw_payload"]),
    )

    observation = db.execute(
        """SELECT id FROM ingestion_observations WHERE listing_uid=? AND source_id=? AND observation_date=?""",
        (listing_uid, source_id, observation_date),
    ).fetchone()
    observation_key = f"{source_id}:{file_hash}:{candidate['identity_key']}"
    if observation:
        db.execute(
            """UPDATE ingestion_observations SET observed_at=?,observed_price_vnd=?,observed_area_m2=?,
               price_per_m2=?,evidence_status=?,freshness_status=?,source_run_id=?,source_url=?,
               observation_key=?,raw_payload=? WHERE id=?""",
            (at.isoformat(), candidate["price_vnd"], candidate["area_m2"], candidate["price_per_m2"],
             candidate["evidence_status"], candidate["freshness_status"], run_id,
             candidate["source_url"], observation_key, candidate["raw_payload"], observation["id"]),
        )
    else:
        db.execute(
            """INSERT INTO ingestion_observations(listing_uid,source_id,observation_date,observed_at,
               observed_price_vnd,observed_area_m2,price_per_m2,evidence_status,freshness_status,
               source_run_id,source_url,observation_key,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (listing_uid, source_id, observation_date, at.isoformat(), candidate["price_vnd"],
             candidate["area_m2"], candidate["price_per_m2"], candidate["evidence_status"],
             candidate["freshness_status"], run_id, candidate["source_url"], observation_key,
             candidate["raw_payload"]),
        )

    current_price = candidate["price_vnd"]
    price_changed = previous_price is not None and current_price is not None and float(previous_price) != float(current_price)
    if price_changed:
        db.execute(
            """INSERT INTO ingestion_price_history(listing_uid,change_date,old_price_vnd,
               new_price_vnd,source_run_id,observed_at) VALUES(?,?,?,?,?,?)
               ON CONFLICT(listing_uid,change_date) DO UPDATE SET new_price_vnd=excluded.new_price_vnd,
               source_run_id=excluded.source_run_id,observed_at=excluded.observed_at""",
            (listing_uid, observation_date, previous_price, current_price, run_id, at.isoformat()),
        )
    return outcome, price_changed


def _insert_run(db: sqlite3.Connection, *, run_id: str, source_id: str, at: datetime,
                mode: str, status: str, file_path: str, file_hash: str,
                counts: dict[str, int], summary: dict[str, Any]) -> None:
    db.execute(
        """INSERT INTO ingestion_runs(run_id,source_id,started_at,finished_at,run_date,mode,status,
           source_file,file_sha256,received,accepted,inserted,updated,duplicates,verified,newly_posted,
           newly_discovered,previously_seen,expired,quarantined,rejected,summary_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, source_id, at.isoformat(), at.isoformat(), at.date().isoformat(), mode, status,
         file_path, file_hash, counts.get("received", 0), counts.get("accepted", 0),
         counts.get("inserted", 0), counts.get("updated", 0), counts.get("duplicates", 0),
         counts.get("verified", 0), counts.get("newly_posted", 0),
         counts.get("newly_discovered", 0), counts.get("previously_seen", 0),
         counts.get("expired", 0), counts.get("quarantined", 0), counts.get("rejected", 0),
         json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)),
    )


def _ingest_payload(payload: Any, *, pilot_db: Path = DEFAULT_PILOT_DB,
                    targets_db: Path = DEFAULT_TARGETS_DB,
                    source_registry: Path = DEFAULT_SOURCE_REGISTRY,
                    source_id: str | None = None, file_path: Path | str = "",
                    file_hash: str | None = None, apply: bool = False,
                    operator_verified: bool = False, verified_by: str | None = None,
                    verification_reference: str | None = None,
                    mode: str = "FILE_IMPORT", at: datetime | None = None,
                    _allow_synthetic_test_data: bool = False,
                    trusted_collector_proofs: list[dict[str, Any] | None] | None = None
                    ) -> dict[str, Any]:
    """Preview or transactionally import one JSON/CSV-compatible listing batch."""
    if mode not in {"FILE_IMPORT", "INBOX_IMPORT", "SCHEDULER_DRY_RUN"}:
        raise ValueError("unsupported ingestion run mode")
    if operator_verified and not (verified_by and verification_reference):
        raise IngestionError("Operator verification requires verified_by and a reference.")
    if operator_verified and not apply:
        # Preview describes what explicit operator verification would change but stores nothing.
        pass
    records, metadata = _records_and_metadata(payload)
    if len(records) > MAX_INPUT_ROWS:
        raise IngestionError(f"Input exceeds the {MAX_INPUT_ROWS}-row processing safety limit.")
    actual_source_id = _file_source_id(records, metadata, source_id)
    registry = load_source_registry(source_registry)
    source = registry.get(actual_source_id)
    if source is None:
        source = {
            "source_id": actual_source_id, "source_name": actual_source_id,
            "source_type": "REVIEW_REQUIRED", "permission_status": "REVIEW_REQUIRED",
            "permission_evidence": "", "permitted_scope": "", "permitted_frequency": "",
            "storage_permission": False, "attribution_requirements": "", "last_reviewed_at": None,
            "enabled": False, "capabilities": {}, "metadata": {},
        }
    ready, reasons = source_readiness(source)
    at = at or now_local()
    file_path_text = str(file_path)
    file_hash = file_hash or hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if _allow_synthetic_test_data is False and (
        actual_source_id.casefold().startswith(("synthetic", "benchmark"))
        or any(isinstance(row, dict) and (
            row.get("source_website") == "DEMO_SYNTHETIC" or row.get("synthetic") is True
        ) for row in records)
    ):
        raise IngestionError("Synthetic fixtures are blocked from the ingestion pilot.")

    pilot_path = _safe_pilot_path(pilot_db)
    exists = pilot_path.is_file()
    db = connect_pilot(pilot_path, readonly=exists and not apply)
    close_db = True
    try:
        schema_ready = bool(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingestion_targets'"
        ).fetchone()) if exists else False
        if apply and (not exists or not schema_ready):
            db.close()
            init_pilot_db(pilot_path, targets_db=targets_db, source_registry=source_registry)
            db = connect_pilot(pilot_path)
        elif not apply and (not exists or not schema_ready):
            # Dry-run may validate a new batch without creating the pilot database.
            db.close()
            db = sqlite3.connect(":memory:")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(PILOT_SCHEMA)
            for target in _load_targets(targets_db):
                db.execute(
                    "INSERT INTO ingestion_targets VALUES(?,?,?,?,?,?)",
                    (target["target_rank"], target["original_ward"], target["original_district"],
                     target["original_province"], target.get("source_reference") or "", at.isoformat()),
                )
            for source_entry in registry.values():
                db.execute(
                    """INSERT INTO ingestion_sources(source_id,source_name,source_type,permission_status,
                       permission_evidence,permitted_scope,permitted_frequency,storage_permission,
                       attribution_requirements,last_reviewed_at,enabled,capabilities_json,metadata_json,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (source_entry["source_id"], source_entry["source_name"], source_entry["source_type"],
                     source_entry["permission_status"], source_entry["permission_evidence"],
                     source_entry["permitted_scope"], source_entry["permitted_frequency"],
                     int(source_entry["storage_permission"]), source_entry["attribution_requirements"],
                     source_entry["last_reviewed_at"], int(source_entry["enabled"]),
                     json.dumps(source_entry.get("capabilities") or {}),
                     json.dumps(source_entry.get("metadata") or {}), at.isoformat()),
                )
        elif apply:
            sync_pilot_registry(db, targets_db=targets_db, source_registry=source_registry)
        if not ready:
            counts = {"received": len(records), "accepted": 0, "inserted": 0, "updated": 0,
                      "duplicates": 0, "verified": 0, "newly_posted": 0,
                      "newly_discovered": 0, "previously_seen": 0, "expired": 0,
                      "quarantined": 0, "rejected": 0}
            report = {
                "status": "BLOCKED_SOURCE", "run_id": None, "source_id": actual_source_id,
                "source_permission_status": source["permission_status"],
                "source_ready": False, "source_block_reasons": reasons,
                **counts, "rejected_reasons": {}, "network_attempted": False,
                "production_database_written": False,
            }
            if apply:
                # Keep an auditable blocked attempt without treating an unknown source as approved.
                db.execute(
                    """INSERT OR IGNORE INTO ingestion_sources(source_id,source_name,source_type,
                       permission_status,updated_at) VALUES(?,?,?,?,?)""",
                    (actual_source_id, source["source_name"], source["source_type"],
                     source["permission_status"], at.isoformat()),
                )
                run_id = uuid.uuid4().hex
                with db:
                    _insert_run(db, run_id=run_id, source_id=actual_source_id, at=at, mode=mode,
                                status="BLOCKED_SOURCE", file_path=file_path_text,
                                file_hash=file_hash, counts=counts,
                                summary={"source_block_reasons": reasons})
                report["run_id"] = run_id
            return report

        accepted, rejected, counts = _preview_rows(
            db, records, source=source, source_id=actual_source_id, at=at,
            operator_verified=operator_verified, verified_by=verified_by,
            verification_reference=verification_reference, file_hash=file_hash,
            trusted_collector_proofs=trusted_collector_proofs,
        )
        counts["duplicates"] += sum(
            1 for row in rejected if row["reason"] == "DUPLICATE_IN_BATCH"
        )
        observation_date = _local_day(
            metadata.get("snapshot_date") or metadata.get("collected_at") or metadata.get("run_date"),
            at.date(),
        )
        if apply:
            run_id = uuid.uuid4().hex
            _insert_run(
                db, run_id=run_id, source_id=actual_source_id, at=at, mode=mode,
                status="IN_PROGRESS", file_path=file_path_text, file_hash=file_hash,
                counts=counts,
                summary={"observation_date": observation_date,
                         "source_type": source["source_type"],
                         "permission_status": source["permission_status"],
                         "direct_listing_urls": counts.get("direct_listing_urls", 0),
                         "category_urls": counts.get("category_urls", 0)},
            )
            for candidate in accepted:
                existing = candidate.get("existing")
                if existing and candidate["freshness_status"] in {"PREVIOUSLY_SEEN", "UPDATED_LISTING"}:
                    if candidate["freshness_status"] == "UPDATED_LISTING":
                        counts["updated"] += 0  # preview already counted this update
                    else:
                        counts["previously_seen"] += 0
                outcome, _price_changed = _upsert_candidate(
                    db, candidate, run_id=run_id, observation_date=observation_date,
                    at=at, source=source, file_hash=file_hash,
                )
                if outcome == "UPDATED":
                    counts["updated"] = max(counts["updated"], 0)
                else:
                    counts["inserted"] += 0  # already represented by preview counts
            for rejected_row in rejected:
                db.execute(
                    """INSERT INTO ingestion_quarantine(run_id,source_id,row_index,quarantined_at,
                       reason,raw_payload) VALUES(?,?,?,?,?,?)""",
                    (run_id, actual_source_id, rejected_row["row_index"], at.isoformat(),
                     rejected_row["reason"], rejected_row["raw"]),
                )
            db.execute(
                """UPDATE ingestion_runs SET finished_at=?,status=?,accepted=?,inserted=?,updated=?,
                   duplicates=?,verified=?,newly_posted=?,newly_discovered=?,previously_seen=?,
                   expired=?,quarantined=?,rejected=?,summary_json=? WHERE run_id=?""",
                (at.isoformat(), "SUCCEEDED" if not rejected else "SUCCEEDED_WITH_QUARANTINE",
                 counts.get("accepted", 0), counts.get("inserted", 0), counts.get("updated", 0),
                 counts.get("duplicates", 0), counts.get("verified", 0),
                 counts.get("newly_posted", 0), counts.get("newly_discovered", 0),
                 counts.get("previously_seen", 0), counts.get("expired", 0),
                 counts.get("quarantined", 0), counts.get("rejected", 0),
                 json.dumps({"observation_date": observation_date,
                             "source_type": source["source_type"],
                             "permission_status": source["permission_status"],
                             "direct_listing_urls": counts.get("direct_listing_urls", 0),
                             "category_urls": counts.get("category_urls", 0)},
                            ensure_ascii=False, sort_keys=True), run_id),
            )
            db.execute(
                """INSERT INTO ingestion_files(source_id,file_sha256,original_name,first_imported_at,
                   observation_date,last_run_id) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,file_sha256)
                   DO UPDATE SET observation_date=excluded.observation_date,last_run_id=excluded.last_run_id""",
                (actual_source_id, file_hash, Path(file_path_text).name if file_path_text else "payload",
                 at.isoformat(), observation_date, run_id),
            )
            stats_groups = _refresh_daily_statistics(db, observation_date)
            db.commit()
            report = {
                "status": "APPLIED" if not rejected else "APPLIED_WITH_QUARANTINE",
                "run_id": run_id, "source_id": actual_source_id,
                "source_permission_status": source["permission_status"], "source_ready": True,
                **counts,
                "rejected_reasons": _reason_counts(rejected),
                "observations": len(accepted), "price_history_changes": int(db.execute(
                    "SELECT COUNT(*) FROM ingestion_price_history WHERE source_run_id=?", (run_id,)
                ).fetchone()[0]),
                "statistics_groups_refreshed": stats_groups,
                "observation_date": observation_date, "network_attempted": False,
                "production_database_written": False,
            }
        else:
            report = {
                "status": "PREVIEW_ONLY", "run_id": None, "source_id": actual_source_id,
                "source_permission_status": source["permission_status"], "source_ready": True,
                **counts, "rejected_reasons": _reason_counts(rejected),
                "observation_date_preview": observation_date,
                "network_attempted": False, "pilot_database_written": False,
                "production_database_written": False,
            }
        return report
    finally:
        if close_db:
            db.close()


def ingest_payload(payload: Any, *, pilot_db: Path = DEFAULT_PILOT_DB,
                   targets_db: Path = DEFAULT_TARGETS_DB,
                   source_registry: Path = DEFAULT_SOURCE_REGISTRY,
                   source_id: str | None = None, file_path: Path | str = "",
                   file_hash: str | None = None, apply: bool = False,
                   operator_verified: bool = False, verified_by: str | None = None,
                   verification_reference: str | None = None,
                   mode: str = "FILE_IMPORT", at: datetime | None = None) -> dict[str, Any]:
    """Ingest a user/API payload without trusting source-page proof embedded in it."""
    return _ingest_payload(
        payload, pilot_db=pilot_db, targets_db=targets_db, source_registry=source_registry,
        source_id=source_id, file_path=file_path, file_hash=file_hash, apply=apply,
        operator_verified=operator_verified, verified_by=verified_by,
        verification_reference=verification_reference, mode=mode, at=at,
    )


def _reason_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rejected:
        counts[row["reason"]] = counts.get(row["reason"], 0) + 1
    return counts


def ingest_file(file_path: Path, **kwargs: Any) -> dict[str, Any]:
    path = Path(file_path)
    if path.suffix.casefold() not in {".json", ".csv", ".xlsx"}:
        raise IngestionError("Input must be .json, .csv, or .xlsx.")
    payload = load_listing_payload(path)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return ingest_payload(payload, file_path=path, file_hash=file_hash, **kwargs)


def _collector_result_parts(result: Any, *, source_id: str
                            ) -> tuple[dict[str, Any], list[dict[str, Any] | None]]:
    """Build the common payload plus out-of-band proof from a collector result."""
    candidates = getattr(result, "listing_candidates", None)
    target_rank = getattr(result, "target_rank", None)
    collected_at = getattr(result, "collected_at", None)
    if isinstance(result, dict):
        candidates = result.get("listing_candidates", candidates)
        target_rank = result.get("target_rank", target_rank)
        collected_at = result.get("collected_at", collected_at)
    if not isinstance(candidates, list):
        raise IngestionError("Collector result must contain listing_candidates[].")
    output = []
    trusted_proofs: list[dict[str, Any] | None] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw = candidate.get("raw_payload") or {}
        if not isinstance(raw, dict):
            raw = {}
        evidence = candidate.get("evidence") or {}
        if not isinstance(evidence, dict):
            evidence = {}
        price_evidence = evidence.get("price") or {}
        area_evidence = evidence.get("area_m2") or {}
        detail_url = candidate.get("canonical_url") or candidate.get("source_url") or ""
        trusted_proofs.append({
            "retrieved_direct": bool(raw.get("retrieved_at")) and bool(detail_url),
            "detail_url": canonicalize_source_url(detail_url) if detail_url else "",
            "content_sha256": raw.get("content_sha256") or evidence.get("content_sha256") or "",
            "visible_price_match": bool(raw.get("visible_price_match")),
            "visible_area_match": bool(raw.get("visible_area_match")),
            "address_verified": bool(
                raw.get("address_visible") and raw.get("target_terms_present")
                and evidence.get("target_match")
            ),
        })
        row = {
            "source_id": source_id,
            "source_listing_id": candidate.get("source_listing_id"),
            "source_url": candidate.get("source_url") or detail_url,
            "source_url_type": candidate.get("source_url_type") or "DIRECT_LISTING",
            "title": candidate.get("title"),
            "address": candidate.get("address"),
            "target_rank": candidate.get("target_rank") or target_rank,
            "original_ward": candidate.get("original_ward"),
            "original_district": candidate.get("original_district"),
            "original_province": candidate.get("original_province"),
            "property_type": candidate.get("property_type"),
            # The HTML collector does not prove transaction type; leave it unknown.
            "transaction_type": candidate.get("transaction_type"),
            "price_vnd": candidate.get("price_vnd"),
            "area_m2": candidate.get("area_m2"),
            "area_basis": candidate.get("area_basis") or "UNKNOWN",
            "address_evidence": evidence.get("address") if evidence.get("target_match") else "",
            "price_evidence": str(price_evidence.get("visible")) if price_evidence.get("visible") is not None else "",
            "area_evidence": str(area_evidence.get("visible")) if area_evidence.get("visible") is not None else "",
            "evidence_status": candidate.get("evidence_status") or "UNVERIFIED",
            "published_at": candidate.get("listed_date"),
            "expires_at": candidate.get("expires_at"),
            "collected_at": candidate.get("collected_at") or collected_at,
            "raw_collector_evidence": raw,
        }
        output.append(row)
    payload = {
        "source_id": source_id,
        "collected_at": collected_at,
        "listings": output,
        "metadata": {"adapter": "wardprice.collectors", "network_called_by_adapter": False},
    }
    return payload, trusted_proofs


def collector_result_to_payload(result: Any, *, source_id: str) -> dict[str, Any]:
    """Adapt collector output for review; embedded fields alone cannot verify it."""
    payload, _trusted_proofs = _collector_result_parts(result, source_id=source_id)
    return payload


def ingest_collector_result(result: Any, *, source_id: str,
                            pilot_db: Path = DEFAULT_PILOT_DB,
                            targets_db: Path = DEFAULT_TARGETS_DB,
                            source_registry: Path = DEFAULT_SOURCE_REGISTRY,
                            file_path: Path | str = "", apply: bool = False,
                            operator_verified: bool = False,
                            verified_by: str | None = None,
                            verification_reference: str | None = None,
                            mode: str = "FILE_IMPORT",
                            at: datetime | None = None) -> dict[str, Any]:
    """Ingest the existing collector's local result without performing a fetch."""
    payload, trusted_proofs = _collector_result_parts(result, source_id=source_id)
    file_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return _ingest_payload(
        payload, pilot_db=pilot_db, targets_db=targets_db, source_registry=source_registry,
        source_id=source_id, file_path=file_path, file_hash=file_hash, apply=apply,
        operator_verified=operator_verified, verified_by=verified_by,
        verification_reference=verification_reference, mode=mode, at=at,
        trusted_collector_proofs=trusted_proofs,
    )


def list_sources(source_registry: Path = DEFAULT_SOURCE_REGISTRY) -> dict[str, Any]:
    sources = load_source_registry(source_registry)
    records = []
    for source in sources.values():
        ready, reasons = source_readiness(source)
        records.append({
            "source_id": source["source_id"], "source_name": source["source_name"],
            "source_type": source["source_type"], "permission_status": source["permission_status"],
            "enabled": source["enabled"], "source_ready": ready,
            "storage_permission": source["storage_permission"],
            "last_reviewed_at": source.get("last_reviewed_at"),
            "block_reasons": reasons,
        })
    return {"source_count": len(records), "sources": records,
            "network_attempted": False, "database_written": False}


def monitoring_summary(pilot_db: Path = DEFAULT_PILOT_DB, *, run_date: str | None = None) -> dict[str, Any]:
    if not Path(pilot_db).is_file():
        return {
            "status": "NOT_INITIALIZED", "daily_goal": DAILY_LISTING_GOAL,
            "pilot_database": str(pilot_db), "target_count": 0, "covered_targets": 0,
            "candidate_count": 0, "verified_count": 0, "stats_eligible_count": 0,
            "direct_url_ratio": 0.0, "network_attempted": False,
            "scheduler_status": "NOT_ACTIVATED", "target_coverage": [],
        }
    day = run_date or now_local().date().isoformat()
    db = connect_pilot(Path(pilot_db), readonly=True)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingestion_runs'").fetchone():
            return {"status": "NOT_INITIALIZED", "daily_goal": DAILY_LISTING_GOAL,
                    "pilot_database": str(pilot_db), "target_count": 0, "covered_targets": 0,
                    "candidate_count": 0, "verified_count": 0, "stats_eligible_count": 0,
                    "direct_url_ratio": 0.0, "network_attempted": False,
                    "scheduler_status": "NOT_ACTIVATED", "target_coverage": []}
        totals = {key: 0 for key in (
            "requests_made", "discovered_urls", "candidates_extracted", "inserted",
            "verified", "newly_posted", "newly_discovered", "previously_seen",
            "updated", "expired", "quarantined", "rejected", "duplicates",
        )}
        runs = [dict(row) for row in db.execute(
            """SELECT run_id,source_id,started_at,finished_at,run_date,mode,status,source_file,
                      received,accepted,inserted,updated,duplicates,verified,newly_posted,
                      newly_discovered,previously_seen,expired,quarantined,rejected,summary_json
               FROM ingestion_runs WHERE run_date=? ORDER BY started_at DESC""", (day,)
        )]
        for run in runs:
            for key in ("inserted", "updated", "duplicates", "verified", "newly_posted",
                        "newly_discovered", "previously_seen", "expired", "quarantined", "rejected"):
                totals[key] += int(run.get(key) or 0)
            try:
                summary = json.loads(run.get("summary_json") or "{}")
            except json.JSONDecodeError:
                summary = {}
            totals["discovered_urls"] += int(summary.get("direct_listing_urls", 0)) + int(summary.get("category_urls", 0))
            totals["candidates_extracted"] += int(run.get("accepted") or 0)
        candidate_count = int(db.execute("SELECT COUNT(*) FROM ingestion_listings").fetchone()[0])
        verified_count = int(db.execute(
            "SELECT COUNT(*) FROM ingestion_listings WHERE evidence_status='SOURCE_PAGE_CONFIRMED'"
        ).fetchone()[0])
        stats_count = int(db.execute(
            "SELECT COUNT(*) FROM ingestion_listings WHERE stats_eligible=1 AND validity_status='VALID'"
        ).fetchone()[0])
        target_count = int(db.execute("SELECT COUNT(*) FROM ingestion_targets").fetchone()[0])
        covered = int(db.execute(
            "SELECT COUNT(DISTINCT target_rank) FROM ingestion_listings WHERE stats_eligible=1 AND validity_status='VALID'"
        ).fetchone()[0])
        candidate_coverage = {
            int(row["target_rank"]): (int(row["candidate_count"]), int(row["verified_count"]))
            for row in db.execute(
                """SELECT target_rank,COUNT(*) AS candidate_count,
                          SUM(CASE WHEN stats_eligible=1 AND validity_status='VALID' THEN 1 ELSE 0 END) AS verified_count
                   FROM ingestion_listings GROUP BY target_rank"""
            )
        }
        daily_posted = {
            int(row["target_rank"]): int(row["listing_count"])
            for row in db.execute(
                """SELECT l.target_rank,COUNT(DISTINCT o.listing_uid) AS listing_count
                   FROM ingestion_observations o JOIN ingestion_listings l USING(listing_uid)
                   WHERE o.observation_date=? AND o.freshness_status='NEWLY_POSTED_LAST_24H'
                   GROUP BY l.target_rank""", (day,)
            )
        }
        target_coverage = []
        for target in db.execute(
            "SELECT target_rank,original_ward,original_province FROM ingestion_targets ORDER BY target_rank"
        ):
            rank = int(target["target_rank"])
            candidates, verified = candidate_coverage.get(rank, (0, 0))
            new_today = daily_posted.get(rank, 0)
            target_coverage.append({
                "target_rank": rank, "ward": target["original_ward"],
                "province": target["original_province"], "candidate_count": candidates,
                "verified_count": verified, "newly_posted_today": new_today,
                "daily_goal": TARGET_DAILY_LISTING_GOAL,
                "goal_remaining": max(0, TARGET_DAILY_LISTING_GOAL - new_today),
                "goal_met": new_today >= TARGET_DAILY_LISTING_GOAL,
            })
        direct_count = int(db.execute(
            "SELECT COUNT(*) FROM ingestion_listings WHERE source_url_type='DIRECT_LISTING' AND source_url<>''"
        ).fetchone()[0])
        url_ratio = direct_count / candidate_count if candidate_count else 0.0
        sources = []
        for row in db.execute("SELECT * FROM ingestion_sources ORDER BY source_id"):
            source = dict(row)
            permission_reasons = []
            if source["permission_status"] != "AUTHORIZED":
                permission_reasons.append("PERMISSION_NOT_AUTHORIZED")
            if not source["enabled"]:
                permission_reasons.append("SOURCE_DISABLED")
            if not source["storage_permission"]:
                permission_reasons.append("STORAGE_NOT_PERMITTED")
            sources.append({"source_id": source["source_id"], "source_name": source["source_name"],
                            "source_type": source["source_type"],
                            "permission_status": source["permission_status"],
                            "enabled": bool(source["enabled"]),
                            "storage_permission": bool(source["storage_permission"]),
                            "health": "READY" if not permission_reasons else "BLOCKED",
                            "block_reasons": permission_reasons})
        evidence_counts = [dict(row) for row in db.execute(
            "SELECT evidence_status,COUNT(*) AS count FROM ingestion_listings GROUP BY evidence_status ORDER BY evidence_status"
        )]
        status_counts = [dict(row) for row in db.execute(
            "SELECT validity_status,COUNT(*) AS count FROM ingestion_listings GROUP BY validity_status ORDER BY validity_status"
        )]
        freshness_counts = [dict(row) for row in db.execute(
            "SELECT freshness_status,COUNT(*) AS count FROM ingestion_listings GROUP BY freshness_status ORDER BY freshness_status"
        )]
        recent_quarantine = [dict(row) for row in db.execute(
            """SELECT q.run_id,q.source_id,q.row_index,q.quarantined_at,q.reason
               FROM ingestion_quarantine q ORDER BY q.quarantined_at DESC,q.id DESC LIMIT 20"""
        )]
        recent_runs = [dict(row) for row in db.execute(
            """SELECT run_id,source_id,started_at,finished_at,run_date,mode,status,received,accepted,inserted,
                      updated,duplicates,verified,newly_posted,newly_discovered,previously_seen,
                      expired,quarantined,rejected FROM ingestion_runs ORDER BY started_at DESC LIMIT 20"""
        )]
        return {
            "status": "OK", "run_date": day, "daily_goal": DAILY_LISTING_GOAL,
            "target_daily_goal": TARGET_DAILY_LISTING_GOAL,
            "target_count": target_count, "covered_targets": covered,
            "candidate_covered_targets": sum(1 for item in target_coverage if item["candidate_count"]),
            "targets_needing_data": sum(1 for item in target_coverage if not item["goal_met"]),
            "target_coverage": target_coverage,
            "candidate_count": candidate_count, "verified_count": verified_count,
            "stats_eligible_count": stats_count, "direct_url_count": direct_count,
            "direct_url_ratio": url_ratio, "daily_totals": totals,
            "source_health": sources, "evidence_counts": evidence_counts,
            "validity_counts": status_counts, "freshness_counts": freshness_counts,
            "recent_quarantine": recent_quarantine,
            "runs_today": runs, "recent_runs": recent_runs,
            "last_successful_ingestion": next((run["finished_at"] for run in recent_runs
                                                if run["status"].startswith("SUCCEEDED") or run["status"].startswith("APPLIED")), None),
            "scheduler_status": "NOT_ACTIVATED", "external_collection_enabled": False,
            "network_attempted": False, "production_database_written": False,
            "historical_dataset_mixed": False, "demo_database_mixed": False,
        }
    finally:
        db.close()


def lookup_pilot(pilot_db: Path = DEFAULT_PILOT_DB, *, target_rank: int | None = None,
                 property_type: str | None = None, limit: int = 200) -> dict[str, Any]:
    if not Path(pilot_db).is_file():
        return {"status": "NOT_INITIALIZED", "listings": []}
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    db = connect_pilot(Path(pilot_db), readonly=True)
    try:
        clauses, params = [], []
        if target_rank is not None:
            if not 1 <= target_rank <= 50:
                raise ValueError("target_rank must be between 1 and 50")
            clauses.append("l.target_rank=?")
            params.append(target_rank)
        if property_type:
            value = property_type.upper()
            if value not in PROPERTY_TYPES:
                raise ValueError("unsupported property_type")
            clauses.append("l.property_type=?")
            params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        listings = [dict(row) for row in db.execute(
            """SELECT l.listing_uid,l.primary_source_id,l.source_listing_id,l.source_url,
                      l.source_url_type,l.title,l.description,l.target_rank,l.original_ward,
                      l.original_district,l.original_province,l.property_type,l.transaction_type,
                      l.price_vnd,l.area_m2,l.price_per_m2,l.area_basis,l.address,l.published_at,
                      l.first_seen_at,l.last_seen_at,l.evidence_status,l.validity_status,
                      l.freshness_status,l.possible_duplicate,l.stats_eligible,l.review_reasons,
                      l.ingestion_run_id
               FROM ingestion_listings l""" + where +
            " ORDER BY l.last_seen_at DESC,l.target_rank LIMIT ?", (*params, limit)
        )]
        for item in listings:
            item["review_reasons"] = json.loads(item["review_reasons"] or "[]")
        stats_rows = []
        query = """SELECT target_rank,property_type,price_per_m2,last_seen_at FROM ingestion_listings
                   WHERE stats_eligible=1 AND validity_status='VALID' AND evidence_status='SOURCE_PAGE_CONFIRMED'
                     AND transaction_type='SALE' AND price_per_m2 IS NOT NULL"""
        stat_params: list[Any] = []
        if target_rank is not None:
            query += " AND target_rank=?"
            stat_params.append(target_rank)
        if property_type:
            query += " AND property_type=?"
            stat_params.append(property_type.upper())
        grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
        for row in db.execute(query, stat_params):
            grouped.setdefault((int(row["target_rank"]), row["property_type"]), []).append(row)
        for (rank, kind), rows in grouped.items():
            values = [float(row["price_per_m2"]) for row in rows]
            stats_rows.append({
                "target_rank": rank, "property_type": kind, "listing_count": len(values),
                "mean_price_per_m2": mean(values), "median_price_per_m2": median(values),
                "min_price_per_m2": min(values), "max_price_per_m2": max(values),
                "data_quality": "SOURCE_VERIFIED", "last_updated": max(row["last_seen_at"] for row in rows),
            })
        return {"status": "OK", "target_rank": target_rank,
                "property_type": property_type, "listings": listings,
                "statistics": stats_rows, "candidate_count": len(listings),
                "statistics_count": sum(row["listing_count"] for row in stats_rows),
                "network_attempted": False, "historical_dataset_mixed": False}
    finally:
        db.close()


def export_daily_report(pilot_db: Path = DEFAULT_PILOT_DB, *, run_date: str | None = None,
                        output_dir: Path = PROJECT_ROOT / "outputs" / "ingestion") -> dict[str, Any]:
    summary = monitoring_summary(pilot_db, run_date=run_date)
    day = summary.get("run_date") or run_date or now_local().date().isoformat()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"ingestion_daily_{day}.json"
    csv_path = output_dir / f"ingestion_daily_{day}.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    columns = ["metric", "value"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        rows = [
            ("daily_goal", summary.get("daily_goal", DAILY_LISTING_GOAL)),
            ("newly_posted_last_24h", summary.get("daily_totals", {}).get("newly_posted", 0)),
            ("newly_discovered", summary.get("daily_totals", {}).get("newly_discovered", 0)),
            ("previously_seen", summary.get("daily_totals", {}).get("previously_seen", 0)),
            ("updated", summary.get("daily_totals", {}).get("updated", 0)),
            ("verified", summary.get("daily_totals", {}).get("verified", 0)),
            ("quarantined", summary.get("daily_totals", {}).get("quarantined", 0)),
            ("stats_eligible_total", summary.get("stats_eligible_count", 0)),
            ("covered_targets", summary.get("covered_targets", 0)),
        ]
        writer.writerows({"metric": key, "value": value} for key, value in rows)
    return {"json_report": str(json_path), "csv_report": str(csv_path),
            "summary": summary, "email_sent": False}


def _move_file(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        destination = destination_dir / f"{source.stem}_{uuid.uuid4().hex[:8]}{source.suffix}"
    shutil.move(str(source), str(destination))
    return destination


def process_inbox(*, inbox: Path = DEFAULT_INBOX, processing: Path = DEFAULT_PROCESSING,
                  processed: Path = DEFAULT_PROCESSED, quarantine: Path = DEFAULT_QUARANTINE,
                  pilot_db: Path = DEFAULT_PILOT_DB, targets_db: Path = DEFAULT_TARGETS_DB,
                  source_registry: Path = DEFAULT_SOURCE_REGISTRY, source_id: str | None = None,
                  apply: bool = False, stability_seconds: float = 0.25) -> dict[str, Any]:
    inbox = Path(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in inbox.iterdir() if path.is_file() and path.suffix.casefold() in {".json", ".csv", ".xlsx"})
    results = []
    for path in files:
        before = path.stat()
        if stability_seconds > 0:
            time.sleep(min(stability_seconds, 2.0))
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            results.append({"file": path.name, "status": "DEFERRED_FILE_STILL_CHANGING"})
            continue
        target_path = path
        if apply:
            target_path = _move_file(path, Path(processing))
        try:
            report = ingest_file(
                target_path, pilot_db=pilot_db, targets_db=targets_db,
                source_registry=source_registry, source_id=source_id, apply=apply,
                mode="INBOX_IMPORT",
            )
            report["file"] = target_path.name
            if apply:
                destination_dir = quarantine if report["status"] == "BLOCKED_SOURCE" else processed
                report["moved_to"] = str(_move_file(target_path, Path(destination_dir)))
            results.append(report)
        except (OSError, ValueError, sqlite3.Error) as exc:
            safe_error = str(exc) if isinstance(exc, IngestionError) else type(exc).__name__
            item = {"file": target_path.name, "status": "FAILED", "error": safe_error,
                    "network_attempted": False}
            if apply and target_path.exists():
                item["moved_to"] = str(_move_file(target_path, Path(quarantine)))
            results.append(item)
    return {"status": "OK", "files_seen": len(files), "results": results,
            "applied": apply, "network_attempted": False,
            "production_database_written": False}


def scheduler_dry_run(*, pilot_db: Path = DEFAULT_PILOT_DB, targets_db: Path = DEFAULT_TARGETS_DB,
                      source_registry: Path = DEFAULT_SOURCE_REGISTRY, inbox: Path = DEFAULT_INBOX,
                      output_dir: Path = PROJECT_ROOT / "outputs" / "ingestion") -> dict[str, Any]:
    inbox_preview = process_inbox(inbox=inbox, pilot_db=pilot_db, targets_db=targets_db,
                                  source_registry=source_registry, apply=False, stability_seconds=0)
    status = monitoring_summary(pilot_db)
    report = {
        "status": "DRY_RUN_ONLY", "scheduled_local_time": "08:00",
        "timezone": "Asia/Ho_Chi_Minh", "daily_goal": DAILY_LISTING_GOAL,
        "target_count": status.get("target_count", 0), "inbox": inbox_preview,
        "current_pipeline": status, "task_scheduler_registered": False,
        "network_attempted": False, "database_written": False,
        "production_database_written": False,
    }
    if Path(pilot_db).is_file():
        report["reports"] = export_daily_report(pilot_db, output_dir=output_dir)
    return report


def _benchmark_source_registry(path: Path) -> None:
    source = {
        "source_id": "benchmark-synthetic", "source_name": "Temporary synthetic benchmark",
        "source_type": "USER_SUPPLIED", "permission_status": "AUTHORIZED",
        "permission_evidence": "Temporary benchmark fixture; never production data.",
        "permitted_scope": "Temporary in-memory benchmark database only.",
        "permitted_frequency": "One offline benchmark run.", "storage_permission": True,
        "attribution_requirements": "Synthetic benchmark; no external source.",
        "last_reviewed_at": now_local().date().isoformat(), "enabled": True,
        "capabilities": {"published_at_authoritative": False}, "metadata": {"synthetic": True},
    }
    path.write_text(json.dumps({"version": 1, "sources": [source]}, indent=2), encoding="utf-8")


def benchmark_synthetic_500(*, targets_db: Path = DEFAULT_TARGETS_DB,
                            count: int = 500) -> dict[str, Any]:
    """Measure the full normalized insert path in a disposable temporary database."""
    if count < 1 or count > 10_000:
        raise ValueError("benchmark count must be between 1 and 10000")
    targets = _load_targets(targets_db)
    with tempfile.TemporaryDirectory(prefix="wardprice-ingestion-benchmark-") as folder:
        root = Path(folder)
        pilot_db = root / "benchmark.sqlite3"
        registry = root / "sources.json"
        _benchmark_source_registry(registry)
        init_pilot_db(pilot_db, targets_db=targets_db, source_registry=registry)
        per_target = [targets[index % len(targets)] for index in range(count)]
        listings = []
        for index, target in enumerate(per_target, start=1):
            listings.append({
                "source_id": "benchmark-synthetic", "source_listing_id": f"fixture-{index:05d}",
                "source_url": f"https://benchmark.invalid/listing/{index}",
                "source_url_type": "DIRECT_LISTING", "title": f"Synthetic listing {index}",
                "target_rank": target["target_rank"], "original_ward": target["original_ward"],
                "original_district": target["original_district"], "original_province": target["original_province"],
                "property_type": ("DAT_O", "NHA_RIENG", "CHUNG_CU")[index % 3],
                "transaction_type": "SALE", "price_vnd": 3_000_000_000 + index * 1_000_000,
                "area_m2": 60 + index % 30, "address": f"Đường mẫu, {target['original_ward']}",
            })
        payload = {"source_id": "benchmark-synthetic", "snapshot_date": now_local().date().isoformat(),
                   "listings": listings}
        tracemalloc.start()
        started = time.perf_counter()
        report = _ingest_payload(
            payload, pilot_db=pilot_db, targets_db=targets_db, source_registry=registry,
            apply=True, mode="FILE_IMPORT", _allow_synthetic_test_data=True,
        )
        elapsed = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        verify_db = sqlite3.connect(pilot_db)
        try:
            pilot_count = verify_db.execute(
                "SELECT COUNT(*) FROM ingestion_listings"
            ).fetchone()[0]
        finally:
            verify_db.close()
        if pilot_count != count or report["inserted"] != count:
            raise AssertionError(f"Expected {count} synthetic records in temporary benchmark DB; got {pilot_count}.")
        replay = _ingest_payload(
            payload, pilot_db=pilot_db, targets_db=targets_db, source_registry=registry,
            apply=True, mode="FILE_IMPORT", _allow_synthetic_test_data=True,
        )
        verify_db = sqlite3.connect(pilot_db)
        try:
            observations = verify_db.execute(
                "SELECT COUNT(*) FROM ingestion_observations"
            ).fetchone()[0]
        finally:
            verify_db.close()
        return {
            "status": "PASS", "records_processed": count, "inserted_first_pass": report["inserted"],
            "unique_listings": pilot_count, "replay_inserted": replay["inserted"],
            "replay_duplicates_existing": replay["previously_seen"], "unique_observations": observations,
            "elapsed_seconds": round(elapsed, 4), "peak_python_memory_bytes": peak,
            "temporary_database_only": True, "synthetic_data_in_production": False,
            "network_attempted": False,
        }


def _print_json(value: Any) -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "sources", "status", "report", "scheduler-dry-run", "benchmark"):
        command = sub.add_parser(name)
        command.add_argument("--pilot-db", type=Path, default=DEFAULT_PILOT_DB)
        command.add_argument("--targets-db", type=Path, default=DEFAULT_TARGETS_DB)
        command.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
        if name in {"report", "scheduler-dry-run"}:
            command.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "ingestion")
        if name == "scheduler-dry-run":
            command.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
        if name == "benchmark":
            command.add_argument("--count", type=int, default=500)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--file", type=Path, required=True)
    ingest.add_argument("--source-id")
    ingest.add_argument("--pilot-db", type=Path, default=DEFAULT_PILOT_DB)
    ingest.add_argument("--targets-db", type=Path, default=DEFAULT_TARGETS_DB)
    ingest.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    ingest.add_argument("--apply", action="store_true")
    ingest.add_argument("--operator-verified", action="store_true")
    ingest.add_argument("--verified-by")
    ingest.add_argument("--verification-reference")
    inbox = sub.add_parser("inbox")
    inbox.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    inbox.add_argument("--processing", type=Path, default=DEFAULT_PROCESSING)
    inbox.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED)
    inbox.add_argument("--quarantine", type=Path, default=DEFAULT_QUARANTINE)
    inbox.add_argument("--source-id")
    inbox.add_argument("--pilot-db", type=Path, default=DEFAULT_PILOT_DB)
    inbox.add_argument("--targets-db", type=Path, default=DEFAULT_TARGETS_DB)
    inbox.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    inbox.add_argument("--apply", action="store_true")
    inbox.add_argument("--watch", action="store_true")
    inbox.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = init_pilot_db(args.pilot_db, targets_db=args.targets_db,
                                   source_registry=args.source_registry)
        elif args.command == "sources":
            result = list_sources(args.source_registry)
        elif args.command == "status":
            result = monitoring_summary(args.pilot_db)
        elif args.command == "report":
            result = export_daily_report(args.pilot_db, output_dir=args.output_dir)
        elif args.command == "scheduler-dry-run":
            result = scheduler_dry_run(pilot_db=args.pilot_db, targets_db=args.targets_db,
                                       source_registry=args.source_registry, inbox=args.inbox,
                                       output_dir=args.output_dir)
        elif args.command == "benchmark":
            result = benchmark_synthetic_500(targets_db=args.targets_db, count=args.count)
        elif args.command == "ingest":
            result = ingest_file(
                args.file, pilot_db=args.pilot_db, targets_db=args.targets_db,
                source_registry=args.source_registry, source_id=args.source_id,
                apply=args.apply, operator_verified=args.operator_verified,
                verified_by=args.verified_by, verification_reference=args.verification_reference,
            )
        else:
            def run_once() -> dict[str, Any]:
                return process_inbox(
                    inbox=args.inbox, processing=args.processing, processed=args.processed,
                    quarantine=args.quarantine, pilot_db=args.pilot_db, targets_db=args.targets_db,
                    source_registry=args.source_registry, source_id=args.source_id,
                    apply=args.apply,
                )
            if args.watch:
                pipeline_config = PROJECT_ROOT / "config" / "ingestion_pipeline.json"
                config = json.loads(pipeline_config.read_text(encoding="utf-8"))
                if not config.get("file_drop_enabled", False):
                    raise IngestionError("File-drop watch is disabled in config/ingestion_pipeline.json.")
                if not args.apply:
                    raise IngestionError("--watch requires --apply; otherwise use inbox preview once.")
                if args.interval < 1:
                    raise IngestionError("watch interval must be at least 1 second")
                while True:
                    _print_json(run_once())
                    time.sleep(args.interval)
            else:
                result = run_once()
        _print_json(result)
    except (OSError, sqlite3.Error, ValueError, KeyError, json.JSONDecodeError) as exc:
        message = str(exc) if isinstance(exc, IngestionError) else type(exc).__name__
        raise SystemExit(f"ERROR: {message}") from exc


if __name__ == "__main__":
    main()
