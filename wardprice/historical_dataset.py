"""Isolated, non-commercial TiniX AI historical dataset pilot importer.

Historical rows live in their own SQLite tables and are never written into the
current listing/observation/statistics pipeline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .national_registry import normalize_admin_name

DATASET_ID = "tinixai/vietnam-real-estates"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
LICENSE_ID = "cc-by-nc-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
MAX_IMPORT_CANDIDATES = 10_000
MAX_SOURCE_ROWS = 10_000
DEFAULT_TARGETS_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_PILOT_DB = PROJECT_ROOT / "state" / "ward_prices.historical_pilot.sqlite3"
DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "historical_pilot" / "tinix_sample.jsonl"
DEFAULT_METADATA = PROJECT_ROOT / "data" / "historical_pilot" / "tinix_sample.metadata.json"

PROPERTY_TYPE_MAP = {
    normalize_admin_name("Nhà"): "NHA_RIENG",
    normalize_admin_name("Căn hộ chung cư"): "CHUNG_CU",
}
PROPERTY_REVIEW_TYPES = {
    normalize_admin_name("Đất"): "LAND_UNSPECIFIED",
    normalize_admin_name("Biệt thự/Nhà liền kề"): "HOUSE_SUBTYPE_REVIEW",
    normalize_admin_name("Shophouse"): "MIXED_USE_REVIEW",
}
LAND_RESIDENTIAL_TITLE_CUES = ("dat o", "dat tho cu", "tho cu")
LAND_NONRESIDENTIAL_OR_MIXED_CUES = (
    "dat nong nghiep",
    "dat vuon",
    "nong nghiep",
    "co tho cu",
    "mot phan tho cu",
    "khong tho cu",
    "khong co tho cu",
    "chua tho cu",
    "chua co tho cu",
)
SALE_CUES = (
    "can ban",
    "chinh chu ban",
    "ban gap",
    "ban nha",
    "ban dat",
    "ban can ho",
    "ban chung cu",
    "ban biet thu",
    "ban shophouse",
    "chuyen nhuong",
    "sang nhuong",
)
RENT_CUES = (
    "cho thue",
    "can thue",
    "chinh chu cho thue",
    "thue mat bang",
    "thue nha",
    "thue can ho",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_dataset_registry (
    dataset_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    dataset_url TEXT NOT NULL,
    license_id TEXT NOT NULL,
    license_url TEXT NOT NULL,
    attribution TEXT NOT NULL,
    source_record_count INTEGER NOT NULL,
    sample_method TEXT NOT NULL,
    sample_row_count INTEGER NOT NULL,
    sample_sha256 TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    full_dataset_downloaded INTEGER NOT NULL CHECK(full_dataset_downloaded = 0),
    commercial_use INTEGER NOT NULL CHECK(commercial_use = 0),
    PRIMARY KEY(dataset_id, revision)
);
CREATE TABLE IF NOT EXISTS historical_target_registry (
    target_rank INTEGER PRIMARY KEY CHECK(target_rank BETWEEN 1 AND 50),
    original_ward TEXT NOT NULL,
    original_district TEXT NOT NULL,
    original_province TEXT NOT NULL,
    source_reference TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_candidates (
    candidate_id TEXT PRIMARY KEY,
    dedupe_fingerprint TEXT NOT NULL UNIQUE,
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    first_source_row_index INTEGER NOT NULL,
    target_rank INTEGER NOT NULL CHECK(target_rank BETWEEN 1 AND 50),
    original_ward TEXT NOT NULL,
    original_district TEXT NOT NULL,
    original_province TEXT NOT NULL,
    title TEXT NOT NULL,
    property_type_raw TEXT NOT NULL,
    property_type TEXT,
    deal_type TEXT NOT NULL CHECK(deal_type IN (
        'EXPLICIT_SALE','EXPLICIT_RENT','AMBIGUOUS','UNCLASSIFIED'
    )),
    deal_classification TEXT NOT NULL CHECK(deal_classification IN (
        'SALE_CONFIRMED_BY_TEXT','RENT_CONFIRMED_BY_TEXT','AMBIGUOUS','CONFLICT'
    )),
    dedupe_classification TEXT NOT NULL CHECK(dedupe_classification IN (
        'EXACT_DUPLICATE','POSSIBLE_DUPLICATE','DISTINCT','NEEDS_REVIEW'
    )),
    price_vnd REAL NOT NULL CHECK(price_vnd > 0),
    area_m2 REAL NOT NULL CHECK(area_m2 > 0),
    price_per_m2 REAL NOT NULL CHECK(price_per_m2 > 0),
    published_date TEXT NOT NULL,
    evidence_status TEXT NOT NULL CHECK(evidence_status = 'HISTORICAL_DATASET_UNVERIFIED'),
    candidate_status TEXT NOT NULL,
    review_reason TEXT,
    sample_quality_flags TEXT NOT NULL DEFAULT '[]',
    source_dataset_url TEXT NOT NULL,
    source_row_index INTEGER NOT NULL,
    source_shard TEXT,
    source_row_in_shard INTEGER,
    raw_payload TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY(target_rank) REFERENCES historical_target_registry(target_rank),
    FOREIGN KEY(dataset_id,dataset_revision)
        REFERENCES historical_dataset_registry(dataset_id,revision)
);
CREATE INDEX IF NOT EXISTS ix_historical_candidate_target_type_date
    ON historical_candidates(target_rank,property_type,published_date);
CREATE INDEX IF NOT EXISTS ix_historical_candidate_status
    ON historical_candidates(candidate_status,deal_type);
CREATE TABLE IF NOT EXISTS historical_source_rows (
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_row_index INTEGER NOT NULL,
    source_shard TEXT,
    source_row_in_shard INTEGER,
    outcome TEXT NOT NULL,
    reason TEXT,
    dedupe_classification TEXT NOT NULL CHECK(dedupe_classification IN (
        'EXACT_DUPLICATE','POSSIBLE_DUPLICATE','DISTINCT','NEEDS_REVIEW'
    )),
    target_rank INTEGER,
    candidate_id TEXT,
    processed_at TEXT NOT NULL,
    PRIMARY KEY(dataset_id,dataset_revision,source_row_index),
    FOREIGN KEY(candidate_id) REFERENCES historical_candidates(candidate_id)
);
CREATE INDEX IF NOT EXISTS ix_historical_source_rows_candidate
    ON historical_source_rows(candidate_id);
CREATE TABLE IF NOT EXISTS historical_observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    published_date TEXT NOT NULL,
    observed_price_vnd REAL NOT NULL,
    observed_area_m2 REAL NOT NULL,
    price_per_m2 REAL NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(candidate_id,dataset_id,dataset_revision),
    FOREIGN KEY(candidate_id) REFERENCES historical_candidates(candidate_id)
);
CREATE INDEX IF NOT EXISTS ix_historical_observation_date
    ON historical_observations(published_date,candidate_id);
CREATE TABLE IF NOT EXISTS historical_quarantine (
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    source_row_index INTEGER NOT NULL,
    reason TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    quarantined_at TEXT NOT NULL,
    PRIMARY KEY(dataset_id,dataset_revision,source_row_index)
);
CREATE TABLE IF NOT EXISTS historical_monthly_statistics (
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    property_type TEXT NOT NULL CHECK(property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')),
    published_month TEXT NOT NULL,
    n_samples INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    mean_price_per_m2 REAL NOT NULL,
    mean_without_outliers REAL,
    median_price_per_m2 REAL NOT NULL,
    p25_price_per_m2 REAL NOT NULL,
    p75_price_per_m2 REAL NOT NULL,
    min_price_per_m2 REAL NOT NULL,
    max_price_per_m2 REAL NOT NULL,
    outlier_count INTEGER NOT NULL,
    outlier_method TEXT NOT NULL,
    sample_quality_flags TEXT NOT NULL,
    latest_published_date TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    PRIMARY KEY(dataset_id,dataset_revision,target_rank,property_type,published_month),
    FOREIGN KEY(target_rank) REFERENCES historical_target_registry(target_rank)
);
CREATE TABLE IF NOT EXISTS historical_import_runs (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    sample_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL,
    input_rows INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    network_attempted INTEGER NOT NULL CHECK(network_attempted = 0),
    production_database_written INTEGER NOT NULL CHECK(production_database_written = 0)
);
CREATE TABLE IF NOT EXISTS historical_dataset_batches (
    batch_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    sample_sha256 TEXT NOT NULL,
    sample_row_count INTEGER NOT NULL,
    new_source_row_count INTEGER NOT NULL,
    sample_method TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    batch_metadata_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('COMPLETE')),
    UNIQUE(dataset_id,revision,sample_sha256)
);
CREATE TABLE IF NOT EXISTS historical_duplicate_pairs (
    dataset_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    candidate_id_a TEXT NOT NULL,
    candidate_id_b TEXT NOT NULL,
    classification TEXT NOT NULL CHECK(classification IN ('EXACT_DUPLICATE','POSSIBLE_DUPLICATE')),
    reason TEXT NOT NULL,
    audited_at TEXT NOT NULL,
    PRIMARY KEY(dataset_id,dataset_revision,candidate_id_a,candidate_id_b),
    FOREIGN KEY(candidate_id_a) REFERENCES historical_candidates(candidate_id),
    FOREIGN KEY(candidate_id_b) REFERENCES historical_candidates(candidate_id)
);
CREATE TABLE IF NOT EXISTS historical_quality_audits (
    audit_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    sample_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    report_path TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    UNIQUE(dataset_id,revision,batch_id,sample_sha256)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_geography(value: Any, level: str) -> str:
    normalized = normalize_admin_name(value)
    prefixes = {
        "province": (("thanh", "pho"), ("tinh",), ("tp",)),
        "district": (("thanh", "pho"), ("quan",), ("huyen",), ("thi", "xa"), ("q",)),
        "ward": (("phuong",), ("xa",), ("thi", "tran"), ("dac", "khu"), ("p",)),
    }[level]
    tokens = normalized.split()
    for prefix in prefixes:
        if tuple(tokens[: len(prefix)]) == prefix:
            return " ".join(tokens[len(prefix) :])
    return normalized


def _geography_key(province: Any, district: Any, ward: Any) -> tuple[str, str, str]:
    return (
        _normalize_geography(province, "province"),
        _normalize_geography(district, "district"),
        _normalize_geography(ward, "ward"),
    )


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _published_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None


def _deal_classification(title: str) -> str:
    normalized = normalize_admin_name(title)
    sale = any(cue in normalized for cue in SALE_CUES)
    rent = any(cue in normalized for cue in RENT_CUES)
    if sale and rent:
        # A listing can describe a tenant/lease while still being offered for sale.
        # Without enough context, do not infer transaction intent from that phrase.
        if "dang cho thue" in normalized or "hop dong thue" in normalized:
            return "AMBIGUOUS"
        return "CONFLICT"
    if sale:
        return "SALE_CONFIRMED_BY_TEXT"
    if rent:
        return "RENT_CONFIRMED_BY_TEXT"
    return "AMBIGUOUS"


def _deal_type(title: str) -> str:
    classification = _deal_classification(title)
    if classification == "SALE_CONFIRMED_BY_TEXT":
        return "EXPLICIT_SALE"
    if classification == "RENT_CONFIRMED_BY_TEXT":
        return "EXPLICIT_RENT"
    if classification == "CONFLICT":
        return "AMBIGUOUS"
    return "UNCLASSIFIED"


def _property_type(raw_value: Any, title: Any = "") -> tuple[str | None, str | None]:
    raw = str(raw_value or "").strip()
    normalized = normalize_admin_name(raw)
    if normalized in PROPERTY_TYPE_MAP:
        return PROPERTY_TYPE_MAP[normalized], None
    if normalized == normalize_admin_name("Đất"):
        title_normalized = normalize_admin_name(title)
        title_tokens = title_normalized.split()

        def has_phrase(phrase: str) -> bool:
            phrase_tokens = phrase.split()
            return any(
                title_tokens[index : index + len(phrase_tokens)] == phrase_tokens
                for index in range(len(title_tokens) - len(phrase_tokens) + 1)
            )

        has_explicit_residential_cue = any(has_phrase(cue) for cue in LAND_RESIDENTIAL_TITLE_CUES)
        has_conflicting_or_mixed_cue = any(
            has_phrase(cue) for cue in LAND_NONRESIDENTIAL_OR_MIXED_CUES
        )
        if has_explicit_residential_cue and not has_conflicting_or_mixed_cue:
            return "DAT_O", "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED"
    if normalized in PROPERTY_REVIEW_TYPES:
        return None, PROPERTY_REVIEW_TYPES[normalized]
    return None, "PROPERTY_TYPE_UNMAPPED"


def _sample_quality_level(sample_count: int) -> str:
    if sample_count < 5:
        return "INSUFFICIENT_SAMPLE"
    if sample_count < 10:
        return "LOW_CONFIDENCE"
    return "DESCRIPTIVE_SAMPLE"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def load_sample(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TypeError(f"Sample line {line_number} must be a JSON object")
            rows.append(row)
    return rows


def load_metadata(path: Path) -> dict[str, Any]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("dataset_id") != DATASET_ID:
        raise ValueError("Unexpected dataset id; refusing import")
    if metadata.get("license_id") != LICENSE_ID:
        raise ValueError("Dataset license is not CC BY-NC 4.0; refusing import")
    if metadata.get("private") or metadata.get("gated"):
        raise ValueError("Dataset is not public; refusing import")
    if metadata.get("full_dataset_downloaded") is not False:
        raise ValueError("Metadata does not confirm a bounded sample")
    if metadata.get("commercial_use") is not False:
        raise ValueError("Pilot is restricted to non-commercial use")
    if not metadata.get("revision") or not metadata.get("sample_rows"):
        raise ValueError("Dataset revision and sample row count are required")
    if int(metadata["sample_rows"]) > MAX_SOURCE_ROWS:
        raise ValueError(f"Sample exceeds the configured {MAX_SOURCE_ROWS:,}-row safety limit")
    fields = {feature.get("name") for feature in metadata.get("schema", [])}
    required = {
        "name", "property_type_name", "province_name", "district_name", "ward_name",
        "price", "area", "published_at",
    }
    if not required.issubset(fields):
        raise ValueError(f"Dataset schema is missing required fields: {sorted(required - fields)}")
    return metadata


def read_targets(targets_db: Path) -> list[dict[str, Any]]:
    if not targets_db.is_file():
        raise FileNotFoundError(f"Target database not found: {targets_db}")
    connection = sqlite3.connect(f"{targets_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='priority_targets'"
        ).fetchone()
        if exists is None:
            raise ValueError("Target database has no priority_targets table")
        targets = [
            dict(row)
            for row in connection.execute(
                """SELECT target_rank,original_ward,original_district,original_province,
                          source_reference
                   FROM priority_targets ORDER BY target_rank"""
            )
        ]
    finally:
        connection.close()
    if len(targets) != 50 or {int(row["target_rank"]) for row in targets} != set(range(1, 51)):
        raise ValueError(f"Expected exactly 50 ranked targets; found {len(targets)}")
    return targets


def _target_index(targets: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for target in targets:
        key = _geography_key(
            target["original_province"], target["original_district"], target["original_ward"]
        )
        if key in result:
            raise ValueError("Top50 contains duplicate normalized province/district/ward keys")
        result[key] = target
    return result


def _candidate_record(
    row: dict[str, Any], target: dict[str, Any], revision: str, batch_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    title = str(row.get("name") or "").strip()
    price = _positive_number(row.get("price"))
    area = _positive_number(row.get("area"))
    published = _published_date(row.get("published_at"))
    missing: list[str] = []
    if not title:
        missing.append("MISSING_TITLE")
    if price is None:
        missing.append("INVALID_OR_MISSING_PRICE")
    if area is None:
        missing.append("INVALID_OR_MISSING_AREA")
    if published is None:
        missing.append("INVALID_OR_MISSING_PUBLISHED_DATE")
    if missing:
        return None, ";".join(missing)

    raw_property = str(row.get("property_type_name") or "").strip()
    mapped_type, type_review = _property_type(raw_property, title)
    deal_type = _deal_type(title)
    deal_classification = _deal_classification(title)
    reasons: list[str] = []
    if deal_type != "EXPLICIT_SALE":
        reasons.append(
            "RENT_PERIOD_UNSPECIFIED" if deal_type == "EXPLICIT_RENT" else "TRANSACTION_UNCLASSIFIED"
        )
    if type_review:
        reasons.append(type_review)
    candidate_status = (
        "ELIGIBLE_HISTORICAL_SALE"
        if deal_type == "EXPLICIT_SALE" and mapped_type in {"NHA_RIENG", "CHUNG_CU", "DAT_O"}
        else "NEEDS_REVIEW"
    )
    price_per_m2 = price / area
    if not math.isfinite(price_per_m2) or price_per_m2 <= 0:
        return None, "INVALID_PRICE_PER_M2"
    row_index = int(row["source_row_index"])
    fingerprint_payload = {
        "target_rank": int(target["target_rank"]),
        "title": normalize_admin_name(title),
        "property_type": normalize_admin_name(raw_property),
        "price_vnd": format(price, ".12g"),
        "area_m2": format(area, ".12g"),
        "published_date": published,
        "street_name": normalize_admin_name(row.get("street_name")),
        "project_name": normalize_admin_name(row.get("project_name")),
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    candidate_id = f"tinix_{fingerprint[:32]}"
    safe_payload = json.dumps(_json_safe(row), ensure_ascii=False, sort_keys=True, allow_nan=False)
    return {
        "candidate_id": candidate_id,
        "dedupe_fingerprint": fingerprint,
        "dataset_id": DATASET_ID,
        "dataset_revision": revision,
        "batch_id": batch_id,
        "first_source_row_index": row_index,
        "target_rank": int(target["target_rank"]),
        "original_ward": str(target["original_ward"]),
        "original_district": str(target["original_district"]),
        "original_province": str(target["original_province"]),
        "title": title,
        "property_type_raw": raw_property,
        "property_type": mapped_type,
        "deal_type": deal_type,
        "deal_classification": deal_classification,
        "dedupe_classification": "DISTINCT",
        "price_vnd": price,
        "area_m2": area,
        "price_per_m2": price_per_m2,
        "published_date": published,
        "evidence_status": "HISTORICAL_DATASET_UNVERIFIED",
        "candidate_status": candidate_status,
        "review_reason": ";".join(reasons) or None,
        "sample_quality_flags": [],
        "source_dataset_url": DATASET_URL,
        "source_row_index": row_index,
        "source_shard": row.get("source_shard"),
        "source_row_in_shard": row.get("source_row_in_shard"),
        "raw_payload": safe_payload,
    }, None


def _normalized_content_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    payload = json.loads(candidate["raw_payload"])
    return (
        int(candidate["target_rank"]),
        normalize_admin_name(candidate["title"]),
        normalize_admin_name(candidate["property_type_raw"]),
        format(float(candidate["price_vnd"]), ".12g"),
        format(float(candidate["area_m2"]), ".12g"),
        normalize_admin_name(payload.get("street_name")),
        normalize_admin_name(payload.get("project_name")),
    )


def _weak_dedupe_identity(candidate: dict[str, Any]) -> bool:
    payload = json.loads(candidate["raw_payload"])
    title = normalize_admin_name(candidate["title"])
    tokens = [token for token in title.split() if len(token) > 1]
    has_location_detail = bool(
        normalize_admin_name(payload.get("street_name"))
        or normalize_admin_name(payload.get("project_name"))
    )
    return len(tokens) < 3 and not has_location_detail


def _possible_duplicate_signatures(candidate: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Index likely relistings by target, type, detailed title and address cue."""
    payload = json.loads(candidate["raw_payload"])
    title = normalize_admin_name(candidate["title"])
    if len([token for token in title.split() if len(token) > 1]) < 4:
        return []
    street = normalize_admin_name(payload.get("street_name"))
    project = normalize_admin_name(payload.get("project_name"))
    prefix = (
        int(candidate["target_rank"]),
        normalize_admin_name(candidate["property_type_raw"]),
        title,
    )
    signatures = []
    if street:
        signatures.append((*prefix, "street", street))
    if project:
        signatures.append((*prefix, "project", project))
    return signatures


def plan_import(
    rows: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    known_source_rows: set[int] | None = None,
    candidates_by_fingerprint: dict[str, str] | None = None,
    existing_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if len(rows) != int(metadata["sample_rows"]):
        raise ValueError(
            f"Sample has {len(rows)} rows but metadata declares {metadata['sample_rows']}"
        )
    source_indexes = [row.get("source_row_index") for row in rows]
    if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in source_indexes):
        raise ValueError("Every sample row needs a stable non-negative source_row_index")
    if len(source_indexes) != len(set(source_indexes)):
        raise ValueError("Sample contains repeated source_row_index values")
    target_by_key = _target_index(targets)
    known_source_rows = known_source_rows or set()
    candidates_by_fingerprint = candidates_by_fingerprint or {}
    seen_fingerprints = dict(candidates_by_fingerprint)
    seen_candidates = list(existing_candidates or [])
    seen_content: dict[tuple[Any, ...], dict[str, Any]] = {}
    possible_duplicate_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for existing in seen_candidates:
        try:
            if not _weak_dedupe_identity(existing):
                seen_content.setdefault(_normalized_content_key(existing), existing)
            for signature in _possible_duplicate_signatures(existing):
                possible_duplicate_index[signature].append(existing)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    source_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    duplicate_pairs: list[dict[str, Any]] = []
    batch_id = _batch_id(metadata)
    counts: dict[str, Any] = {
        "input_rows": len(rows),
        "matched_top50_rows": 0,
        "eligible_historical_sales": 0,
        "needs_review_candidates": 0,
        "explicit_rent_candidates": 0,
        "unclassified_transaction_candidates": 0,
        "unmapped_property_candidates": 0,
        "rejected_outside_top50": 0,
        "quarantined_invalid_core_fields": 0,
        "duplicate_content_rows": 0,
        "possible_duplicate_rows": 0,
        "dedupe_classification_counts": {},
        "replayed_source_rows": 0,
        "quarantine_reasons": {},
        "deal_type_counts": {},
        "deal_classification_counts": {},
        "raw_property_type_counts": {},
    }
    matched_ranks: set[int] = set()

    for row in rows:
        row_index = row.get("source_row_index")
        if isinstance(row_index, bool) or not isinstance(row_index, int) or row_index < 0:
            raise ValueError("Every sample row needs a stable non-negative source_row_index")
        if row_index in known_source_rows:
            counts["replayed_source_rows"] += 1
            continue
        source_shard = row.get("source_shard")
        source_row_in_shard = row.get("source_row_in_shard")
        raw_payload = json.dumps(_json_safe(row), ensure_ascii=False, sort_keys=True, allow_nan=False)
        target = target_by_key.get(
            _geography_key(row.get("province_name"), row.get("district_name"), row.get("ward_name"))
        )
        if target is None:
            counts["rejected_outside_top50"] += 1
            source_rows.append({
                "batch_id": batch_id,
                "source_row_index": row_index,
                "source_shard": source_shard,
                "source_row_in_shard": source_row_in_shard,
                "outcome": "OUTSIDE_TOP50",
                "reason": "NO_EXACT_LEGACY_PROVINCE_DISTRICT_WARD_MATCH",
                "dedupe_classification": "DISTINCT" if row.get("name") else "NEEDS_REVIEW",
                "target_rank": None,
                "candidate_id": None,
                "matched_candidate_id": None,
                "raw_payload": raw_payload,
            })
            continue
        counts["matched_top50_rows"] += 1
        matched_ranks.add(int(target["target_rank"]))
        candidate, reason = _candidate_record(
            row, target, str(metadata["revision"]), batch_id
        )
        if candidate is None:
            counts["quarantined_invalid_core_fields"] += 1
            for reason_code in (reason or "INVALID_CORE_FIELDS").split(";"):
                counts["quarantine_reasons"][reason_code] = (
                    counts["quarantine_reasons"].get(reason_code, 0) + 1
                )
            quarantine.append({
                "source_row_index": row_index,
                "reason": reason or "INVALID_CORE_FIELDS",
                "raw_payload": json.dumps(_json_safe(row), ensure_ascii=False, allow_nan=False),
            })
            source_rows.append({
                "batch_id": batch_id,
                "source_row_index": row_index,
                "source_shard": source_shard,
                "source_row_in_shard": source_row_in_shard,
                "outcome": "QUARANTINED",
                "reason": reason,
                "dedupe_classification": "NEEDS_REVIEW",
                "target_rank": int(target["target_rank"]),
                "candidate_id": None,
                "matched_candidate_id": None,
                "raw_payload": raw_payload,
            })
            continue

        known_candidate_id = seen_fingerprints.get(candidate["dedupe_fingerprint"])
        content_match = None
        if known_candidate_id is None and not _weak_dedupe_identity(candidate):
            content_match = seen_content.get(_normalized_content_key(candidate))
            if content_match is not None:
                known_candidate_id = str(content_match["candidate_id"])
        if known_candidate_id:
            counts["duplicate_content_rows"] += 1
            candidate_id = known_candidate_id
            outcome = "DUPLICATE_CONTENT"
            dedupe_classification = "EXACT_DUPLICATE"
            matched_candidate_id = known_candidate_id
        else:
            possible_match = None
            for signature in _possible_duplicate_signatures(candidate):
                possible_match = next(
                    (
                        item
                        for item in possible_duplicate_index.get(signature, [])
                        if float(item["price_vnd"]) != float(candidate["price_vnd"])
                        or float(item["area_m2"]) != float(candidate["area_m2"])
                    ),
                    None,
                )
                if possible_match is not None:
                    break
            if possible_match is not None:
                dedupe_classification = "POSSIBLE_DUPLICATE"
                candidate["candidate_status"] = "NEEDS_REVIEW"
                candidate["review_reason"] = ";".join(
                    filter(None, (candidate["review_reason"], "POSSIBLE_DUPLICATE_PRICE_OR_AREA_CHANGED"))
                )
                counts["possible_duplicate_rows"] += 1
                matched_candidate_id = str(possible_match["candidate_id"])
                possible_match["candidate_status"] = "NEEDS_REVIEW"
                possible_match["dedupe_classification"] = "POSSIBLE_DUPLICATE"
                possible_match["review_reason"] = ";".join(
                    filter(
                        None,
                        (
                            possible_match.get("review_reason"),
                            "POSSIBLE_DUPLICATE_PRICE_OR_AREA_CHANGED",
                        ),
                    )
                )
                duplicate_pairs.append(
                    {
                        "batch_id": batch_id,
                        "candidate_id_a": min(matched_candidate_id, candidate["candidate_id"]),
                        "candidate_id_b": max(matched_candidate_id, candidate["candidate_id"]),
                        "classification": "POSSIBLE_DUPLICATE",
                        "reason": "SAME_TARGET_TYPE_TITLE_AND_STREET_OR_PROJECT_BUT_PRICE_OR_AREA_DIFFERS",
                    }
                )
            elif _weak_dedupe_identity(candidate):
                dedupe_classification = "NEEDS_REVIEW"
                candidate["candidate_status"] = "NEEDS_REVIEW"
                candidate["review_reason"] = ";".join(
                    filter(None, (candidate["review_reason"], "WEAK_DEDUPE_IDENTITY"))
                )
                matched_candidate_id = None
            else:
                dedupe_classification = "DISTINCT"
                matched_candidate_id = None
            candidate["dedupe_classification"] = dedupe_classification
            candidates.append(candidate)
            seen_fingerprints[candidate["dedupe_fingerprint"]] = candidate["candidate_id"]
            candidate_id = candidate["candidate_id"]
            outcome = "CANDIDATE"
            seen_candidates.append(candidate)
            for signature in _possible_duplicate_signatures(candidate):
                possible_duplicate_index[signature].append(candidate)
            if dedupe_classification == "DISTINCT":
                seen_content.setdefault(_normalized_content_key(candidate), candidate)
            if candidate["deal_type"] == "EXPLICIT_RENT":
                counts["explicit_rent_candidates"] += 1
            if candidate["deal_type"] in {"UNCLASSIFIED", "AMBIGUOUS"}:
                counts["unclassified_transaction_candidates"] += 1
            if candidate["property_type"] is None:
                counts["unmapped_property_candidates"] += 1
            if candidate["candidate_status"] == "ELIGIBLE_HISTORICAL_SALE":
                counts["eligible_historical_sales"] += 1
            else:
                counts["needs_review_candidates"] += 1
            counts["deal_type_counts"][candidate["deal_type"]] = (
                counts["deal_type_counts"].get(candidate["deal_type"], 0) + 1
            )
            counts["deal_classification_counts"][candidate["deal_classification"]] = (
                counts["deal_classification_counts"].get(candidate["deal_classification"], 0) + 1
            )
            counts["raw_property_type_counts"][candidate["property_type_raw"]] = (
                counts["raw_property_type_counts"].get(candidate["property_type_raw"], 0) + 1
            )
        counts["dedupe_classification_counts"][dedupe_classification] = (
            counts["dedupe_classification_counts"].get(dedupe_classification, 0) + 1
        )
        source_rows.append({
            "batch_id": batch_id,
            "source_row_index": row_index,
            "source_shard": source_shard,
            "source_row_in_shard": source_row_in_shard,
            "outcome": outcome,
            "reason": (
                candidate["review_reason"]
                or ("NORMALIZED_CONTENT_MATCH" if dedupe_classification == "EXACT_DUPLICATE" else None)
            ),
            "dedupe_classification": dedupe_classification,
            "target_rank": int(target["target_rank"]),
            "candidate_id": candidate_id,
            "matched_candidate_id": matched_candidate_id,
            "raw_payload": raw_payload,
        })

    if len(candidates) > MAX_IMPORT_CANDIDATES:
        raise ValueError(f"Pilot import exceeds {MAX_IMPORT_CANDIDATES} unique candidates")
    counts["unique_candidates_to_import"] = len(candidates)
    counts["records_with_core_validation"] = (
        counts["eligible_historical_sales"] + counts["needs_review_candidates"]
    )
    counts["statistics_eligible_candidates"] = counts["eligible_historical_sales"]
    counts["matched_target_ranks"] = sorted(matched_ranks)
    return {
        "summary": counts,
        "candidates": candidates,
        "source_rows": source_rows,
        "quarantine": quarantine,
        "duplicate_pairs": duplicate_pairs,
    }


def _sample_digest(sample_path: Path) -> str:
    digest = hashlib.sha256()
    with sample_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _batch_id(metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("batch_id")
        or f"tinix-{int(metadata['sample_rows'])}-{str(metadata['revision'])[:12]}"
    )


def _validate_sample_digest(sample_path: Path, metadata: dict[str, Any]) -> str:
    digest = _sample_digest(sample_path)
    declared = metadata.get("sample_sha256")
    if declared and declared != digest:
        raise ValueError("Sample SHA-256 differs from metadata; refusing import")
    return digest


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _migrate_pilot_schema(connection: sqlite3.Connection) -> None:
    """Add E3 audit fields without replacing any E2 table or data."""
    old_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    additions = {
        "historical_candidates": {
            "batch_id": "TEXT NOT NULL DEFAULT 'E2-LEGACY'",
            "deal_classification": "TEXT NOT NULL DEFAULT 'AMBIGUOUS'",
            "dedupe_classification": "TEXT NOT NULL DEFAULT 'DISTINCT'",
            "sample_quality_flags": "TEXT NOT NULL DEFAULT '[]'",
            "source_shard": "TEXT",
            "source_row_in_shard": "INTEGER",
        },
        "historical_source_rows": {
            "batch_id": "TEXT NOT NULL DEFAULT 'E2-LEGACY'",
            "source_shard": "TEXT",
            "source_row_in_shard": "INTEGER",
            "dedupe_classification": "TEXT NOT NULL DEFAULT 'DISTINCT'",
            "matched_candidate_id": "TEXT",
            "raw_payload": "TEXT",
        },
        "historical_monthly_statistics": {
            "n_samples": "INTEGER NOT NULL DEFAULT 0",
            "mean_without_outliers": "REAL",
            "p25_price_per_m2": "REAL NOT NULL DEFAULT 0",
            "p75_price_per_m2": "REAL NOT NULL DEFAULT 0",
            "outlier_count": "INTEGER NOT NULL DEFAULT 0",
            "outlier_method": "TEXT NOT NULL DEFAULT 'NOT_AUDITED'",
            "sample_quality_flags": "TEXT NOT NULL DEFAULT '[]'",
        },
        "historical_import_runs": {
            "batch_id": "TEXT NOT NULL DEFAULT 'E2-LEGACY'",
        },
    }
    for table, columns in additions.items():
        current = _column_names(connection, table)
        for name, definition in columns.items():
            if name not in current:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    if old_version < 3:
        connection.execute(
            """UPDATE historical_candidates SET deal_classification=CASE deal_type
                 WHEN 'EXPLICIT_SALE' THEN 'SALE_CONFIRMED_BY_TEXT'
                 WHEN 'EXPLICIT_RENT' THEN 'RENT_CONFIRMED_BY_TEXT'
                 WHEN 'AMBIGUOUS' THEN 'AMBIGUOUS'
                 ELSE 'AMBIGUOUS' END
               WHERE deal_classification='AMBIGUOUS'"""
        )
        connection.execute(
            """UPDATE historical_source_rows SET dedupe_classification=CASE outcome
                 WHEN 'DUPLICATE_CONTENT' THEN 'EXACT_DUPLICATE'
                 WHEN 'QUARANTINED' THEN 'NEEDS_REVIEW'
                 ELSE 'DISTINCT' END
               WHERE dedupe_classification='DISTINCT'"""
        )
        connection.execute(
            "UPDATE historical_monthly_statistics SET n_samples=sample_count WHERE n_samples=0"
        )
        connection.execute(
            "UPDATE historical_monthly_statistics SET p25_price_per_m2=median_price_per_m2 "
            "WHERE p25_price_per_m2=0"
        )
        connection.execute(
            "UPDATE historical_monthly_statistics SET p75_price_per_m2=median_price_per_m2 "
            "WHERE p75_price_per_m2=0"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_historical_source_batch "
        "ON historical_source_rows(batch_id,source_row_index)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_historical_candidate_batch "
        "ON historical_candidates(batch_id,target_rank)"
    )
    connection.execute("PRAGMA user_version=3")


def _backup_before_e3_migration(path: Path) -> Path | None:
    if not path.is_file():
        return None
    source = sqlite3.connect(path)
    try:
        version = int(source.execute("PRAGMA user_version").fetchone()[0])
        if version >= 3 and "batch_id" in _column_names(source, "historical_source_rows"):
            return None
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"{path.stem}.pre_e3_{stamp}.sqlite3"
        suffix = 1
        while backup_path.exists():
            backup_path = backup_dir / f"{path.stem}.pre_e3_{stamp}_{suffix}.sqlite3"
            suffix += 1
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {integrity}")
        finally:
            target.close()
        return backup_path
    finally:
        source.close()


def _connect_pilot(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(SCHEMA)
    _migrate_pilot_schema(connection)
    connection.commit()
    return connection


def _assert_safe_pilot_path(pilot_db: Path, targets_db: Path) -> None:
    pilot_resolved = pilot_db.resolve()
    protected = {
        targets_db.resolve(),
        (PROJECT_ROOT / "state" / "ward_prices.sqlite3").resolve(),
        (PROJECT_ROOT / "state" / "ward_prices.demo.sqlite3").resolve(),
        (PROJECT_ROOT / "state" / "wardprice_webpilot.sqlite3").resolve(),
    }
    if pilot_resolved in protected:
        raise ValueError("Pilot DB path collides with production, demo or WebPilot database")


def _register_dataset_and_targets(
    connection: sqlite3.Connection,
    metadata: dict[str, Any],
    sample_sha256: str,
    targets: list[dict[str, Any]],
) -> None:
    connection.execute(
        """INSERT INTO historical_dataset_registry(
             dataset_id,revision,dataset_url,license_id,license_url,attribution,
             source_record_count,sample_method,sample_row_count,sample_sha256,retrieved_at,
             full_dataset_downloaded,commercial_use
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)
           ON CONFLICT(dataset_id,revision) DO UPDATE SET
             dataset_url=excluded.dataset_url,
             license_id=excluded.license_id,
             license_url=excluded.license_url,
             attribution=excluded.attribution,
             source_record_count=excluded.source_record_count,
             sample_method=excluded.sample_method,
             sample_row_count=excluded.sample_row_count,
             sample_sha256=excluded.sample_sha256,
             retrieved_at=excluded.retrieved_at,
             full_dataset_downloaded=0,
             commercial_use=0""",
        (
            DATASET_ID,
            metadata["revision"],
            DATASET_URL,
            LICENSE_ID,
            LICENSE_URL,
            "TiniX AI, vietnam-real-estates (CC BY-NC 4.0)",
            int(metadata["split_rows_reported"]),
            metadata["sample_method"],
            int(metadata["sample_rows"]),
            sample_sha256,
            metadata["retrieved_at"],
            0,
        ),
    )
    # Preserve the E2 rows and label their original provenance before assigning
    # them to the deterministic E2 batch recorded in the E3 metadata.
    previous_batch = metadata.get("previous_batch") or {}
    previous_batch_id = previous_batch.get("batch_id")
    if previous_batch_id:
        legacy_rows = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_source_rows
                   WHERE dataset_id=? AND dataset_revision=? AND batch_id='E2-LEGACY'""",
                (DATASET_ID, metadata["revision"]),
            ).fetchone()[0]
        )
        if legacy_rows:
            connection.execute(
                """UPDATE historical_source_rows SET batch_id=?
                   WHERE dataset_id=? AND dataset_revision=? AND batch_id='E2-LEGACY'""",
                (previous_batch_id, DATASET_ID, metadata["revision"]),
            )
            connection.execute(
                """UPDATE historical_candidates SET batch_id=?
                   WHERE dataset_id=? AND dataset_revision=? AND batch_id='E2-LEGACY'""",
                (previous_batch_id, DATASET_ID, metadata["revision"]),
            )
            connection.execute(
                """UPDATE historical_import_runs SET batch_id=?
                   WHERE dataset_id=? AND dataset_revision=? AND batch_id='E2-LEGACY'""",
                (previous_batch_id, DATASET_ID, metadata["revision"]),
            )
            connection.execute(
                """INSERT OR IGNORE INTO historical_dataset_batches(
                     batch_id,dataset_id,revision,sample_sha256,sample_row_count,
                     new_source_row_count,sample_method,retrieved_at,batch_metadata_json,status
                   ) VALUES(?,?,?,?,?,?,?,?,?,'COMPLETE')""",
                (
                    previous_batch_id,
                    DATASET_ID,
                    metadata["revision"],
                    previous_batch.get("sample_sha256") or hashlib.sha256(
                        previous_batch_id.encode("utf-8")
                    ).hexdigest(),
                    int(previous_batch.get("sample_rows") or legacy_rows),
                    legacy_rows,
                    previous_batch.get("sample_method") or "E2 deterministic Dataset Viewer sample",
                    previous_batch.get("retrieved_at") or metadata["retrieved_at"],
                    json.dumps(previous_batch, ensure_ascii=False, sort_keys=True),
                ),
            )

    existing = {
        int(row["target_rank"]): dict(row)
        for row in connection.execute("SELECT * FROM historical_target_registry")
    }
    expected = {int(row["target_rank"]): row for row in targets}
    if existing:
        if set(existing) != set(expected):
            raise ValueError("Pilot target registry differs from the authorized Top50 snapshot")
        for rank, target in expected.items():
            saved = existing[rank]
            for field in ("original_ward", "original_district", "original_province"):
                if saved[field] != target[field]:
                    raise ValueError(f"Pilot target rank {rank} changed in {field}; refusing overwrite")
        return
    connection.executemany(
        """INSERT INTO historical_target_registry(
             target_rank,original_ward,original_district,original_province,source_reference
           ) VALUES(?,?,?,?,?)""",
        [
            (
                int(row["target_rank"]), row["original_ward"], row["original_district"],
                row["original_province"], row.get("source_reference") or "Top50 read-only snapshot",
            )
            for row in targets
        ],
    )


def _existing_state(
    connection: sqlite3.Connection, revision: str
) -> tuple[set[int], dict[str, str], list[dict[str, Any]]]:
    known_rows = {
        int(row[0])
        for row in connection.execute(
            """SELECT source_row_index FROM historical_source_rows
               WHERE dataset_id=? AND dataset_revision=?""",
            (DATASET_ID, revision),
        )
    }
    fingerprints = {
        row["dedupe_fingerprint"]: row["candidate_id"]
        for row in connection.execute("SELECT dedupe_fingerprint,candidate_id FROM historical_candidates")
    }
    existing_candidates = [
        dict(row)
        for row in connection.execute(
            """SELECT candidate_id,dedupe_fingerprint,target_rank,title,property_type_raw,
                      price_vnd,area_m2,raw_payload,candidate_status,deal_type
               FROM historical_candidates WHERE dataset_id=? AND dataset_revision=?""",
            (DATASET_ID, revision),
        )
    ]
    return known_rows, fingerprints, existing_candidates


def _backfill_existing_source_identity(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    revision: str,
) -> int:
    """Attach stable shard/local-row provenance to E2 identities from the E3 sample."""
    missing_indexes = {
        int(row[0])
        for row in connection.execute(
            """SELECT source_row_index FROM historical_source_rows
               WHERE dataset_id=? AND dataset_revision=?
                 AND (source_shard IS NULL OR source_row_in_shard IS NULL OR raw_payload IS NULL)""",
            (DATASET_ID, revision),
        )
    }
    rows_by_index = {int(row["source_row_index"]): row for row in rows}
    stamp_rows = [
        (
            row.get("source_shard"),
            row.get("source_row_in_shard"),
            json.dumps(_json_safe(row), ensure_ascii=False, sort_keys=True, allow_nan=False),
            DATASET_ID,
            revision,
            int(row["source_row_index"]),
        )
        for index, row in rows_by_index.items()
        if index in missing_indexes
    ]
    connection.executemany(
        """UPDATE historical_source_rows
           SET source_shard=COALESCE(source_shard,?),
               source_row_in_shard=COALESCE(source_row_in_shard,?),
               raw_payload=COALESCE(raw_payload,?)
           WHERE dataset_id=? AND dataset_revision=? AND source_row_index=?""",
        stamp_rows,
    )
    connection.executemany(
        """UPDATE historical_candidates
           SET source_shard=COALESCE(source_shard,?),
               source_row_in_shard=COALESCE(source_row_in_shard,?)
           WHERE dataset_id=? AND dataset_revision=? AND first_source_row_index=?""",
        [
            (
                row.get("source_shard"),
                row.get("source_row_in_shard"),
                DATASET_ID,
                revision,
                int(row["source_row_index"]),
            )
            for index, row in rows_by_index.items()
            if index in missing_indexes
        ],
    )
    return len(stamp_rows)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot calculate a quantile from an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _sample_statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        raise ValueError("Cannot calculate statistics from an empty sample")
    p25 = _quantile(values, 0.25)
    p75 = _quantile(values, 0.75)
    spread = p75 - p25
    low_fence = p25 - 1.5 * spread
    high_fence = p75 + 1.5 * spread
    outlier_mask = (
        [value < low_fence or value > high_fence for value in values]
        if len(values) >= 4
        else [False] * len(values)
    )
    outliers = [value for value, flagged in zip(values, outlier_mask, strict=True) if flagged]
    retained = [value for value, flagged in zip(values, outlier_mask, strict=True) if not flagged]
    flags = [
        "HISTORICAL_DATASET_UNVERIFIED",
        "ASKING_PRICE",
        "NO_PER_LISTING_SOURCE_URL",
        "NON_PROBABILITY_SAMPLE",
    ]
    if len(values) < 5:
        flags.append("SMALL_SAMPLE_N_LT_5")
    elif len(values) < 10:
        flags.append("LOW_CONFIDENCE_SAMPLE_N_5_TO_9")
    if outliers:
        flags.append("TUKEY_IQR_OUTLIERS_PRESENT_DIAGNOSTIC_ONLY")
    return {
        "n_samples": len(values),
        "sample_count": len(values),
        "sample_quality_level": _sample_quality_level(len(values)),
        "mean_price_per_m2": statistics.mean(values),
        "mean_without_outliers": statistics.mean(retained)
        if outliers and len(values) >= 5 and retained
        else None,
        "median_price_per_m2": statistics.median(values),
        "p25_price_per_m2": p25,
        "p75_price_per_m2": p75,
        "min_price_per_m2": min(values),
        "max_price_per_m2": max(values),
        "outlier_count": len(outliers),
        "outlier_method": "TUKEY_1_5_IQR_DIAGNOSTIC_ONLY_N_GE_4"
        if len(values) >= 4
        else "NOT_APPLIED_SMALL_N",
        "sample_quality_flags": flags,
        "outlier_mask": outlier_mask,
    }


def _rebuild_monthly_statistics(connection: sqlite3.Connection, revision: str) -> int:
    candidates = connection.execute(
        """SELECT candidate_id,target_rank,property_type,published_date,price_per_m2,review_reason
           FROM historical_candidates
           WHERE dataset_id=? AND dataset_revision=?
             AND candidate_status='ELIGIBLE_HISTORICAL_SALE'
             AND deal_type='EXPLICIT_SALE' AND property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')
           ORDER BY target_rank,property_type,published_date""",
        (DATASET_ID, revision),
    ).fetchall()
    groups: dict[tuple[int, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in candidates:
        groups[(int(row["target_rank"]), row["property_type"], row["published_date"][:7])].append(row)
    connection.execute(
        "DELETE FROM historical_monthly_statistics WHERE dataset_id=? AND dataset_revision=?",
        (DATASET_ID, revision),
    )
    insert_rows = []
    for (rank, property_type, month), rows in groups.items():
        values = [float(row["price_per_m2"]) for row in rows]
        summary = _sample_statistics(values)
        candidate_quality_flags = {}
        for row, outlier in zip(rows, summary["outlier_mask"], strict=True):
            flags = list(summary["sample_quality_flags"])
            if "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED" in str(
                row["review_reason"] or ""
            ):
                flags.append("PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED")
            if outlier:
                flags.append("TUKEY_IQR_OUTLIER")
            candidate_quality_flags[str(row["candidate_id"])] = json.dumps(flags)
        connection.executemany(
            """UPDATE historical_candidates SET sample_quality_flags=?
               WHERE candidate_id=? AND sample_quality_flags<>?""",
            [
                (flags, candidate_id, flags)
                for candidate_id, flags in candidate_quality_flags.items()
            ],
        )
        flags_text = ";".join(summary["sample_quality_flags"])
        insert_rows.append(
            (
                DATASET_ID,
                revision,
                rank,
                property_type,
                month,
                summary["n_samples"],
                summary["n_samples"],
                summary["mean_price_per_m2"],
                summary["mean_without_outliers"],
                summary["median_price_per_m2"],
                summary["p25_price_per_m2"],
                summary["p75_price_per_m2"],
                summary["min_price_per_m2"],
                summary["max_price_per_m2"],
                summary["outlier_count"],
                summary["outlier_method"],
                flags_text,
                max(row["published_date"] for row in rows),
                flags_text,
                "historical-importer-e4-v1",
            )
        )
    connection.executemany(
        """INSERT INTO historical_monthly_statistics(
             dataset_id,dataset_revision,target_rank,property_type,published_month,n_samples,sample_count,
             mean_price_per_m2,mean_without_outliers,median_price_per_m2,p25_price_per_m2,
             p75_price_per_m2,min_price_per_m2,max_price_per_m2,outlier_count,outlier_method,
             sample_quality_flags,latest_published_date,data_quality,calculation_version
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        insert_rows,
    )
    return len(insert_rows)


def refresh_title_supported_property_mappings(pilot_db: Path) -> dict[str, Any]:
    """Apply only newly supported title-based land mapping rules to the isolated pilot."""
    if not pilot_db.is_file():
        raise FileNotFoundError(f"Historical pilot database not found: {pilot_db}")
    backup_dir = pilot_db.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / (
        f"{pilot_db.stem}.pre_e4_property_mapping_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}Z.sqlite3"
    )
    source = sqlite3.connect(pilot_db)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
    finally:
        backup.close()
        source.close()
    backup = sqlite3.connect(backup_path)
    try:
        integrity = str(backup.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        backup.close()
    if integrity != "ok":
        backup_path.unlink(missing_ok=True)
        raise sqlite3.DatabaseError(f"Pilot backup integrity check failed: {integrity}")
    connection = sqlite3.connect(pilot_db)
    connection.row_factory = sqlite3.Row
    try:
        dataset = connection.execute(
            "SELECT dataset_id,revision FROM historical_dataset_registry "
            "ORDER BY retrieved_at DESC LIMIT 1"
        ).fetchone()
        if dataset is None:
            raise ValueError("Historical pilot database has no registered dataset")
        revision = str(dataset["revision"])
        connection.execute("BEGIN IMMEDIATE")
        before = connection.execute(
            """SELECT property_type,COUNT(*) AS n FROM historical_candidates
               WHERE dataset_id=? AND dataset_revision=? GROUP BY property_type""",
            (dataset["dataset_id"], revision),
        ).fetchall()
        rows = connection.execute(
            """SELECT candidate_id,property_type_raw,title,deal_type,dedupe_classification,
                      property_type,review_reason,candidate_status
               FROM historical_candidates WHERE dataset_id=? AND dataset_revision=?
                 AND (property_type IS NULL OR instr(COALESCE(review_reason,''),
                      'PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED')>0)""",
            (dataset["dataset_id"], revision),
        ).fetchall()
        changed = 0
        reclassified = 0
        reverted_to_unknown = 0
        for row in rows:
            mapped_type, type_review = _property_type(row["property_type_raw"], row["title"])
            has_title_mapping_marker = (
                "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED"
                in str(row["review_reason"] or "")
            )
            if (
                mapped_type == row["property_type"]
                and has_title_mapping_marker
                and type_review == "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED"
            ):
                continue
            if mapped_type is None and not has_title_mapping_marker:
                continue
            reasons = [
                item
                for item in str(row["review_reason"] or "").split(";")
                if item
                and item
                not in {
                    "LAND_UNSPECIFIED",
                    "PROPERTY_TYPE_UNMAPPED",
                    "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED",
                }
            ]
            if mapped_type is None:
                type_review = type_review or "LAND_UNSPECIFIED"
            if type_review and type_review not in reasons:
                reasons.append(type_review)
            status = (
                "ELIGIBLE_HISTORICAL_SALE"
                if row["deal_type"] == "EXPLICIT_SALE"
                and mapped_type in {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
                and row["dedupe_classification"] not in {"POSSIBLE_DUPLICATE", "NEEDS_REVIEW"}
                else "NEEDS_REVIEW"
            )
            connection.execute(
                """UPDATE historical_candidates SET property_type=?,candidate_status=?,review_reason=?
                   WHERE candidate_id=?""",
                (mapped_type, status, ";".join(reasons) or None, row["candidate_id"]),
            )
            changed += 1
            if mapped_type is None:
                reverted_to_unknown += 1
            else:
                reclassified += 1
        statistic_groups = _rebuild_monthly_statistics(connection, revision)
        after = connection.execute(
            """SELECT property_type,COUNT(*) AS n FROM historical_candidates
               WHERE dataset_id=? AND dataset_revision=? GROUP BY property_type""",
            (dataset["dataset_id"], revision),
        ).fetchall()
        eligible = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_candidates
                   WHERE dataset_id=? AND dataset_revision=?
                     AND candidate_status='ELIGIBLE_HISTORICAL_SALE'
                     AND deal_type='EXPLICIT_SALE'
                     AND property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')
                     AND dedupe_classification NOT IN ('POSSIBLE_DUPLICATE','NEEDS_REVIEW')""",
                (dataset["dataset_id"], revision),
            ).fetchone()[0]
        )
        connection.commit()
        return {
            "dataset_id": dataset["dataset_id"],
            "revision": revision,
            "backup_path": str(backup_path),
            "backup_integrity_check": integrity,
            "candidates_updated": changed,
            "candidates_reclassified": reclassified,
            "candidates_reverted_to_unknown": reverted_to_unknown,
            "property_type_counts_before": {
                str(row["property_type"] or "UNKNOWN"): int(row["n"]) for row in before
            },
            "property_type_counts_after": {
                str(row["property_type"] or "UNKNOWN"): int(row["n"]) for row in after
            },
            "statistics_eligible_count_after": eligible,
            "monthly_statistics_groups_after": statistic_groups,
            "production_database_written": False,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def dry_run(
    sample_path: Path, metadata_path: Path, targets_db: Path, pilot_db: Path
) -> dict[str, Any]:
    _assert_safe_pilot_path(pilot_db, targets_db)
    metadata = load_metadata(metadata_path)
    rows = load_sample(sample_path)
    sample_sha256 = _validate_sample_digest(sample_path, metadata)
    targets = read_targets(targets_db)
    known_rows: set[int] = set()
    known_fingerprints: dict[str, str] = {}
    existing_candidates: list[dict[str, Any]] = []
    existing_source_count = 0
    if pilot_db.is_file():
        connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            has_tables = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='historical_candidates'"
            ).fetchone()
            if has_tables:
                known_rows, known_fingerprints, existing_candidates = _existing_state(
                    connection, metadata["revision"]
                )
                existing_source_count = int(
                    connection.execute(
                        """SELECT COUNT(*) FROM historical_source_rows
                           WHERE dataset_id=? AND dataset_revision=?""",
                        (DATASET_ID, metadata["revision"]),
                    ).fetchone()[0]
                )
        finally:
            connection.close()
    planned = plan_import(
        rows,
        targets,
        metadata,
        known_source_rows=known_rows,
        candidates_by_fingerprint=known_fingerprints,
        existing_candidates=existing_candidates,
    )
    if existing_source_count + len(planned["source_rows"]) > MAX_SOURCE_ROWS:
        raise ValueError(
            f"Import would exceed the {MAX_SOURCE_ROWS:,}-source-row cap for this dataset revision"
        )
    return {
        "mode": "DRY_RUN",
        "dataset_id": DATASET_ID,
        "revision": metadata["revision"],
        "license": LICENSE_ID,
        "targets": len(targets),
        "pilot_database": str(pilot_db),
        "pilot_database_written": False,
        "network_attempted": False,
        "full_dataset_downloaded": False,
        "batch_id": _batch_id(metadata),
        "sample_sha256": sample_sha256,
        "source_rows_already_processed": len(known_rows),
        "new_source_rows_to_process": len(planned["source_rows"]),
        "summary": planned["summary"],
    }


def _quality_report_paths(metadata: dict[str, Any], output_dir: Path | None) -> tuple[Path, Path]:
    batch_id = _batch_id(metadata)
    safe_batch = "".join(character if character.isalnum() or character in "-_" else "_" for character in batch_id)
    root = output_dir or PROJECT_ROOT / "outputs" / "historical_quality"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe_batch}_quality_audit.json", root / f"{safe_batch}_title_review.csv"


def audit_sample_quality(
    sample_path: Path,
    metadata_path: Path,
    targets_db: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Create an offline data-quality report and an unlabeled title-review packet."""
    metadata = load_metadata(metadata_path)
    rows = load_sample(sample_path)
    sample_sha256 = _validate_sample_digest(sample_path, metadata)
    targets = read_targets(targets_db)
    target_by_key = _target_index(targets)
    planned = plan_import(rows, targets, metadata)
    top50_by_source = {
        int(row["source_row_index"]): row for row in planned["source_rows"]
    }

    missing_price = invalid_price = missing_area = invalid_area = 0
    missing_title = invalid_date = missing_date = 0
    valid_price_area: list[float] = []
    province_counts: Counter[str] = Counter()
    month_counts: Counter[str] = Counter()
    shard_counts: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()
    raw_property_counts: Counter[str] = Counter()
    normalized_type_counts: Counter[str] = Counter()
    matched_rows = 0
    outside_top50 = 0
    for row in rows:
        price_value = row.get("price")
        area_value = row.get("area")
        if price_value is None or price_value == "":
            missing_price += 1
        elif _positive_number(price_value) is None:
            invalid_price += 1
        if area_value is None or area_value == "":
            missing_area += 1
        elif _positive_number(area_value) is None:
            invalid_area += 1
        price = _positive_number(price_value)
        area = _positive_number(area_value)
        if price and area:
            valid_price_area.append(price / area)
        title = str(row.get("name") or "").strip()
        if not title:
            missing_title += 1
        classification_counts[_deal_classification(title)] += 1
        raw_property = str(row.get("property_type_name") or "<NULL>")
        raw_property_counts[raw_property] += 1
        mapped_type, type_review = _property_type(row.get("property_type_name"))
        normalized_type_counts[mapped_type or type_review or "PROPERTY_TYPE_UNMAPPED"] += 1
        published = _published_date(row.get("published_at"))
        if row.get("published_at") is None or row.get("published_at") == "":
            missing_date += 1
        elif published is None:
            invalid_date += 1
        month_counts[published[:7] if published else ("<NULL>" if not row.get("published_at") else "<INVALID>")] += 1
        province_counts[str(row.get("province_name") or "<NULL>")] += 1
        shard_counts[str(row.get("source_shard") or "<UNKNOWN>")] += 1
        target = target_by_key.get(
            _geography_key(row.get("province_name"), row.get("district_name"), row.get("ward_name"))
        )
        if target:
            matched_rows += 1
        else:
            outside_top50 += 1

    if len(valid_price_area) >= 4:
        p25 = _quantile(valid_price_area, 0.25)
        p75 = _quantile(valid_price_area, 0.75)
        iqr = p75 - p25
        lower_fence = p25 - 1.5 * iqr
        upper_fence = p75 + 1.5 * iqr
        extreme_count = sum(value < lower_fence or value > upper_fence for value in valid_price_area)
    else:
        p25 = p75 = lower_fence = upper_fence = None
        extreme_count = 0

    eligible_titles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        title = str(row.get("name") or "").strip()
        classification = _deal_classification(title)
        source_index = int(row["source_row_index"])
        source_result = top50_by_source.get(source_index, {})
        eligible_titles[classification].append(
            {
                "source_row_index": source_index,
                "source_shard": row.get("source_shard") or "",
                "target_rank": source_result.get("target_rank") or "",
                "province_name": row.get("province_name") or "",
                "district_name": row.get("district_name") or "",
                "ward_name": row.get("ward_name") or "",
                "title": title,
                "predicted_classification": classification,
                "human_label": "",
                "review_notes": "",
            }
        )
    seeded_groups = {
        key: sorted(
            group,
            key=lambda item: hashlib.sha256(
                f"{metadata['revision']}:{item['source_row_index']}".encode()
            ).hexdigest(),
        )
        for key, group in eligible_titles.items()
    }
    review_rows: list[dict[str, Any]] = []
    review_classes = sorted(seeded_groups)
    position = 0
    while len(review_rows) < min(100, len(rows)):
        added = False
        for classification in review_classes:
            group = seeded_groups[classification]
            if position < len(group):
                review_rows.append(group[position])
                added = True
                if len(review_rows) >= 100:
                    break
        if not added:
            break
        position += 1

    report_path, review_path = _quality_report_paths(metadata, output_dir)
    review_fields = (
        "source_row_index", "source_shard", "target_rank", "province_name", "district_name",
        "ward_name", "title", "predicted_classification", "human_label", "review_notes",
    )
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review_rows)

    report = {
        "created_at": _now(),
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "attribution": "TiniX AI, vietnam-real-estates",
        "license": LICENSE_ID,
        "license_url": LICENSE_URL,
        "revision": metadata["revision"],
        "batch_id": _batch_id(metadata),
        "sample_sha256": sample_sha256,
        "sample_source_rows": len(rows),
        "source_record_count": int(metadata["split_rows_reported"]),
        "sample_method": metadata["sample_method"],
        "sampling_is_statistically_representative": False,
        "parquet_shard_counts": dict(sorted(shard_counts.items())),
        "province_counts": dict(sorted(province_counts.items())),
        "published_month_counts": dict(sorted(month_counts.items())),
        "quality_counts": {
            "missing_price": missing_price,
            "invalid_price": invalid_price,
            "missing_area": missing_area,
            "invalid_area": invalid_area,
            "missing_title": missing_title,
            "missing_published_date": missing_date,
            "invalid_published_date": invalid_date,
            "valid_price_area": len(valid_price_area),
            "matched_top50_rows": matched_rows,
            "outside_top50_rows": outside_top50,
            "unique_candidates_in_whitelist": planned["summary"]["unique_candidates_to_import"],
            "statistics_eligible_sales": planned["summary"]["statistics_eligible_candidates"],
            "exact_duplicate_source_rows": planned["summary"]["duplicate_content_rows"],
            "possible_duplicate_rows": planned["summary"]["possible_duplicate_rows"],
            "quarantined_invalid_core_fields": planned["summary"]["quarantined_invalid_core_fields"],
            "extreme_global_iqr_price_per_m2_rows_diagnostic_only": extreme_count,
        },
        "global_iqr_diagnostic": {
            "q25_price_per_m2": p25,
            "q75_price_per_m2": p75,
            "lower_fence": lower_fence,
            "upper_fence": upper_fence,
            "method": "Tukey 1.5xIQR on sampled rows; diagnostic only, no row removed",
        },
        "sale_rent_classification": dict(sorted(classification_counts.items())),
        "raw_property_type_distribution": dict(sorted(raw_property_counts.items())),
        "mapped_property_type_distribution": dict(sorted(normalized_type_counts.items())),
        "source_provenance": {
            "source_listing_url_field_present": bool(metadata.get("listing_detail_url_field_present")),
            "listing_id_field_present": bool(metadata.get("listing_id_field_present")),
            "transaction_type_field_present": bool(metadata.get("transaction_type_field_present")),
            "dataset_listing_source_verified": False,
            "per_listing_url_available": False,
            "full_dataset_monthly_baseline_available": False,
        },
        "ground_truth_labels_available": False,
        "precision_recall_confusion_matrix": None,
        "manual_title_review_packet": {
            "path": str(review_path),
            "row_count": len(review_rows),
            "human_label_column_blank": True,
        },
        "plan_summary": planned["summary"],
        "report_file": str(report_path),
        "network_attempted": False,
        "production_database_written": False,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _persist_quality_audit_if_available(
    connection: sqlite3.Connection,
    metadata: dict[str, Any],
    sample_sha256: str,
) -> str | None:
    report_path, _ = _quality_report_paths(metadata, None)
    if not report_path.is_file():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("sample_sha256") != sample_sha256:
        raise ValueError("Quality audit report digest does not match the import sample")
    metrics = report.get("quality_counts") or {}
    connection.execute(
        """INSERT OR IGNORE INTO historical_quality_audits(
             audit_id,dataset_id,revision,batch_id,sample_sha256,created_at,report_path,
             summary_json,metrics_json
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            f"{_batch_id(metadata)}:{sample_sha256[:16]}",
            DATASET_ID,
            metadata["revision"],
            _batch_id(metadata),
            sample_sha256,
            report.get("created_at") or _now(),
            str(report_path),
            json.dumps(
                {
                    "attribution": report.get("attribution"),
                    "license": report.get("license"),
                    "dataset_url": report.get("dataset_url"),
                    "revision": report.get("revision"),
                    "sample_method": report.get("sample_method"),
                    "sample_distribution": {
                        "province_counts": report.get("province_counts"),
                        "published_month_counts": report.get("published_month_counts"),
                        "parquet_shard_counts": report.get("parquet_shard_counts"),
                    },
                    "sale_rent_classification": report.get("sale_rent_classification"),
                    "raw_property_type_distribution": report.get("raw_property_type_distribution"),
                    "source_provenance": report.get("source_provenance"),
                    "sampling_is_statistically_representative": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(
                {
                    **metrics,
                    "global_iqr_diagnostic": report.get("global_iqr_diagnostic"),
                    "ground_truth_labels_available": report.get("ground_truth_labels_available"),
                    "precision_recall_confusion_matrix": report.get("precision_recall_confusion_matrix"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    return str(report_path)


def import_batch(
    sample_path: Path,
    metadata_path: Path,
    targets_db: Path,
    pilot_db: Path,
) -> dict[str, Any]:
    _assert_safe_pilot_path(pilot_db, targets_db)
    metadata = load_metadata(metadata_path)
    rows = load_sample(sample_path)
    targets = read_targets(targets_db)
    sample_sha256 = _validate_sample_digest(sample_path, metadata)
    backup_path = _backup_before_e3_migration(pilot_db)
    connection = _connect_pilot(pilot_db)
    run_id = str(uuid.uuid4())
    try:
        connection.execute("BEGIN IMMEDIATE")
        _register_dataset_and_targets(connection, metadata, sample_sha256, targets)
        backfilled_source_rows = _backfill_existing_source_identity(
            connection, rows, metadata["revision"]
        )
        known_rows, known_fingerprints, existing_candidates = _existing_state(
            connection, metadata["revision"]
        )
        planned = plan_import(
            rows,
            targets,
            metadata,
            known_source_rows=known_rows,
            candidates_by_fingerprint=known_fingerprints,
            existing_candidates=existing_candidates,
        )
        existing_source_count = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_source_rows
                   WHERE dataset_id=? AND dataset_revision=?""",
                (DATASET_ID, metadata["revision"]),
            ).fetchone()[0]
        )
        if existing_source_count + len(planned["source_rows"]) > MAX_SOURCE_ROWS:
            raise ValueError(
                f"Import would exceed the {MAX_SOURCE_ROWS:,}-source-row cap for this dataset revision"
            )
        stamp = _now()
        batch_id = _batch_id(metadata)
        candidate_columns = (
            "candidate_id", "dedupe_fingerprint", "dataset_id", "dataset_revision", "batch_id",
            "first_source_row_index", "target_rank", "original_ward", "original_district",
            "original_province", "title", "property_type_raw", "property_type", "deal_type",
            "deal_classification", "dedupe_classification", "price_vnd", "area_m2",
            "price_per_m2", "published_date", "evidence_status", "candidate_status",
            "review_reason", "sample_quality_flags", "source_dataset_url", "source_row_index",
            "source_shard", "source_row_in_shard", "raw_payload",
        )
        candidate_values = [
            tuple(
                json.dumps(candidate[key], ensure_ascii=False)
                if key == "sample_quality_flags"
                else candidate[key]
                for key in candidate_columns
            ) + (stamp,)
            for candidate in planned["candidates"]
        ]
        connection.executemany(
            """INSERT OR IGNORE INTO historical_candidates(
                 candidate_id,dedupe_fingerprint,dataset_id,dataset_revision,batch_id,
                 first_source_row_index,target_rank,original_ward,original_district,original_province,
                 title,property_type_raw,property_type,deal_type,deal_classification,
                 dedupe_classification,price_vnd,area_m2,price_per_m2,published_date,evidence_status,
                 candidate_status,review_reason,sample_quality_flags,source_dataset_url,source_row_index,
                 source_shard,source_row_in_shard,raw_payload,imported_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            candidate_values,
        )
        connection.executemany(
            """INSERT OR IGNORE INTO historical_source_rows(
                 dataset_id,dataset_revision,batch_id,source_row_index,source_shard,
                 source_row_in_shard,outcome,reason,dedupe_classification,target_rank,candidate_id,
                 matched_candidate_id,raw_payload,processed_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    DATASET_ID,
                    metadata["revision"],
                    source["batch_id"],
                    source["source_row_index"],
                    source["source_shard"],
                    source["source_row_in_shard"],
                    source["outcome"],
                    source["reason"],
                    source["dedupe_classification"],
                    source["target_rank"],
                    source["candidate_id"],
                    source["matched_candidate_id"],
                    source["raw_payload"],
                    stamp,
                )
                for source in planned["source_rows"]
            ],
        )
        connection.executemany(
            """INSERT OR IGNORE INTO historical_duplicate_pairs(
                 dataset_id,dataset_revision,batch_id,candidate_id_a,candidate_id_b,
                 classification,reason,audited_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            [
                (
                    DATASET_ID,
                    metadata["revision"],
                    pair["batch_id"],
                    pair["candidate_id_a"],
                    pair["candidate_id_b"],
                    pair["classification"],
                    pair["reason"],
                    stamp,
                )
                for pair in planned["duplicate_pairs"]
            ],
        )
        for pair in planned["duplicate_pairs"]:
            for candidate_id in (pair["candidate_id_a"], pair["candidate_id_b"]):
                connection.execute(
                    """UPDATE historical_candidates
                       SET candidate_status='NEEDS_REVIEW',
                           dedupe_classification='POSSIBLE_DUPLICATE',
                           review_reason=CASE
                             WHEN instr(COALESCE(review_reason,''),'POSSIBLE_DUPLICATE_PRICE_OR_AREA_CHANGED')>0
                               THEN review_reason
                             ELSE trim(COALESCE(review_reason,'') || ';POSSIBLE_DUPLICATE_PRICE_OR_AREA_CHANGED',';')
                           END
                       WHERE candidate_id=?""",
                    (candidate_id,),
                )
        connection.executemany(
            """INSERT OR IGNORE INTO historical_quarantine(
                 dataset_id,dataset_revision,source_row_index,reason,raw_payload,quarantined_at
               ) VALUES(?,?,?,?,?,?)""",
            [
                (
                    DATASET_ID, metadata["revision"], item["source_row_index"], item["reason"],
                    item["raw_payload"], stamp,
                )
                for item in planned["quarantine"]
            ],
        )
        connection.executemany(
            """INSERT OR IGNORE INTO historical_observations(
                 candidate_id,dataset_id,dataset_revision,published_date,observed_price_vnd,
                 observed_area_m2,price_per_m2,imported_at
               ) SELECT candidate_id,dataset_id,dataset_revision,published_date,price_vnd,
                        area_m2,price_per_m2,? FROM historical_candidates WHERE candidate_id=?""",
            [
                (stamp, source["candidate_id"])
                for source in planned["source_rows"]
                if source["candidate_id"] is not None
            ],
        )
        if planned["source_rows"]:
            stat_groups = _rebuild_monthly_statistics(connection, metadata["revision"])
        else:
            stat_groups = int(
                connection.execute(
                    """SELECT COUNT(*) FROM historical_monthly_statistics
                       WHERE dataset_id=? AND dataset_revision=?""",
                    (DATASET_ID, metadata["revision"]),
                ).fetchone()[0]
            )
        connection.execute(
            """INSERT OR IGNORE INTO historical_dataset_batches(
                 batch_id,dataset_id,revision,sample_sha256,sample_row_count,new_source_row_count,
                 sample_method,retrieved_at,batch_metadata_json,status
               ) VALUES(?,?,?,?,?,?,?,?,?,'COMPLETE')""",
            (
                batch_id,
                DATASET_ID,
                metadata["revision"],
                sample_sha256,
                int(metadata["sample_rows"]),
                len(planned["source_rows"]),
                metadata["sample_method"],
                metadata["retrieved_at"],
                json.dumps(
                    {
                        key: metadata.get(key)
                        for key in (
                            "sample_method", "sampling_strata", "sample_distribution",
                            "parquet_manifest", "parquet_footer_bytes_fetched", "previous_batch",
                            "sample_offsets", "batch_new_rows", "reused_e2_rows",
                        )
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
        registered_batch = connection.execute(
            "SELECT sample_sha256 FROM historical_dataset_batches WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if registered_batch is None or registered_batch["sample_sha256"] != sample_sha256:
            raise ValueError("Batch id already exists with a different sample digest")
        quality_report_path = _persist_quality_audit_if_available(
            connection, metadata, sample_sha256
        )
        summary = dict(planned["summary"])
        summary.update(
            {
                "candidate_count_after_import": int(
                    connection.execute("SELECT COUNT(*) FROM historical_candidates").fetchone()[0]
                ),
                "observation_count_after_import": int(
                    connection.execute("SELECT COUNT(*) FROM historical_observations").fetchone()[0]
                ),
                "monthly_statistic_groups_after_import": stat_groups,
                "source_rows_after_import": int(
                    connection.execute(
                        """SELECT COUNT(*) FROM historical_source_rows
                           WHERE dataset_id=? AND dataset_revision=?""",
                        (DATASET_ID, metadata["revision"]),
                    ).fetchone()[0]
                ),
                "existing_source_rows_backfilled_with_identity": backfilled_source_rows,
                "duplicate_pair_count_after_import": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM historical_duplicate_pairs WHERE dataset_id=? AND dataset_revision=?",
                        (DATASET_ID, metadata["revision"]),
                    ).fetchone()[0]
                ),
                "quality_report_path": quality_report_path,
            }
        )
        connection.execute(
            """INSERT INTO historical_import_runs(
                 run_id,dataset_id,dataset_revision,batch_id,sample_sha256,started_at,input_rows,summary_json,
                 network_attempted,production_database_written
               ) VALUES(?,?,?,?,?,?,?,?,0,0)""",
            (
                run_id,
                DATASET_ID,
                metadata["revision"],
                batch_id,
                sample_sha256,
                stamp,
                len(rows),
                json.dumps(summary, sort_keys=True),
            ),
        )
        connection.commit()
        return {
            "mode": "PILOT_IMPORT",
            "run_id": run_id,
            "dataset_id": DATASET_ID,
            "revision": metadata["revision"],
            "license": LICENSE_ID,
            "pilot_database": str(pilot_db),
            "backup_database": str(backup_path) if backup_path else None,
            "batch_id": batch_id,
            "production_database_written": False,
            "network_attempted": False,
            "summary": summary,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


class HistoricalDatasetImporter:
    """Import bounded historical samples into a dedicated pilot database."""

    def __init__(
        self,
        targets_db: Path = DEFAULT_TARGETS_DB,
        pilot_db: Path = DEFAULT_PILOT_DB,
    ) -> None:
        self.targets_db = Path(targets_db)
        self.pilot_db = Path(pilot_db)

    def dry_run(
        self,
        sample_path: Path = DEFAULT_SAMPLE,
        metadata_path: Path = DEFAULT_METADATA,
    ) -> dict[str, Any]:
        return dry_run(sample_path, metadata_path, self.targets_db, self.pilot_db)

    def import_batch(
        self,
        sample_path: Path = DEFAULT_SAMPLE,
        metadata_path: Path = DEFAULT_METADATA,
    ) -> dict[str, Any]:
        return import_batch(sample_path, metadata_path, self.targets_db, self.pilot_db)


def pilot_overview(pilot_db: Path) -> dict[str, Any]:
    if not pilot_db.is_file():
        raise FileNotFoundError(f"Historical pilot database not found: {pilot_db}")
    connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dataset = connection.execute(
            "SELECT * FROM historical_dataset_registry ORDER BY retrieved_at DESC LIMIT 1"
        ).fetchone()
        if dataset is None:
            return {"status": "EMPTY", "candidate_count": 0}
        summary = connection.execute(
            """SELECT COUNT(*) AS candidate_count,
                      COUNT(DISTINCT target_rank) AS covered_targets,
                      MIN(published_date) AS first_published_date,
                      MAX(published_date) AS last_published_date,
                      SUM(CASE WHEN candidate_status='ELIGIBLE_HISTORICAL_SALE'
                                AND deal_type='EXPLICIT_SALE'
                                AND dedupe_classification NOT IN ('POSSIBLE_DUPLICATE','NEEDS_REVIEW')
                               THEN 1 ELSE 0 END)
                        AS statistics_eligible_count
               FROM historical_candidates WHERE dataset_id=? AND dataset_revision=?""",
            (dataset["dataset_id"], dataset["revision"]),
        ).fetchone()
        output = dict(dataset)
        output.update(dict(summary))
        output["source_rows_processed"] = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_source_rows
                   WHERE dataset_id=? AND dataset_revision=?""",
                (dataset["dataset_id"], dataset["revision"]),
            ).fetchone()[0]
        )
        output["batch_count"] = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_dataset_batches
                   WHERE dataset_id=? AND revision=?""",
                (dataset["dataset_id"], dataset["revision"]),
            ).fetchone()[0]
        )
        output["last_imported_at"] = connection.execute(
            """SELECT MAX(started_at) FROM historical_import_runs
               WHERE dataset_id=? AND dataset_revision=?""",
            (dataset["dataset_id"], dataset["revision"]),
        ).fetchone()[0]
        output["deal_classification_counts"] = {
            str(row["deal_classification"]): int(row["row_count"])
        for row in connection.execute(
                """SELECT deal_classification,COUNT(*) AS row_count FROM historical_candidates
                   WHERE dataset_id=? AND dataset_revision=? GROUP BY deal_classification""",
                (dataset["dataset_id"], dataset["revision"]),
            )
        }
        output["property_type_counts"] = {
            str(row["property_type"] or row["property_type_raw"] or "UNMAPPED"): int(row["row_count"])
            for row in connection.execute(
                """SELECT property_type,property_type_raw,COUNT(*) AS row_count
                   FROM historical_candidates WHERE dataset_id=? AND dataset_revision=?
                   GROUP BY property_type,property_type_raw""",
                (dataset["dataset_id"], dataset["revision"]),
            )
        }
        province_counts: Counter[str] = Counter()
        month_counts: Counter[str] = Counter()
        shard_counts: Counter[str] = Counter()
        for source in connection.execute(
            """SELECT raw_payload,source_shard FROM historical_source_rows
               WHERE dataset_id=? AND dataset_revision=?""",
            (dataset["dataset_id"], dataset["revision"]),
        ):
            raw = json.loads(source["raw_payload"] or "{}")
            province_counts[str(raw.get("province_name") or "<NULL>")] += 1
            published = _published_date(raw.get("published_at"))
            month_counts[
                published[:7]
                if published
                else ("<NULL>" if not raw.get("published_at") else "<INVALID>")
            ] += 1
            shard_counts[str(source["source_shard"] or "<UNKNOWN>")] += 1
        output["sample_distribution"] = {
            "province_counts": dict(sorted(province_counts.items())),
            "published_month_counts": dict(sorted(month_counts.items())),
            "parquet_shard_counts": dict(sorted(shard_counts.items())),
        }
        quality_audit = connection.execute(
            """SELECT report_path,metrics_json FROM historical_quality_audits
               WHERE dataset_id=? AND revision=? ORDER BY created_at DESC LIMIT 1""",
            (dataset["dataset_id"], dataset["revision"]),
        ).fetchone()
        output["quality_audit"] = (
            {"report_path": quality_audit["report_path"], **json.loads(quality_audit["metrics_json"])}
            if quality_audit
            else None
        )
        output["status"] = "READY"
        output["research_only"] = True
        output["current_verified"] = False
        output["daily_new"] = False
        output["ai_context_enabled"] = False
        return output
    finally:
        connection.close()


def pilot_targets(pilot_db: Path) -> list[dict[str, Any]]:
    if not pilot_db.is_file():
        raise FileNotFoundError(f"Historical pilot database not found: {pilot_db}")
    connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """WITH latest AS (
                   SELECT dataset_id,revision FROM historical_dataset_registry
                   WHERE dataset_id=? ORDER BY retrieved_at DESC LIMIT 1
               )
               SELECT t.target_rank,t.original_ward,t.original_district,t.original_province,
                      COUNT(c.candidate_id) AS candidate_count,
                       COALESCE(SUM(CASE WHEN c.candidate_status='ELIGIBLE_HISTORICAL_SALE'
                                        AND c.deal_type='EXPLICIT_SALE'
                                        AND c.dedupe_classification NOT IN ('POSSIBLE_DUPLICATE','NEEDS_REVIEW')
                                        THEN 1 ELSE 0 END),0) AS statistics_eligible_count,
                       COALESCE(SUM(CASE WHEN c.deal_classification='SALE_CONFIRMED_BY_TEXT'
                                        THEN 1 ELSE 0 END),0) AS sale_title_count,
                       COALESCE(SUM(CASE WHEN c.deal_classification='RENT_CONFIRMED_BY_TEXT'
                                        THEN 1 ELSE 0 END),0) AS rent_title_count,
                       COALESCE(SUM(CASE WHEN c.deal_classification='AMBIGUOUS'
                                        THEN 1 ELSE 0 END),0) AS ambiguous_title_count,
                       COALESCE(SUM(CASE WHEN c.deal_classification='CONFLICT'
                                        THEN 1 ELSE 0 END),0) AS conflict_title_count
               FROM historical_target_registry t LEFT JOIN historical_candidates c
                 ON c.target_rank=t.target_rank
                AND c.dataset_id=(SELECT dataset_id FROM latest)
                AND c.dataset_revision=(SELECT revision FROM latest)
               GROUP BY t.target_rank,t.original_ward,t.original_district,t.original_province
               ORDER BY t.target_rank"""
            , (DATASET_ID,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def pilot_lookup(pilot_db: Path, target_rank: int, property_type: str | None = None) -> dict[str, Any]:
    if not pilot_db.is_file():
        raise FileNotFoundError(f"Historical pilot database not found: {pilot_db}")
    if not 1 <= target_rank <= 50:
        raise ValueError("target_rank must be between 1 and 50")
    if property_type not in {None, "DAT_O", "NHA_RIENG", "CHUNG_CU"}:
        raise ValueError("Unsupported historical property_type")
    connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dataset = connection.execute(
            "SELECT dataset_id,revision,sample_row_count FROM historical_dataset_registry "
            "ORDER BY retrieved_at DESC LIMIT 1"
        ).fetchone()
        if dataset is None:
            raise ValueError("Historical pilot database has no registered dataset")
        target = connection.execute(
            "SELECT * FROM historical_target_registry WHERE target_rank=?", (target_rank,)
        ).fetchone()
        if target is None:
            raise ValueError("target_rank is absent from the pilot Top50 registry")
        where = "dataset_id=? AND dataset_revision=? AND target_rank=?"
        params: list[Any] = [dataset["dataset_id"], dataset["revision"], target_rank]
        if property_type:
            where += " AND property_type=?"
            params.append(property_type)
        stats_where = (
            "dataset_id=? AND dataset_revision=? AND target_rank=? "
            "AND candidate_status='ELIGIBLE_HISTORICAL_SALE'"
        )
        stats_params: list[Any] = [dataset["dataset_id"], dataset["revision"], target_rank]
        if property_type:
            stats_where += " AND property_type=?"
            stats_params.append(property_type)
        stat_rows = connection.execute(
            f"""SELECT property_type,price_per_m2 FROM historical_candidates WHERE {stats_where}
                AND deal_type='EXPLICIT_SALE'
                AND dedupe_classification NOT IN ('POSSIBLE_DUPLICATE','NEEDS_REVIEW')""",
            stats_params,
        ).fetchall()
        grouped_values: dict[str, list[float]] = defaultdict(list)
        for row in stat_rows:
            grouped_values[row["property_type"]].append(float(row["price_per_m2"]))
        statistics_by_property_type = []
        for property_type_key, type_values in sorted(grouped_values.items()):
            summary = _sample_statistics(type_values)
            summary.pop("outlier_mask")
            statistics_by_property_type.append({"property_type": property_type_key, **summary})
        selected_statistics = next(
            (
                item
                for item in statistics_by_property_type
                if item["property_type"] == property_type
            ),
            None,
        ) if property_type else None
        candidate_count = int(
            connection.execute(
                f"SELECT COUNT(*) FROM historical_candidates WHERE {where}", params
            ).fetchone()[0]
        )
        candidates = [
            dict(row)
            for row in connection.execute(
                f"""SELECT candidate_id,target_rank,title,property_type_raw,property_type,deal_type,
                           deal_classification,dedupe_classification,price_vnd,area_m2,
                           price_per_m2,published_date,evidence_status,candidate_status,
                           review_reason,sample_quality_flags,source_dataset_url,source_row_index,
                           source_shard,source_row_in_shard,batch_id
                    FROM historical_candidates WHERE {where}
                    ORDER BY published_date DESC,source_row_index LIMIT 500""",
                params,
            )
        ]
        monthly = [
            dict(row)
            for row in connection.execute(
                """SELECT property_type,published_month,n_samples,sample_count,mean_price_per_m2,
                          mean_without_outliers,median_price_per_m2,p25_price_per_m2,
                          p75_price_per_m2,min_price_per_m2,max_price_per_m2,outlier_count,
                          outlier_method,sample_quality_flags,latest_published_date,data_quality
                   FROM historical_monthly_statistics
                   WHERE dataset_id=? AND dataset_revision=? AND target_rank=?
                     AND (? IS NULL OR property_type=?)
                   ORDER BY published_month,property_type""",
                (
                    dataset["dataset_id"],dataset["revision"],target_rank,
                    property_type,property_type,
                ),
            )
        ]
        for row in monthly:
            row["sample_quality_level"] = _sample_quality_level(int(row["sample_count"]))
        return {
            "target": dict(target),
            "property_type": property_type,
            "sample_row_count": int(dataset["sample_row_count"]),
            "candidate_count": candidate_count,
            "statistics_eligible_count": (
                selected_statistics["sample_count"]
                if selected_statistics
                else (
                    0
                    if property_type
                    else sum(item["sample_count"] for item in statistics_by_property_type)
                )
            ),
            "mean_price_per_m2": (
                selected_statistics["mean_price_per_m2"] if selected_statistics else None
            ),
            "median_price_per_m2": (
                selected_statistics["median_price_per_m2"] if selected_statistics else None
            ),
            "min_price_per_m2": (
                selected_statistics["min_price_per_m2"] if selected_statistics else None
            ),
            "max_price_per_m2": (
                selected_statistics["max_price_per_m2"] if selected_statistics else None
            ),
            "p25_price_per_m2": (
                selected_statistics["p25_price_per_m2"] if selected_statistics else None
            ),
            "p75_price_per_m2": (
                selected_statistics["p75_price_per_m2"] if selected_statistics else None
            ),
            "mean_without_outliers": (
                selected_statistics["mean_without_outliers"] if selected_statistics else None
            ),
            "sample_quality_flags": (
                selected_statistics["sample_quality_flags"] if selected_statistics else []
            ),
            "statistics_by_property_type": statistics_by_property_type,
            "data_quality": "HISTORICAL_DATASET_SAMPLE; ASKING_PRICE; NOT_CURRENT_VERIFIED",
            "candidates": candidates,
            "monthly_statistics": monthly,
        }
    finally:
        connection.close()


def _json_print(value: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("dry-run", "import", "quality-audit"):
        command = subparsers.add_parser(name)
        command.add_argument("--targets-db", type=Path, default=DEFAULT_TARGETS_DB)
        command.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
        command.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
        if name != "quality-audit":
            command.add_argument("--pilot-db", type=Path, default=DEFAULT_PILOT_DB)
        else:
            command.add_argument("--output-dir", type=Path)
    overview = subparsers.add_parser("overview")
    overview.add_argument("--pilot-db", type=Path, default=DEFAULT_PILOT_DB)
    args = parser.parse_args()
    try:
        if args.command == "dry-run":
            result = HistoricalDatasetImporter(args.targets_db, args.pilot_db).dry_run(
                args.sample, args.metadata
            )
        elif args.command == "import":
            result = HistoricalDatasetImporter(args.targets_db, args.pilot_db).import_batch(
                args.sample, args.metadata
            )
        elif args.command == "quality-audit":
            result = audit_sample_quality(
                args.sample, args.metadata, args.targets_db, args.output_dir
            )
        else:
            result = pilot_overview(args.pilot_db)
        _json_print(result)
    except (OSError, sqlite3.Error, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()
