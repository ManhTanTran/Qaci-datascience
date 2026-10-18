"""Isolated storage, statistics, and offline scheduler for synthetic demo fixtures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, flag

DEMO_DB = PROJECT_ROOT / "state" / "ward_prices.demo.sqlite3"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "demo500"
PROPERTY_TYPES = ("DAT_O", "NHA_RIENG", "CHUNG_CU")
MAX_DEMO_LISTINGS = 500

DEMO_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS demo_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_wards (
    target_rank INTEGER PRIMARY KEY CHECK(target_rank BETWEEN 1 AND 50),
    ward_code TEXT NOT NULL UNIQUE,
    ward_name TEXT NOT NULL,
    district TEXT NOT NULL,
    province TEXT NOT NULL,
    admin_source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_listings (
    listing_id TEXT PRIMARY KEY,
    identity_fingerprint TEXT NOT NULL UNIQUE,
    target_rank INTEGER NOT NULL REFERENCES demo_wards(target_rank),
    ward_code TEXT NOT NULL,
    ward_name TEXT NOT NULL,
    district TEXT NOT NULL,
    province TEXT NOT NULL,
    property_type TEXT NOT NULL CHECK(property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')),
    title TEXT NOT NULL,
    address TEXT NOT NULL,
    price_vnd REAL NOT NULL CHECK(price_vnd > 0),
    area_m2 REAL NOT NULL CHECK(area_m2 > 0),
    price_per_m2 REAL NOT NULL CHECK(price_per_m2 > 0),
    source_website TEXT NOT NULL CHECK(source_website='DEMO_SYNTHETIC'),
    source_url TEXT,
    source_domain TEXT,
    listed_date TEXT,
    collected_at TEXT NOT NULL,
    evidence_status TEXT NOT NULL CHECK(evidence_status='UNVERIFIED'),
    raw_payload TEXT NOT NULL,
    first_import_run_id TEXT NOT NULL,
    last_import_run_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_demo_listing_ward_type
    ON demo_listings(target_rank, property_type, active);
CREATE TABLE IF NOT EXISTS demo_daily_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL REFERENCES demo_listings(listing_id),
    target_rank INTEGER NOT NULL,
    observation_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    price_vnd REAL NOT NULL,
    area_m2 REAL NOT NULL,
    price_per_m2 REAL NOT NULL,
    evidence_status TEXT NOT NULL CHECK(evidence_status='UNVERIFIED'),
    raw_payload TEXT NOT NULL,
    import_run_id TEXT NOT NULL,
    UNIQUE(listing_id, observation_date)
);
CREATE INDEX IF NOT EXISTS ix_demo_observation_rank_date
    ON demo_daily_observations(target_rank, observation_date DESC);
CREATE TABLE IF NOT EXISTS demo_import_runs (
    run_id TEXT PRIMARY KEY,
    source_batch TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    received INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    observations_added INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE TABLE IF NOT EXISTS demo_statistics (
    target_rank INTEGER NOT NULL REFERENCES demo_wards(target_rank),
    ward_name TEXT NOT NULL,
    district TEXT NOT NULL,
    province TEXT NOT NULL,
    property_type TEXT NOT NULL,
    listing_count INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    mean_price_per_m2 REAL NOT NULL,
    median_price_per_m2 REAL NOT NULL,
    min_price_per_m2 REAL NOT NULL,
    max_price_per_m2 REAL NOT NULL,
    data_quality TEXT NOT NULL CHECK(data_quality='DEMO_SYNTHETIC'),
    last_updated TEXT NOT NULL,
    PRIMARY KEY(target_rank, property_type)
);
CREATE TABLE IF NOT EXISTS demo_scheduler_runs (
    schedule_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_group_index INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    network_called INTEGER NOT NULL DEFAULT 0 CHECK(network_called=0)
);
"""


class DemoImportError(ValueError):
    """Raised when demo data fails its mode, schema, or whitelist checks."""


def demo_mode_enabled() -> bool:
    """Read the explicit demo-mode switch, supporting both documented names."""
    return flag("WARDPRICE_DEMO_MODE", flag("DEMO_MODE", False))


def require_demo_mode() -> None:
    if not demo_mode_enabled():
        raise DemoImportError(
            "Synthetic records require WARDPRICE_DEMO_MODE=1 (or DEMO_MODE=1)."
        )


def _assert_not_production(path: Path) -> None:
    production_db = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
    if path.resolve() == production_db.resolve():
        raise DemoImportError("The demo importer refuses the production database path.")


def open_demo_db(path: Path | str = DEMO_DB) -> sqlite3.Connection:
    """Open the demo-only database; never migrate or write production storage."""
    require_demo_mode()
    db_path = Path(path)
    _assert_not_production(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript(DEMO_SCHEMA)
    listing_columns = {row[1] for row in db.execute("PRAGMA table_info(demo_listings)")}
    if "source_domain" not in listing_columns:
        db.execute("ALTER TABLE demo_listings ADD COLUMN source_domain TEXT")
    statistic_columns = {row[1] for row in db.execute("PRAGMA table_info(demo_statistics)")}
    if "sample_count" not in statistic_columns:
        db.execute("ALTER TABLE demo_statistics ADD COLUMN sample_count INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE demo_statistics SET sample_count=listing_count")
    db.execute(
        "INSERT OR IGNORE INTO demo_meta(key,value) VALUES('mode','DEMO MODE — SYNTHETIC DATA')"
    )
    db.commit()
    return db


@contextmanager
def demo_database(path: Path | str = DEMO_DB) -> Iterator[sqlite3.Connection]:
    db = open_demo_db(path)
    try:
        yield db
    finally:
        db.close()


def _load_targets(registry_path: Path = PROJECT_ROOT / "config" / "wards.csv") -> dict[int, dict[str, str]]:
    with registry_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 50:
        raise DemoImportError(f"Expected 50 configured targets; found {len(rows)}.")
    targets: dict[int, dict[str, str]] = {}
    for row in rows:
        rank = int(row["source_rank"])
        if rank in targets or not 1 <= rank <= 50:
            raise DemoImportError(f"Invalid or duplicate target rank in registry: {rank}.")
        targets[rank] = row
    if set(targets) != set(range(1, 51)):
        raise DemoImportError("Configured target ranks must be exactly 1 through 50.")
    return targets


def _seed_targets(db: sqlite3.Connection, registry_path: Path) -> dict[int, dict[str, str]]:
    targets = _load_targets(registry_path)
    for rank, target in targets.items():
        values = (
            rank,
            target["ward_code"],
            target["ward_name"],
            target["district"],
            target["province"],
            target.get("admin_source", "config/wards.csv"),
        )
        existing = db.execute(
            "SELECT ward_code,ward_name,district,province FROM demo_wards WHERE target_rank=?",
            (rank,),
        ).fetchone()
        if existing and tuple(existing) != values[1:5]:
            raise DemoImportError(f"Demo target rank {rank} conflicts with its stored registry.")
        db.execute(
            """INSERT OR IGNORE INTO demo_wards
               (target_rank,ward_code,ward_name,district,province,admin_source)
               VALUES(?,?,?,?,?,?)""",
            values,
        )
    return targets


def _normalise_identity(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


def _fingerprint(row: dict[str, Any]) -> str:
    identity = "|".join(
        (
            str(row["target_rank"]),
            row["property_type"],
            _normalise_identity(row["title"]),
            _normalise_identity(row["address"]),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _read_payload(source: Path | str | dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    if isinstance(source, dict):
        payload = source
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        source_name = str(payload.get("group_id") or "inline-demo-payload")
        source_bytes = raw.encode("utf-8")
    else:
        source_path = Path(source)
        source_bytes = source_path.read_bytes()
        payload = json.loads(source_bytes.decode("utf-8-sig"))
        source_name = source_path.name
        raw = source_bytes.decode("utf-8-sig")
    if not isinstance(payload, dict) or not isinstance(payload.get("listings"), list):
        raise DemoImportError("Demo JSON must be an object with a listings array.")
    return payload, source_name, hashlib.sha256(source_bytes).hexdigest()


def _validate_rows(
    payload: dict[str, Any], targets: dict[int, dict[str, str]]
) -> list[dict[str, Any]]:
    rows = payload["listings"]
    if not rows:
        raise DemoImportError("Demo batch contains no listings.")
    if payload.get("web_search_used") is not False:
        raise DemoImportError("Synthetic fixtures must explicitly declare web_search_used=false.")
    if payload.get("actual_collected") is not None and int(payload["actual_collected"]) != len(rows):
        raise DemoImportError("Batch actual_collected does not match its listings array.")

    validated = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise DemoImportError(f"Listing #{index + 1} is not a JSON object.")
        try:
            rank = int(item["target_rank"])
            target = targets[rank]
            property_type = str(item["property_type"])
            title = str(item["title"]).strip()
            address = str(item["address"]).strip()
            price_vnd = float(item["price_vnd"])
            area_m2 = float(item["area_m2"])
            collected_at = str(item["collected_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DemoImportError(f"Listing #{index + 1} is missing valid required fields.") from exc
        if item.get("original_ward") != target["ward_name"]:
            raise DemoImportError(f"Rank {rank} does not match the configured ward whitelist.")
        if item.get("original_district") != target["district"]:
            raise DemoImportError(f"Rank {rank} does not match the configured legacy district.")
        if item.get("original_province") != target["province"]:
            raise DemoImportError(f"Rank {rank} does not match the configured province.")
        if property_type not in PROPERTY_TYPES:
            raise DemoImportError(f"Listing #{index + 1} has unsupported property_type.")
        if item.get("source_website") != "DEMO_SYNTHETIC":
            raise DemoImportError(f"Listing #{index + 1} is not marked DEMO_SYNTHETIC.")
        if item.get("source_url") is not None:
            raise DemoImportError(f"Synthetic listing #{index + 1} must not claim a source URL.")
        if item.get("evidence_status") != "UNVERIFIED":
            raise DemoImportError(f"Synthetic listing #{index + 1} must remain UNVERIFIED.")
        if not title or not address or "demo" not in (title + " " + address).casefold():
            raise DemoImportError(f"Listing #{index + 1} is missing a visible synthetic label.")
        if not math.isfinite(price_vnd) or not math.isfinite(area_m2) or price_vnd <= 0 or area_m2 <= 0:
            raise DemoImportError(f"Listing #{index + 1} must have positive finite price and area.")
        try:
            datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DemoImportError(f"Listing #{index + 1} has an invalid collected_at date.") from exc
        row = dict(item)
        row.update(
            {
                "target_rank": rank,
                "ward_code": target["ward_code"],
                "ward_name": target["ward_name"],
                "district": target["district"],
                "province": target["province"],
                "property_type": property_type,
                "title": title,
                "address": address,
                "price_vnd": price_vnd,
                "area_m2": area_m2,
                "price_per_m2": price_vnd / area_m2,
                "collected_at": collected_at,
                "identity_fingerprint": _fingerprint(
                    {
                        "target_rank": rank,
                        "property_type": property_type,
                        "title": title,
                        "address": address,
                    }
                ),
                "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
            }
        )
        validated.append(row)
    return validated


def recompute_demo_statistics(db: sqlite3.Connection) -> int:
    """Calculate synthetic-only summaries in Python from unique listing rows."""
    groups = db.execute(
        """SELECT target_rank,ward_name,district,province,property_type,
                  price_per_m2,collected_at
           FROM demo_listings WHERE active=1 ORDER BY target_rank,property_type"""
    ).fetchall()
    by_key: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in groups:
        by_key.setdefault((row["target_rank"], row["property_type"]), []).append(row)
    db.execute("DELETE FROM demo_statistics")
    for (rank, property_type), records in by_key.items():
        values = [float(record["price_per_m2"]) for record in records]
        db.execute(
            """INSERT INTO demo_statistics
               (target_rank,ward_name,district,province,property_type,listing_count,
                sample_count,mean_price_per_m2,median_price_per_m2,min_price_per_m2,max_price_per_m2,
                data_quality,last_updated)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rank,
                records[0]["ward_name"],
                records[0]["district"],
                records[0]["province"],
                property_type,
                len(values),
                len(values),
                round(statistics.mean(values), 2),
                round(statistics.median(values), 2),
                round(min(values), 2),
                round(max(values), 2),
                "DEMO_SYNTHETIC",
                max(str(record["collected_at"])[:10] for record in records),
            ),
        )
    return len(by_key)


def import_demo_batch(
    db: sqlite3.Connection,
    source: Path | str | dict[str, Any],
    *,
    registry_path: Path = PROJECT_ROOT / "config" / "wards.csv",
) -> dict[str, Any]:
    """Validate and transactionally import one synthetic batch into demo tables."""
    require_demo_mode()
    payload, source_name, source_sha = _read_payload(source)
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        targets = _load_targets(registry_path)
        rows = _validate_rows(payload, targets)
    except Exception as exc:
        db.execute(
            """INSERT INTO demo_import_runs
               (run_id,source_batch,source_sha256,started_at,finished_at,status,received,rejected,error)
               VALUES(?,?,?,?,?,'REJECTED',?,?,?)""",
            (run_id, source_name, source_sha, started_at, started_at,
             len(payload.get("listings", [])), len(payload.get("listings", [])), str(exc)[:1000]),
        )
        db.commit()
        raise

    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            """INSERT INTO demo_import_runs
               (run_id,source_batch,source_sha256,started_at,status,received)
               VALUES(?,?,?,?,'RUNNING',?)""",
            (run_id, source_name, source_sha, started_at, len(rows)),
        )
        targets = _seed_targets(db, registry_path)
        current_count = int(db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0])
        existing_fingerprints = {
            row[0] for row in db.execute("SELECT identity_fingerprint FROM demo_listings")
        }
        new_fingerprints = {
            row["identity_fingerprint"]
            for row in rows
            if row["identity_fingerprint"] not in existing_fingerprints
        }
        if current_count + len(new_fingerprints) > MAX_DEMO_LISTINGS:
            raise DemoImportError(
                f"The demo listing cap is {MAX_DEMO_LISTINGS}; this batch would exceed it."
            )

        inserted = updated = duplicates = observations_added = 0
        for row in rows:
            fingerprint = row["identity_fingerprint"]
            listing_id = "DEMO-" + fingerprint[:24].upper()
            existing = db.execute(
                "SELECT price_vnd,area_m2,price_per_m2 FROM demo_listings "
                "WHERE identity_fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if existing is None:
                db.execute(
                    """INSERT INTO demo_listings
                       (listing_id,identity_fingerprint,target_rank,ward_code,ward_name,district,
                        province,property_type,title,address,price_vnd,area_m2,price_per_m2,
                        source_website,source_url,source_domain,listed_date,collected_at,evidence_status,
                        raw_payload,first_import_run_id,last_import_run_id)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'UNVERIFIED',?,?,?)""",
                    (
                        listing_id,
                        fingerprint,
                        row["target_rank"],
                        row["ward_code"],
                        row["ward_name"],
                        row["district"],
                        row["province"],
                        row["property_type"],
                        row["title"],
                        row["address"],
                        row["price_vnd"],
                        row["area_m2"],
                        row["price_per_m2"],
                        "DEMO_SYNTHETIC",
                        None,
                        None,
                        row.get("published_at"),
                        row["collected_at"],
                        row["raw_payload"],
                        run_id,
                        run_id,
                    ),
                )
                inserted += 1
            elif (
                float(existing["price_vnd"]) == row["price_vnd"]
                and float(existing["area_m2"]) == row["area_m2"]
            ):
                duplicates += 1
                db.execute(
                    "UPDATE demo_listings SET last_import_run_id=?,collected_at=? WHERE listing_id=?",
                    (run_id, row["collected_at"], listing_id),
                )
            else:
                updated += 1
                db.execute(
                    """UPDATE demo_listings SET price_vnd=?,area_m2=?,price_per_m2=?,
                              collected_at=?,raw_payload=?,last_import_run_id=?
                       WHERE listing_id=?""",
                    (
                        row["price_vnd"],
                        row["area_m2"],
                        row["price_per_m2"],
                        row["collected_at"],
                        row["raw_payload"],
                        run_id,
                        listing_id,
                    ),
                )

            observation_date = row["collected_at"][:10]
            prior_observation = db.execute(
                """SELECT id FROM demo_daily_observations
                   WHERE listing_id=? AND observation_date=?""",
                (listing_id, observation_date),
            ).fetchone()
            if prior_observation is None:
                db.execute(
                    """INSERT INTO demo_daily_observations
                       (listing_id,target_rank,observation_date,observed_at,price_vnd,area_m2,
                        price_per_m2,evidence_status,raw_payload,import_run_id)
                       VALUES(?,?,?,?,?,?,?,'UNVERIFIED',?,?)""",
                    (
                        listing_id,
                        row["target_rank"],
                        observation_date,
                        row["collected_at"],
                        row["price_vnd"],
                        row["area_m2"],
                        row["price_per_m2"],
                        row["raw_payload"],
                        run_id,
                    ),
                )
                observations_added += 1
            else:
                db.execute(
                    """UPDATE demo_daily_observations SET observed_at=?,price_vnd=?,area_m2=?,
                              price_per_m2=?,raw_payload=?,import_run_id=? WHERE id=?""",
                    (
                        row["collected_at"],
                        row["price_vnd"],
                        row["area_m2"],
                        row["price_per_m2"],
                        row["raw_payload"],
                        run_id,
                        prior_observation["id"],
                    ),
                )

        statistic_groups = recompute_demo_statistics(db)
        finished_at = datetime.now(timezone.utc).isoformat()
        db.execute(
            """UPDATE demo_import_runs SET finished_at=?,status='SUCCEEDED',inserted=?,updated=?,
                      duplicates=?,observations_added=? WHERE run_id=?""",
            (finished_at, inserted, updated, duplicates, observations_added, run_id),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            """INSERT OR REPLACE INTO demo_import_runs
               (run_id,source_batch,source_sha256,started_at,finished_at,status,received,
                rejected,error)
               VALUES(?,?,?,?,?,'REJECTED',?,?,?)""",
            (run_id, source_name, source_sha, started_at,
             datetime.now(timezone.utc).isoformat(), len(rows), len(rows), str(exc)[:1000]),
        )
        db.commit()
        raise
    return {
        "run_id": run_id,
        "source_batch": source_name,
        "received": len(rows),
        "inserted": inserted,
        "updated": updated,
        "duplicates_exact": duplicates,
        "observations_added": observations_added,
        "statistics_groups": statistic_groups,
        "tracked_listings": int(db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0]),
        "network_called": False,
        "database": "demo-only",
    }


def demo_coverage(db: sqlite3.Connection) -> dict[str, Any]:
    targets = int(db.execute("SELECT COUNT(*) FROM demo_wards").fetchone()[0])
    listings = int(db.execute("SELECT COUNT(*) FROM demo_listings WHERE active=1").fetchone()[0])
    observations = int(db.execute("SELECT COUNT(*) FROM demo_daily_observations").fetchone()[0])
    wards_with_data = int(
        db.execute("SELECT COUNT(DISTINCT target_rank) FROM demo_listings WHERE active=1").fetchone()[0]
    )
    types = {
        row["property_type"]: row["count"]
        for row in db.execute(
            "SELECT property_type,COUNT(*) AS count FROM demo_listings "
            "WHERE active=1 GROUP BY property_type"
        )
    }
    return {
        "mode": "DEMO MODE — SYNTHETIC DATA",
        "database_scope": "isolated demo database",
        "target_count": targets,
        "wards_with_data": wards_with_data,
        "listings": listings,
        "listing_cap": MAX_DEMO_LISTINGS,
        "daily_observations": observations,
        "statistics_groups": int(db.execute("SELECT COUNT(*) FROM demo_statistics").fetchone()[0]),
        "property_type_counts": {kind: int(types.get(kind, 0)) for kind in PROPERTY_TYPES},
        "network_called": False,
    }


def demo_wards(db: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute("SELECT * FROM demo_wards ORDER BY target_rank")]


def demo_lookup(
    db: sqlite3.Connection, query: str, *, property_type: str | None = None
) -> dict[str, Any]:
    if property_type and property_type not in PROPERTY_TYPES:
        raise ValueError("property_type must be DAT_O, NHA_RIENG, or CHUNG_CU.")
    normal_query = _normalise_identity(query.strip())
    if not normal_query:
        return {"status": "NOT_FOUND", "query": query, "targets": []}
    all_wards = demo_wards(db)
    matches = [
        ward
        for ward in all_wards
        if normal_query in _normalise_identity(ward["ward_name"])
        or normal_query in _normalise_identity(ward["district"])
        or normal_query in _normalise_identity(ward["province"])
        or normal_query == ward["ward_code"].casefold()
    ]
    if not matches:
        return {"status": "NOT_IN_TOP50", "query": query, "targets": []}
    targets = []
    for ward in matches:
        params: list[Any] = [ward["target_rank"]]
        type_filter = ""
        if property_type:
            type_filter = " AND property_type=?"
            params.append(property_type)
        statistics_rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM demo_statistics WHERE target_rank=?" + type_filter +
                " ORDER BY CASE property_type WHEN 'DAT_O' THEN 1 WHEN 'NHA_RIENG' THEN 2 ELSE 3 END",
                params,
            )
        ]
        listings = [
            dict(row)
            for row in db.execute(
                "SELECT listing_id,property_type,title,address,price_vnd,area_m2,price_per_m2,"
                "source_website,source_url,evidence_status,collected_at "
                "FROM demo_listings WHERE target_rank=? AND active=1" + type_filter +
                " ORDER BY property_type,listing_id",
                params,
            )
        ]
        targets.append(
            {
                **ward,
                "statistics": statistics_rows,
                "listings": listings,
                "status": "FOUND" if statistics_rows else "NO_PRICE_DATA",
            }
        )
    found = any(target["statistics"] for target in targets)
    return {
        "status": "FOUND" if found else "NO_PRICE_DATA",
        "query": query,
        "property_type": property_type,
        "synthetic": True,
        "targets": targets,
    }


def demo_history(
    db: sqlite3.Connection, target_rank: int, *, property_type: str | None = None
) -> dict[str, Any]:
    if property_type and property_type not in PROPERTY_TYPES:
        raise ValueError("property_type must be DAT_O, NHA_RIENG, or CHUNG_CU.")
    ward = db.execute("SELECT * FROM demo_wards WHERE target_rank=?", (target_rank,)).fetchone()
    if ward is None:
        return {"status": "NOT_IN_TOP50", "target_rank": target_rank, "observations": []}
    params: list[Any] = [target_rank]
    type_filter = ""
    if property_type:
        type_filter = " AND l.property_type=?"
        params.append(property_type)
    rows = [
        dict(row)
        for row in db.execute(
            """SELECT o.listing_id,o.observation_date,o.observed_at,l.property_type,
                      l.title,o.price_vnd,o.area_m2,o.price_per_m2,o.evidence_status,
                      o.import_run_id
               FROM demo_daily_observations o JOIN demo_listings l USING(listing_id)
               WHERE o.target_rank=?""" + type_filter +
            " ORDER BY o.observation_date DESC,o.id DESC",
            params,
        )
    ]
    return {
        "status": "FOUND" if rows else "NO_OBSERVATIONS",
        "target": dict(ward),
        "synthetic": True,
        "observations": rows,
    }


def validate_demo_database(
    db: sqlite3.Connection,
    expected_path: Path = FIXTURE_DIR / "expected_statistics_DEMO_ONLY.json",
) -> dict[str, Any]:
    coverage = demo_coverage(db)
    integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity != "ok":
        raise AssertionError(f"SQLite integrity_check failed: {integrity}")
    if coverage["target_count"] != 50 or coverage["listings"] != 500:
        raise AssertionError(f"Demo database totals do not match fixture: {coverage}")
    per_target = db.execute(
        "SELECT target_rank,COUNT(*) AS count FROM demo_listings GROUP BY target_rank"
    ).fetchall()
    if len(per_target) != 50 or any(row["count"] != 10 for row in per_target):
        raise AssertionError("Expected exactly 10 synthetic listings for each of 50 targets.")
    if coverage["daily_observations"] < 500:
        raise AssertionError("Every unique demo listing must have a daily observation.")
    if coverage["property_type_counts"] != {"DAT_O": 200, "NHA_RIENG": 200, "CHUNG_CU": 100}:
        raise AssertionError(f"Property type totals differ from fixture: {coverage['property_type_counts']}")
    unverified = int(
        db.execute("SELECT COUNT(*) FROM demo_listings WHERE evidence_status!='UNVERIFIED'").fetchone()[0]
    )
    if unverified:
        raise AssertionError(f"Expected only UNVERIFIED demo rows; got {unverified}.")
    mapping_mismatches = int(
        db.execute(
            """SELECT COUNT(*) FROM demo_listings l JOIN demo_wards w USING(target_rank)
               WHERE l.ward_code!=w.ward_code OR l.ward_name!=w.ward_name
                  OR l.district!=w.district OR l.province!=w.province"""
        ).fetchone()[0]
    )
    price_mismatches = int(
        db.execute(
            "SELECT COUNT(*) FROM demo_listings WHERE ABS(price_per_m2-price_vnd/area_m2)>0.01"
        ).fetchone()[0]
    )
    lineage_missing = int(
        db.execute(
            """SELECT COUNT(*) FROM demo_listings l
               WHERE NOT EXISTS(SELECT 1 FROM demo_import_runs r WHERE r.run_id=l.first_import_run_id)
                  OR NOT EXISTS(SELECT 1 FROM demo_import_runs r WHERE r.run_id=l.last_import_run_id)"""
        ).fetchone()[0]
    )
    if mapping_mismatches or price_mismatches or lineage_missing:
        raise AssertionError(
            "Demo data integrity mismatch: "
            f"target_mapping={mapping_mismatches}, price_per_m2={price_mismatches}, "
            f"lineage={lineage_missing}."
        )
    foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise AssertionError(f"Demo database has foreign-key failures: {len(foreign_key_errors)}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))["statistics"]
    mismatches = []
    for item in expected:
        actual = db.execute(
            "SELECT listing_count,sample_count,mean_price_per_m2,median_price_per_m2 "
            "FROM demo_statistics "
            "WHERE target_rank=? AND property_type=?",
            (item["target_rank"], item["property_type"]),
        ).fetchone()
        if (
            actual is None
            or actual["listing_count"] != item["sample_count"]
            or actual["sample_count"] != item["sample_count"]
            or not math.isclose(actual["mean_price_per_m2"], item["demo_mean_price_per_m2"], abs_tol=0.01)
            or not math.isclose(actual["median_price_per_m2"], item["demo_median_price_per_m2"], abs_tol=0.01)
        ):
            mismatches.append(
                {"target_rank": item["target_rank"], "property_type": item["property_type"]}
            )
    if len(expected) != 150 or mismatches:
        raise AssertionError(f"Expected synthetic statistics mismatch: {mismatches[:10]}")
    return {
        "status": "PASS",
        **coverage,
        "sqlite_integrity": integrity,
        "target_mapping_mismatches": mapping_mismatches,
        "price_calculation_mismatches": price_mismatches,
        "lineage_missing": lineage_missing,
        "foreign_key_errors": len(foreign_key_errors),
        "statistics_expected_groups": len(expected),
    }


def run_demo_scheduler(
    db_path: Path | str = DEMO_DB,
    *,
    fixture_dir: Path = FIXTURE_DIR,
    schedule_id: str,
    fail_after_batch: int | None = None,
) -> dict[str, Any]:
    """Run the ten local mock batches with a persisted cursor and no network."""
    require_demo_mode()
    if not schedule_id.strip():
        raise ValueError("schedule_id must not be empty.")
    if fail_after_batch is not None and not 1 <= fail_after_batch <= 10:
        raise ValueError("fail_after_batch must be between 1 and 10.")
    with demo_database(db_path) as db:
        scheduler = db.execute(
            "SELECT * FROM demo_scheduler_runs WHERE schedule_id=?", (schedule_id,)
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if scheduler is None:
            db.execute(
                "INSERT INTO demo_scheduler_runs(schedule_id,status,started_at) VALUES(?,'RUNNING',?)",
                (schedule_id, now),
            )
            last_group = 0
        else:
            last_group = int(scheduler["last_group_index"])
            if scheduler["status"] == "SUCCEEDED" and last_group == 10:
                return {
                    "schedule_id": schedule_id,
                    "status": "SUCCEEDED",
                    "resumed_from_group": 10,
                    "groups_processed": 0,
                    "network_called": False,
                    "coverage": demo_coverage(db),
                }
            db.execute(
                "UPDATE demo_scheduler_runs SET status='RUNNING',finished_at=NULL,error=NULL "
                "WHERE schedule_id=?",
                (schedule_id,),
            )
        db.commit()
        start_group = last_group + 1
        processed = 0
        for group_number in range(start_group, 11):
            source = fixture_dir / "batches" / f"demo_group_{group_number:02d}_50.json"
            import_demo_batch(db, source)
            processed += 1
            db.execute(
                "UPDATE demo_scheduler_runs SET last_group_index=? WHERE schedule_id=?",
                (group_number, schedule_id),
            )
            db.commit()
            if fail_after_batch == group_number:
                message = f"Injected offline failure after batch {group_number}."
                db.execute(
                    "UPDATE demo_scheduler_runs SET status='FAILED',finished_at=?,error=? "
                    "WHERE schedule_id=?",
                    (datetime.now(timezone.utc).isoformat(), message, schedule_id),
                )
                db.commit()
                return {
                    "schedule_id": schedule_id,
                    "status": "FAILED",
                    "last_group_index": group_number,
                    "groups_processed": processed,
                    "error": message,
                    "network_called": False,
                    "coverage": demo_coverage(db),
                }
        db.execute(
            "UPDATE demo_scheduler_runs SET status='SUCCEEDED',last_group_index=10,finished_at=? "
            "WHERE schedule_id=?",
            (datetime.now(timezone.utc).isoformat(), schedule_id),
        )
        db.commit()
        return {
            "schedule_id": schedule_id,
            "status": "SUCCEEDED",
            "resumed_from_group": last_group,
            "groups_processed": processed,
            "network_called": False,
            "coverage": demo_coverage(db),
        }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Offline-only synthetic WardPriceDaily demo tools")
    parser.add_argument("command", choices=("init", "import-all", "replay", "verify", "status", "lookup", "scheduler-mock"))
    parser.add_argument("--db", type=Path, default=DEMO_DB)
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--property-type", choices=PROPERTY_TYPES)
    parser.add_argument("--schedule-id", default="demo-day-01")
    parser.add_argument("--fail-after-batch", type=int)
    args = parser.parse_args(argv)
    if args.command == "verify":
        with demo_database(args.db) as db:
            _print_json(validate_demo_database(db))
        return 0
    if args.command == "init":
        with demo_database(args.db):
            pass
        _print_json({"status": "INITIALIZED", "database": str(args.db), "network_called": False})
        return 0
    if args.command == "import-all":
        results = []
        with demo_database(args.db) as db:
            for group_number in range(1, 11):
                source = args.fixture_dir / "batches" / f"demo_group_{group_number:02d}_50.json"
                results.append(import_demo_batch(db, source))
            result = demo_coverage(db)
        _print_json({"imports": results, "coverage": result})
        return 0
    if args.command == "replay":
        if args.file is None:
            parser.error("replay requires --file <fixture JSON>")
        with demo_database(args.db) as db:
            result = import_demo_batch(db, args.file)
        _print_json(result)
        return 0
    if args.command == "scheduler-mock":
        _print_json(
            run_demo_scheduler(
                args.db,
                fixture_dir=args.fixture_dir,
                schedule_id=args.schedule_id,
                fail_after_batch=args.fail_after_batch,
            )
        )
        return 0
    if args.command == "lookup":
        with demo_database(args.db) as db:
            result = demo_lookup(db, args.query, property_type=args.property_type)
        _print_json(result)
        return 0
    if args.command == "status":
        with demo_database(args.db) as db:
            _print_json(demo_coverage(db))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
