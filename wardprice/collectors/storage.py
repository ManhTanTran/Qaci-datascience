"""SQLite schema and persistence for collector audit and unverified candidates."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .models import CollectionTarget

COLLECTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_settings (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    global_live_enabled INTEGER NOT NULL DEFAULT 0,
    auto_ingest_verified INTEGER NOT NULL DEFAULT 0,
    user_agent TEXT NOT NULL DEFAULT 'WardPriceDailyCollector/0.2',
    global_daily_request_budget INTEGER NOT NULL DEFAULT 500,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_sources (
    source_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    robots_url TEXT NOT NULL,
    terms_url TEXT NOT NULL DEFAULT '',
    robots_status TEXT NOT NULL DEFAULT 'UNCHECKED',
    policy_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
    permission_reference TEXT NOT NULL DEFAULT '',
    policy_checked_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    auto_ingest_verified INTEGER NOT NULL DEFAULT 0,
    crawl_delay_seconds REAL NOT NULL DEFAULT 5,
    daily_request_budget INTEGER NOT NULL DEFAULT 100,
    search_url_template TEXT NOT NULL DEFAULT '',
    detail_path_regex TEXT NOT NULL DEFAULT '',
    listing_id_regex TEXT NOT NULL DEFAULT '',
    policy_note TEXT NOT NULL DEFAULT '',
    cooldown_until TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('DRY_RUN','LIVE')),
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    selection_json TEXT NOT NULL DEFAULT '[]',
    total_targets INTEGER NOT NULL DEFAULT 0,
    processed_targets INTEGER NOT NULL DEFAULT 0,
    requests_made INTEGER NOT NULL DEFAULT 0,
    candidates_found INTEGER NOT NULL DEFAULT 0,
    source_verified INTEGER NOT NULL DEFAULT 0,
    new_listings INTEGER NOT NULL DEFAULT 0,
    refreshed_listings INTEGER NOT NULL DEFAULT 0,
    expired_listings INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    geo_mismatches INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    quarantined INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_collection_runs_date ON collection_runs(run_date, started_at DESC);
CREATE TABLE IF NOT EXISTS collection_target_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    quarantine_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error TEXT,
    retry_after TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(run_id, source_id, target_rank),
    FOREIGN KEY(run_id) REFERENCES collection_runs(run_id),
    FOREIGN KEY(source_id) REFERENCES collection_sources(source_id)
);
CREATE INDEX IF NOT EXISTS ix_collection_target_rank ON collection_target_attempts(target_rank, started_at DESC);
CREATE TABLE IF NOT EXISTS collection_http_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_rank INTEGER,
    requested_url TEXT NOT NULL,
    purpose TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    http_status INTEGER,
    outcome TEXT NOT NULL,
    retry_after TEXT,
    error_code TEXT,
    UNIQUE(run_id, source_id, requested_url, purpose, requested_at),
    FOREIGN KEY(run_id) REFERENCES collection_runs(run_id),
    FOREIGN KEY(source_id) REFERENCES collection_sources(source_id)
);
CREATE INDEX IF NOT EXISTS ix_collection_http_run ON collection_http_attempts(run_id, requested_at);
CREATE TABLE IF NOT EXISTS collection_discovered_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_url_type TEXT NOT NULL CHECK(source_url_type IN ('CATEGORY','DIRECT_LISTING','UNKNOWN')),
    discovered_at TEXT NOT NULL,
    fetched_at TEXT,
    http_status INTEGER,
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    skip_reason TEXT,
    UNIQUE(run_id, source_id, canonical_url),
    FOREIGN KEY(run_id) REFERENCES collection_runs(run_id),
    FOREIGN KEY(source_id) REFERENCES collection_sources(source_id)
);
CREATE INDEX IF NOT EXISTS ix_collection_urls_source ON collection_discovered_urls(source_id, canonical_url);
CREATE TABLE IF NOT EXISTS collection_candidates (
    candidate_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_rank INTEGER NOT NULL,
    original_ward TEXT NOT NULL,
    original_district TEXT NOT NULL,
    original_province TEXT NOT NULL,
    administrative_unit_id INTEGER,
    administrative_code TEXT,
    property_type TEXT,
    title TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    price_vnd REAL,
    area_m2 REAL,
    price_per_m2 REAL,
    area_basis TEXT NOT NULL DEFAULT 'UNKNOWN',
    source_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    source_url_type TEXT NOT NULL CHECK(source_url_type='DIRECT_LISTING'),
    source_listing_id TEXT,
    listed_date TEXT,
    expires_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    validity_status TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'PENDING',
    possible_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_group TEXT,
    candidate_identity_key TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    raw_payload TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, candidate_identity_key),
    FOREIGN KEY(source_id) REFERENCES collection_sources(source_id)
);
CREATE INDEX IF NOT EXISTS ix_collection_candidates_target ON collection_candidates(target_rank, property_type, validity_status);
CREATE INDEX IF NOT EXISTS ix_collection_candidates_content ON collection_candidates(content_fingerprint);
CREATE INDEX IF NOT EXISTS ix_collection_candidates_source_id ON collection_candidates(source_id, source_listing_id);
CREATE TABLE IF NOT EXISTS collection_candidate_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    observed_price_vnd REAL,
    observed_area_m2 REAL,
    price_per_m2 REAL,
    evidence_status TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    UNIQUE(candidate_id, observation_date),
    FOREIGN KEY(candidate_id) REFERENCES collection_candidates(candidate_id),
    FOREIGN KEY(source_run_id) REFERENCES collection_runs(run_id)
);
CREATE TABLE IF NOT EXISTS collection_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_rank INTEGER,
    rejected_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(run_id) REFERENCES collection_runs(run_id),
    FOREIGN KEY(source_id) REFERENCES collection_sources(source_id)
);
CREATE TABLE IF NOT EXISTS collection_daily_statistics (
    run_date TEXT PRIMARY KEY,
    latest_run_id TEXT NOT NULL,
    target_count INTEGER NOT NULL DEFAULT 0,
    processed_target_count INTEGER NOT NULL DEFAULT 0,
    requests_made INTEGER NOT NULL DEFAULT 0,
    candidates_found INTEGER NOT NULL DEFAULT 0,
    source_verified INTEGER NOT NULL DEFAULT 0,
    new_listings INTEGER NOT NULL DEFAULT 0,
    refreshed_listings INTEGER NOT NULL DEFAULT 0,
    expired_listings INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    geo_mismatches INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    quarantined INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def ensure_collection_schema(db: sqlite3.Connection) -> None:
    db.executescript(COLLECTION_SCHEMA)
    db.commit()


def sync_source_registry(db: sqlite3.Connection, path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if payload.get("version") != 1 or not isinstance(payload.get("sources"), list):
        raise ValueError("collector source registry version/shape is invalid")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db:
        db.execute(
            """INSERT INTO collection_settings(singleton,global_live_enabled,auto_ingest_verified,
               user_agent,global_daily_request_budget,updated_at) VALUES(1,?,?,?,?,?)
               ON CONFLICT(singleton) DO UPDATE SET global_live_enabled=excluded.global_live_enabled,
               auto_ingest_verified=excluded.auto_ingest_verified,user_agent=excluded.user_agent,
               global_daily_request_budget=excluded.global_daily_request_budget,updated_at=excluded.updated_at""",
            (
                int(bool(payload.get("global_live_enabled", False))),
                int(bool(payload.get("auto_ingest_verified", False))),
                str(payload.get("user_agent") or "WardPriceDailyCollector/0.2"),
                int(payload.get("global_daily_request_budget", 500)),
                now,
            ),
        )
        for item in payload["sources"]:
            required = ("source_id", "display_name", "base_url", "robots_url", "policy_status")
            if any(not str(item.get(key, "")).strip() for key in required):
                raise ValueError("each source requires source_id, display_name, base_url, robots_url and policy_status")
            db.execute(
                """INSERT INTO collection_sources(
                   source_id,display_name,base_url,robots_url,terms_url,robots_status,policy_status,
                   permission_reference,policy_checked_at,enabled,auto_ingest_verified,crawl_delay_seconds,
                   daily_request_budget,search_url_template,detail_path_regex,listing_id_regex,policy_note,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_id) DO UPDATE SET display_name=excluded.display_name,
                   base_url=excluded.base_url,robots_url=excluded.robots_url,terms_url=excluded.terms_url,
                   robots_status=excluded.robots_status,policy_status=excluded.policy_status,
                   permission_reference=excluded.permission_reference,policy_checked_at=excluded.policy_checked_at,
                   enabled=excluded.enabled,auto_ingest_verified=excluded.auto_ingest_verified,
                   crawl_delay_seconds=excluded.crawl_delay_seconds,daily_request_budget=excluded.daily_request_budget,
                   search_url_template=excluded.search_url_template,detail_path_regex=excluded.detail_path_regex,
                   listing_id_regex=excluded.listing_id_regex,policy_note=excluded.policy_note,updated_at=excluded.updated_at""",
                (
                    item["source_id"], item["display_name"], item["base_url"], item["robots_url"],
                    item.get("terms_url", ""), item.get("robots_status", "UNCHECKED"),
                    item.get("policy_status", "REVIEW_REQUIRED"), item.get("permission_reference", ""),
                    item.get("policy_checked_at"), int(bool(item.get("enabled", False))),
                    int(bool(item.get("auto_ingest_verified", False))),
                    float(item.get("crawl_delay_seconds", 5)), int(item.get("daily_request_budget", 100)),
                    item.get("search_url_template", ""), item.get("detail_path_regex", ""),
                    item.get("listing_id_regex", ""), item.get("policy_note", ""), now,
                ),
            )
    return {"sources_synced": len(payload["sources"]), "global_live_enabled": bool(payload.get("global_live_enabled"))}


def source_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = [dict(row) for row in db.execute("SELECT * FROM collection_sources ORDER BY source_id")]
    for row in rows:
        row["enabled"] = bool(row["enabled"])
        row["auto_ingest_verified"] = bool(row["auto_ingest_verified"])
    return rows


def collection_settings(db: sqlite3.Connection) -> dict[str, Any]:
    row = db.execute("SELECT * FROM collection_settings WHERE singleton=1").fetchone()
    return dict(row) if row else {
        "global_live_enabled": 0, "auto_ingest_verified": 0,
        "global_daily_request_budget": 500, "user_agent": "WardPriceDailyCollector/0.2",
    }


def collection_targets(db: sqlite3.Connection, ranks: set[int] | None = None) -> list[CollectionTarget]:
    columns = {row[1] for row in db.execute("PRAGMA table_info(priority_targets)")}
    targets_by_rank: dict[int, CollectionTarget] = {}
    if "target_rank" in columns:
        rows = db.execute(
            """SELECT target_rank,original_ward,original_district,original_province,mapping_status
               FROM priority_targets ORDER BY target_rank"""
        ).fetchall()
        for row in rows:
            mapping = db.execute(
                """SELECT pm.administrative_unit_id,u.administrative_code,u.administrative_name,
                          u.province_name,u.district_name_legacy
                   FROM priority_target_mappings pm JOIN administrative_units u
                     ON u.id=pm.administrative_unit_id
                   WHERE pm.target_rank=? AND pm.mapping_status='REVIEWED_RESOLUTION'
                     AND u.is_current=1 GROUP BY pm.administrative_unit_id,u.administrative_code,
                     u.administrative_name,u.province_name,u.district_name_legacy""",
                (row["target_rank"],),
            ).fetchall()
            unit_id = mapping[0]["administrative_unit_id"] if len(mapping) == 1 else None
            code = mapping[0]["administrative_code"] if len(mapping) == 1 else None
            target = CollectionTarget(
                int(row["target_rank"]), row["original_ward"], row["original_district"],
                row["original_province"], row["mapping_status"], unit_id, code,
                mapping[0]["administrative_name"] if len(mapping) == 1 else None,
                mapping[0]["province_name"] if len(mapping) == 1 else None,
            )
            targets_by_rank[target.rank] = target
    legacy_rows = db.execute("SELECT * FROM ward_target_legacy ORDER BY rank").fetchall()
    for row in legacy_rows:
        rank = int(row["rank"])
        targets_by_rank.setdefault(rank, CollectionTarget.from_row(row))
    return [
        target
        for rank, target in sorted(targets_by_rank.items())
        if ranks is None or rank in ranks
    ]


def target_mapping_review_counts(db: sqlite3.Connection) -> dict[str, int]:
    rows = db.execute("SELECT mapping_status,COUNT(*) AS n FROM priority_targets GROUP BY mapping_status").fetchall()
    return {row["mapping_status"]: int(row["n"]) for row in rows}


def _candidate_hash(source_id: str, identity: str) -> str:
    return hashlib.sha256(f"{source_id}|{identity}".encode()).hexdigest()[:32]


def _content_fingerprint(candidate: dict[str, Any]) -> str:
    from .parsing import normalize_text

    parts = (
        str(candidate.get("target_rank")), str(candidate.get("property_type") or ""),
        normalize_text(candidate.get("title", "")), normalize_text(candidate.get("address", "")),
        str(round(float(candidate["price_vnd"]))) if candidate.get("price_vnd") else "",
        f"{float(candidate['area_m2']):.4f}" if candidate.get("area_m2") else "",
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def store_discovered_url(db: sqlite3.Connection, *, run_id: str, source_id: str, target_rank: int, item: Any, at: str) -> bool:
    cursor = db.execute(
        """INSERT OR IGNORE INTO collection_discovered_urls(
           run_id,source_id,target_rank,url,canonical_url,source_url_type,discovered_at,status,skip_reason
           ) VALUES(?,?,?,?,?,?,?,'DISCOVERED',?)""",
        (run_id, source_id, target_rank, item.url, item.canonical_url, item.url_type, at,
         "not a configured direct listing URL" if item.url_type != "DIRECT_LISTING" else None),
    )
    return cursor.rowcount == 1


def store_rejection(
    db: sqlite3.Connection,
    *,
    run_id: str,
    source_id: str,
    target_rank: int,
    at: str,
    reason: str,
    raw_payload: dict[str, Any],
) -> bool:
    payload = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, default=str)
    exists = db.execute(
        """SELECT 1 FROM collection_rejections WHERE run_id=? AND source_id=?
           AND target_rank=? AND reason=? AND raw_payload=? LIMIT 1""",
        (run_id, source_id, target_rank, reason, payload),
    ).fetchone()
    if exists:
        return False
    db.execute(
        """INSERT INTO collection_rejections(
           run_id,source_id,target_rank,rejected_at,reason,raw_payload
           ) VALUES(?,?,?,?,?,?)""",
        (run_id, source_id, target_rank, at, reason, payload),
    )
    db.commit()
    return True


def store_candidate(db: sqlite3.Connection, *, run_id: str, source_id: str, candidate: dict[str, Any], at: str) -> dict[str, Any]:
    if candidate.get("source_url_type") != "DIRECT_LISTING":
        raise ValueError("category and unknown URLs cannot be stored as listing candidates")
    source_listing_id = candidate.get("source_listing_id")
    identity = f"id:{source_listing_id}" if source_listing_id else f"url:{candidate['canonical_url']}"
    content_fingerprint = _content_fingerprint(candidate)
    same_source = db.execute(
        """SELECT candidate_id,candidate_identity_key,content_fingerprint,last_seen_at,
                  evidence_status,validity_status,area_basis,listed_date,expires_at
           FROM collection_candidates WHERE source_id=? AND candidate_identity_key=?""",
        (source_id, identity),
    ).fetchone()
    if not same_source and not source_listing_id:
        same_source = db.execute(
            """SELECT candidate_id,candidate_identity_key,content_fingerprint,last_seen_at,
                      evidence_status,validity_status,area_basis,listed_date,expires_at
               FROM collection_candidates WHERE source_id=? AND content_fingerprint=? LIMIT 1""",
            (source_id, content_fingerprint),
        ).fetchone()
    cross_source = db.execute(
        "SELECT candidate_id,source_id FROM collection_candidates WHERE content_fingerprint=? AND source_id<>? LIMIT 1",
        (content_fingerprint, source_id),
    ).fetchone()
    if same_source:
        candidate_id = same_source["candidate_id"]
        identity = same_source["candidate_identity_key"]
    else:
        candidate_id = _candidate_hash(source_id, identity)
    duplicate = bool(cross_source)
    status = "NEEDS_REVIEW" if duplicate else candidate.get("validity_status", "UNVERIFIED")
    review = "NEEDS_REVIEW" if duplicate or status not in {"SOURCE_VERIFIED"} else "PENDING_PROMOTION"
    raw_json = json.dumps(candidate.get("raw_payload", {}), ensure_ascii=False, sort_keys=True)
    evidence_json = json.dumps(candidate.get("evidence", {}), ensure_ascii=False, sort_keys=True)
    inserted = same_source is None
    updated = bool(
        same_source
        and (
            same_source["content_fingerprint"] != content_fingerprint
            or same_source["evidence_status"] != candidate.get("evidence_status", "UNVERIFIED")
            or same_source["validity_status"] != candidate.get("validity_status", "UNVERIFIED")
            or same_source["area_basis"] != candidate.get("area_basis", "UNKNOWN")
            or same_source["listed_date"] != candidate.get("listed_date")
            or same_source["expires_at"] != candidate.get("expires_at")
        )
    )
    was_seen_today = bool(same_source and str(same_source["last_seen_at"])[:10] == at[:10])
    db.execute(
        """INSERT INTO collection_candidates(
           candidate_id,source_id,target_rank,original_ward,original_district,original_province,
           administrative_unit_id,administrative_code,property_type,title,address,price_vnd,area_m2,
           price_per_m2,area_basis,source_url,canonical_url,source_domain,source_url_type,source_listing_id,
           listed_date,expires_at,first_seen_at,last_seen_at,evidence_status,validity_status,review_status,
           possible_duplicate,duplicate_group,candidate_identity_key,content_fingerprint,evidence_json,raw_payload
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source_id,candidate_identity_key) DO UPDATE SET target_rank=excluded.target_rank,
           property_type=excluded.property_type,title=excluded.title,address=excluded.address,
           price_vnd=excluded.price_vnd,area_m2=excluded.area_m2,price_per_m2=excluded.price_per_m2,
           area_basis=excluded.area_basis,source_url=excluded.source_url,canonical_url=excluded.canonical_url,
           listed_date=COALESCE(excluded.listed_date,collection_candidates.listed_date),
           expires_at=COALESCE(excluded.expires_at,collection_candidates.expires_at),last_seen_at=excluded.last_seen_at,
           evidence_status=excluded.evidence_status,validity_status=excluded.validity_status,
           review_status=excluded.review_status,possible_duplicate=MAX(collection_candidates.possible_duplicate,excluded.possible_duplicate),
           duplicate_group=COALESCE(collection_candidates.duplicate_group,excluded.duplicate_group),
           content_fingerprint=excluded.content_fingerprint,evidence_json=excluded.evidence_json,raw_payload=excluded.raw_payload""",
        (
            candidate_id, source_id, candidate["target_rank"], candidate["original_ward"],
            candidate["original_district"], candidate["original_province"],
            candidate.get("administrative_unit_id"), candidate.get("administrative_code"),
            candidate.get("property_type"), candidate.get("title", ""), candidate.get("address", ""),
            candidate.get("price_vnd"), candidate.get("area_m2"), candidate.get("price_per_m2"),
            candidate.get("area_basis", "UNKNOWN"), candidate["source_url"], candidate["canonical_url"],
            candidate["source_domain"], "DIRECT_LISTING", source_listing_id, candidate.get("listed_date"),
            candidate.get("expires_at"), at, at, candidate.get("evidence_status", "UNVERIFIED"), status,
            review, int(duplicate), cross_source["candidate_id"] if cross_source else None,
            identity, content_fingerprint, evidence_json, raw_json,
        ),
    )
    observation_inserted = observation_updated = observation_deduplicated = False
    if candidate.get("price_vnd") and candidate.get("area_m2"):
        observation_day = at[:10]
        existing_observation = db.execute(
            """SELECT observed_price_vnd,observed_area_m2,price_per_m2,evidence_status,source_url
               FROM collection_candidate_observations
               WHERE candidate_id=? AND observation_date=?""",
            (candidate_id, observation_day),
        ).fetchone()
        if existing_observation is None:
            observation_inserted = True
        else:
            observation_updated = any(
                existing_observation[field] != value
                for field, value in (
                    ("observed_price_vnd", candidate["price_vnd"]),
                    ("observed_area_m2", candidate["area_m2"]),
                    ("price_per_m2", candidate["price_per_m2"]),
                    ("evidence_status", candidate["evidence_status"]),
                    ("source_url", candidate["source_url"]),
                )
            )
            observation_deduplicated = not observation_updated
        db.execute(
            """INSERT INTO collection_candidate_observations(
               candidate_id,observation_date,observed_at,observed_price_vnd,observed_area_m2,
               price_per_m2,evidence_status,source_run_id,source_url,raw_payload
               ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(candidate_id,observation_date) DO UPDATE SET
               observed_at=excluded.observed_at,observed_price_vnd=excluded.observed_price_vnd,
               observed_area_m2=excluded.observed_area_m2,price_per_m2=excluded.price_per_m2,
               evidence_status=excluded.evidence_status,source_run_id=excluded.source_run_id,
               source_url=excluded.source_url,raw_payload=excluded.raw_payload""",
            (candidate_id, observation_day, at, candidate["price_vnd"], candidate["area_m2"],
             candidate["price_per_m2"], candidate["evidence_status"], run_id, candidate["source_url"], raw_json),
        )
    db.commit()
    return {
        "candidate_id": candidate_id,
        "inserted": inserted,
        "updated": updated,
        "deduplicated": bool(same_source),
        "was_seen_today": was_seen_today,
        "observation_inserted": observation_inserted,
        "observation_updated": observation_updated,
        "observation_deduplicated": observation_deduplicated,
        "possible_duplicate": duplicate,
        "status": status,
        "content_fingerprint": content_fingerprint,
    }


def monitoring_summary(db: sqlite3.Connection, *, run_date: str | None = None) -> dict[str, Any]:
    run_date = run_date or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    runs = [dict(row) for row in db.execute(
        """SELECT run_id,run_date,mode,status,started_at,finished_at,total_targets,processed_targets,
                  requests_made,candidates_found,source_verified,new_listings,refreshed_listings,
                  expired_listings,conflicts,geo_mismatches,duplicates,quarantined,errors
           FROM collection_runs ORDER BY started_at DESC LIMIT 10"""
    )]
    today = [dict(row) for row in db.execute(
        """SELECT run_id,run_date,mode,status,started_at,finished_at,total_targets,processed_targets,
                  requests_made,candidates_found,source_verified,new_listings,refreshed_listings,
                  expired_listings,conflicts,geo_mismatches,duplicates,quarantined,errors
           FROM collection_runs WHERE run_date=? ORDER BY started_at DESC""", (run_date,)
    )]
    statuses = [dict(row) for row in db.execute(
        "SELECT validity_status,COUNT(*) AS count FROM collection_candidates GROUP BY validity_status ORDER BY validity_status"
    )]
    evidence_counts = [dict(row) for row in db.execute(
        "SELECT evidence_status,COUNT(*) AS count FROM collection_candidates GROUP BY evidence_status ORDER BY evidence_status"
    )]
    attempts = [dict(row) for row in db.execute(
        """SELECT a.target_rank,t.original_ward,t.original_district,t.original_province,
                  a.status,a.source_id,a.candidate_count,a.verified_count,a.duplicate_count,
                  a.quarantine_count,a.error_code,a.error,a.started_at,a.finished_at
           FROM collection_target_attempts a JOIN collection_runs r ON r.run_id=a.run_id
           LEFT JOIN priority_targets t ON t.target_rank=a.target_rank
           WHERE r.run_date=? ORDER BY a.target_rank,a.source_id""", (run_date,)
    )]
    canonical = int(db.execute(
        "SELECT COUNT(*) FROM listings WHERE active=1 AND evidence_status='SOURCE_PAGE_CONFIRMED' AND validation_status='VALIDATED' AND included_in_stats=1"
    ).fetchone()[0])
    target_table = "priority_targets" if db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='priority_targets'"
    ).fetchone() else "ward_target_legacy"
    target_count = int(db.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0])
    processed_target_count = int(db.execute(
        """SELECT COUNT(DISTINCT a.target_rank) FROM collection_target_attempts a
           JOIN collection_runs r ON r.run_id=a.run_id WHERE r.run_date=?""",
        (run_date,),
    ).fetchone()[0])
    totals = db.execute(
        """SELECT COALESCE(SUM(requests_made),0) AS requests_made,
                  COALESCE(SUM(candidates_found),0) AS candidates_found,
                  COALESCE(SUM(source_verified),0) AS source_verified,
                  COALESCE(SUM(new_listings),0) AS new_listings,
                  COALESCE(SUM(refreshed_listings),0) AS refreshed_listings,
                  COALESCE(SUM(expired_listings),0) AS expired_listings,
                  COALESCE(SUM(conflicts),0) AS conflicts,
                  COALESCE(SUM(geo_mismatches),0) AS geo_mismatches,
                  COALESCE(SUM(duplicates),0) AS duplicates,
                  COALESCE(SUM(quarantined),0) AS quarantined,
                  COALESCE(SUM(errors),0) AS errors
           FROM collection_runs WHERE run_date=?""",
        (run_date,),
    ).fetchone()
    latest_candidate_at = db.execute(
        "SELECT MAX(last_seen_at) FROM collection_candidates"
    ).fetchone()[0]
    rejection_count = int(db.execute("SELECT COUNT(*) FROM collection_rejections").fetchone()[0])
    rejected_today = int(db.execute(
        "SELECT COUNT(*) FROM collection_rejections WHERE substr(rejected_at,1,10)=?",
        (run_date,),
    ).fetchone()[0])
    recent_rejections = [dict(row) for row in db.execute(
        """SELECT target_rank,source_id,rejected_at,reason,raw_payload
           FROM collection_rejections ORDER BY rejected_at DESC,id DESC LIMIT 20"""
    )]
    from .source_registry import source_readiness

    return {
        "status": "OK",
        "run_date": run_date,
        "live_enabled": bool(collection_settings(db).get("global_live_enabled")),
        "target_count": target_count,
        "processed_target_count_today": processed_target_count,
        "unprocessed_target_count_today": max(0, target_count - processed_target_count),
        "daily_totals": dict(totals),
        "candidate_count": int(db.execute("SELECT COUNT(*) FROM collection_candidates").fetchone()[0]),
        "rejection_count": rejection_count,
        "rejected_today": rejected_today,
        "recent_rejections": recent_rejections,
        "candidate_evidence_counts": evidence_counts,
        "sources": source_rows(db),
        "source_readiness": source_readiness(db),
        "runs_today": today,
        "recent_runs": runs,
        "candidate_status_counts": statuses,
        "target_attempts_today": attempts,
        "verified_production_listing_count": canonical,
        "last_candidate_seen_at": latest_candidate_at,
        "scheduler_activation_by_pipeline": "NOT_ACTIVATED",
        "network_attempted": False,
    }
