"""SQLite persistence, selection policy, and append-only attempt history."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

NATIONAL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS data_sources (
        source_id TEXT PRIMARY KEY,
        source_name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        data_version TEXT,
        quality_status TEXT NOT NULL,
        file_sha256 TEXT,
        record_count INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS administrative_dataset_versions (
        dataset_version TEXT PRIMARY KEY,
        as_of_date TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        record_count INTEGER NOT NULL,
        province_count INTEGER NOT NULL DEFAULT 0,
        district_count INTEGER NOT NULL DEFAULT 0,
        commune_count INTEGER NOT NULL DEFAULT 0,
        imported_at TEXT NOT NULL,
        status TEXT NOT NULL,
        is_current INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '',
        FOREIGN KEY(source_id) REFERENCES data_sources(source_id)
    );
    CREATE TABLE IF NOT EXISTS administrative_units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        administrative_code TEXT,
        administrative_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        normalized_province TEXT NOT NULL,
        administrative_level TEXT NOT NULL CHECK(
            administrative_level IN ('PROVINCE','DISTRICT_HISTORIC','COMMUNE')
        ),
        administrative_type TEXT NOT NULL,
        parent_unit_id INTEGER,
        parent_unit_code TEXT,
        parent_unit_level TEXT,
        province_code TEXT,
        province_name TEXT NOT NULL,
        district_code_legacy TEXT,
        district_name_legacy TEXT,
        administrative_version TEXT NOT NULL,
        valid_from TEXT,
        valid_to TEXT,
        is_current INTEGER NOT NULL DEFAULT 0,
        mapping_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
        source_reference TEXT NOT NULL,
        source_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(parent_unit_id) REFERENCES administrative_units(id),
        FOREIGN KEY(source_id) REFERENCES data_sources(source_id)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_unit_version_code
        ON administrative_units(
            administrative_version, administrative_level, province_code,
            administrative_code, normalized_name
        )
        WHERE administrative_code IS NOT NULL;
    CREATE INDEX IF NOT EXISTS ix_admin_unit_current_code
        ON administrative_units(is_current, administrative_level, administrative_code);
    CREATE INDEX IF NOT EXISTS ix_admin_unit_name
        ON administrative_units(administrative_level, normalized_name, province_name);
    CREATE INDEX IF NOT EXISTS ix_admin_unit_province
        ON administrative_units(is_current, normalized_province, administrative_level);
    CREATE INDEX IF NOT EXISTS ix_admin_unit_parent
        ON administrative_units(parent_unit_id, is_current);
    CREATE INDEX IF NOT EXISTS ix_admin_unit_version
        ON administrative_units(administrative_version, administrative_level, is_current);
    CREATE TABLE IF NOT EXISTS administrative_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        administrative_unit_id INTEGER,
        alias_name TEXT NOT NULL,
        normalized_alias TEXT NOT NULL,
        alias_type TEXT NOT NULL,
        effective_from TEXT,
        effective_to TEXT,
        source_reference TEXT NOT NULL,
        mapping_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
        province_name TEXT,
        district_name_legacy TEXT,
        target_rank INTEGER,
        source_version TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    CREATE INDEX IF NOT EXISTS ix_admin_alias_name
        ON administrative_aliases(normalized_alias, mapping_status);
    CREATE INDEX IF NOT EXISTS ix_admin_alias_unit
        ON administrative_aliases(administrative_unit_id, alias_type);
    CREATE INDEX IF NOT EXISTS ix_admin_alias_target
        ON administrative_aliases(target_rank, mapping_status);
    CREATE TABLE IF NOT EXISTS administrative_relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_unit_id INTEGER,
        target_unit_id INTEGER,
        relationship_type TEXT NOT NULL CHECK(relationship_type IN (
            'MERGED','RENAMED','SPLIT','PARTIAL_TRANSFER','UNRESOLVED'
        )),
        effective_date TEXT,
        mapping_status TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        source_id TEXT,
        raw_payload TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(source_unit_id) REFERENCES administrative_units(id),
        FOREIGN KEY(target_unit_id) REFERENCES administrative_units(id),
        FOREIGN KEY(source_id) REFERENCES data_sources(source_id)
    );
    CREATE INDEX IF NOT EXISTS ix_admin_relationship_source
        ON administrative_relationships(source_unit_id, mapping_status);
    CREATE INDEX IF NOT EXISTS ix_admin_relationship_target
        ON administrative_relationships(target_unit_id, relationship_type);
    CREATE TABLE IF NOT EXISTS priority_targets (
        target_rank INTEGER PRIMARY KEY CHECK(target_rank BETWEEN 1 AND 50),
        original_ward TEXT NOT NULL,
        original_district TEXT NOT NULL,
        original_province TEXT NOT NULL,
        current_ward TEXT NOT NULL DEFAULT '',
        current_province TEXT NOT NULL DEFAULT '',
        administrative_unit_id INTEGER,
        mapping_status TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    CREATE INDEX IF NOT EXISTS ix_priority_targets_unit
        ON priority_targets(administrative_unit_id, mapping_status);
    CREATE TABLE IF NOT EXISTS priority_target_mappings (
        target_rank INTEGER NOT NULL CHECK(target_rank BETWEEN 1 AND 50),
        administrative_unit_id INTEGER NOT NULL,
        relationship_type TEXT NOT NULL CHECK(relationship_type IN (
            'MERGED','RENAMED','SPLIT','PARTIAL_TRANSFER','UNRESOLVED'
        )),
        mapping_status TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        effective_date TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY(target_rank, administrative_unit_id, source_reference),
        FOREIGN KEY(target_rank) REFERENCES priority_targets(target_rank),
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    CREATE INDEX IF NOT EXISTS ix_priority_target_mappings_rank
        ON priority_target_mappings(target_rank, mapping_status);
    CREATE INDEX IF NOT EXISTS ix_priority_target_mappings_unit
        ON priority_target_mappings(administrative_unit_id, mapping_status);
    CREATE TABLE IF NOT EXISTS listing_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id TEXT NOT NULL,
        administrative_unit_id INTEGER NOT NULL,
        observation_date TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        observed_price_vnd REAL NOT NULL,
        observed_area_m2 REAL NOT NULL,
        price_per_m2 REAL NOT NULL,
        area_basis TEXT NOT NULL,
        evidence_status TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        source_run_id TEXT NOT NULL,
        source_url TEXT NOT NULL,
        raw_payload TEXT NOT NULL,
        UNIQUE(listing_id, observation_date),
        FOREIGN KEY(listing_id) REFERENCES listings(listing_id),
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    CREATE INDEX IF NOT EXISTS ix_listing_observation_unit_date
        ON listing_observations(administrative_unit_id, observation_date, evidence_status);
    CREATE INDEX IF NOT EXISTS ix_listing_observation_listing
        ON listing_observations(listing_id, observation_date DESC);
    CREATE TABLE IF NOT EXISTS ward_price_statistics (
        administrative_unit_id INTEGER NOT NULL,
        target_rank INTEGER,
        property_type TEXT NOT NULL CHECK(property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')),
        area_basis TEXT NOT NULL,
        snapshot_date TEXT NOT NULL,
        sample_count INTEGER NOT NULL,
        mean_price_per_m2 REAL,
        median_price_per_m2 REAL,
        min_price_per_m2 REAL,
        max_price_per_m2 REAL,
        calculation_window_days INTEGER NOT NULL,
        latest_observation_at TEXT,
        source_quality TEXT NOT NULL,
        calculation_version TEXT NOT NULL,
        PRIMARY KEY(administrative_unit_id, property_type, area_basis, snapshot_date),
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
    CREATE INDEX IF NOT EXISTS ix_ward_price_stats_snapshot
        ON ward_price_statistics(snapshot_date, property_type, area_basis);
    CREATE INDEX IF NOT EXISTS ix_ward_price_stats_target
        ON ward_price_statistics(target_rank, snapshot_date);
    CREATE TABLE IF NOT EXISTS listing_quarantine (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        row_index INTEGER NOT NULL,
        reason TEXT NOT NULL,
        raw_payload TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_listing_quarantine_run
        ON listing_quarantine(run_id, row_index);
    CREATE TABLE IF NOT EXISTS provider_fetch_state (
        administrative_unit_id INTEGER NOT NULL,
        property_type TEXT NOT NULL,
        provider TEXT NOT NULL,
        last_attempt TEXT,
        last_success TEXT,
        next_allowed_attempt TEXT,
        status TEXT NOT NULL,
        error TEXT,
        negative_cache_until TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(administrative_unit_id, property_type, provider),
        FOREIGN KEY(administrative_unit_id) REFERENCES administrative_units(id)
    );
"""


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ward_code TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            grounding_used INTEGER DEFAULT 0,
            prompt_tokens INTEGER,
            output_tokens INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_attempt_ward ON attempts(ward_code, attempted_at);
        CREATE TABLE IF NOT EXISTS valuations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ward_code TEXT NOT NULL,
            ward_name TEXT NOT NULL,
            province TEXT NOT NULL,
            property_type TEXT NOT NULL,
            mean_vnd_m2 INTEGER NOT NULL,
            min_vnd_m2 INTEGER NOT NULL,
            max_vnd_m2 INTEGER NOT NULL,
            data_type TEXT NOT NULL,
            quality_gate TEXT NOT NULL,
            confidence TEXT NOT NULL,
            estimation_basis TEXT NOT NULL,
            source_urls_json TEXT NOT NULL,
            grounding_used INTEGER NOT NULL,
            model TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            collected_day TEXT NOT NULL,
            UNIQUE(ward_code, property_type, collected_day)
        );
        CREATE INDEX IF NOT EXISTS idx_val_ward ON valuations(ward_code, collected_at);
        CREATE TABLE IF NOT EXISTS run_log (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
            finished_at TEXT, attempted INTEGER DEFAULT 0,
            accepted INTEGER DEFAULT 0, no_data INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0, details TEXT
        );
        CREATE TABLE IF NOT EXISTS ward_registry (
            ward_code TEXT PRIMARY KEY,
            ward_name TEXT NOT NULL,
            province TEXT NOT NULL,
            district TEXT NOT NULL DEFAULT '',
            admin_source TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            imported_at TEXT NOT NULL,
            last_search_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ward_target_legacy (
            rank INTEGER PRIMARY KEY CHECK(rank BETWEEN 1 AND 50),
            old_province TEXT NOT NULL,
            old_district TEXT NOT NULL,
            old_ward TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('PHƯỜNG','XÃ')),
            n_customers INTEGER NOT NULL CHECK(n_customers >= 0),
            pct REAL NOT NULL CHECK(pct >= 0),
            batch INTEGER NOT NULL CHECK(batch BETWEEN 1 AND 10),
            current_province TEXT NOT NULL DEFAULT '',
            current_ward TEXT NOT NULL DEFAULT '',
            current_ward_code TEXT,
            status TEXT NOT NULL CHECK(status IN ('REVIEWED_RESOLUTION','PENDING_ADMIN_MAPPING')),
            mapping_note TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            imported_at TEXT NOT NULL,
            UNIQUE(old_province, old_district, old_ward),
            CHECK(current_ward_code IS NULL OR length(trim(current_ward_code)) > 0)
        );
        CREATE INDEX IF NOT EXISTS idx_ward_target_batch_status
            ON ward_target_legacy(batch, status, rank);
        CREATE TABLE IF NOT EXISTS listings (
            listing_id TEXT PRIMARY KEY,
            identity_key TEXT NOT NULL UNIQUE,
            identity_fingerprint TEXT NOT NULL,
            ward_code TEXT NOT NULL,
            ward_name TEXT NOT NULL,
            province TEXT NOT NULL,
            property_type TEXT NOT NULL,
            price_vnd REAL NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            address TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            listed_date TEXT,
            collected_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            evidence_excerpt TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            included_in_stats INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_listings_ward_type
            ON listings(ward_code, property_type, active, included_in_stats);
        CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_listings_fingerprint ON listings(ward_code, identity_fingerprint);
        CREATE TABLE IF NOT EXISTS listing_sources (
            canonical_url TEXT PRIMARY KEY,
            listing_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            FOREIGN KEY(listing_id) REFERENCES listings(listing_id)
        );
        CREATE INDEX IF NOT EXISTS idx_listing_sources_listing ON listing_sources(listing_id);
        CREATE TABLE IF NOT EXISTS listing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            price_vnd REAL NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            evidence_status TEXT NOT NULL,
            source_url TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            FOREIGN KEY(listing_id) REFERENCES listings(listing_id)
        );
        CREATE INDEX IF NOT EXISTS idx_listing_history_listing
            ON listing_history(listing_id, observed_at);
        CREATE TABLE IF NOT EXISTS listing_search_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ward_code TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            accepted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            limit_skipped_count INTEGER NOT NULL DEFAULT 0,
            grounding_used INTEGER NOT NULL DEFAULT 0,
            search_queries INTEGER NOT NULL DEFAULT 0,
            prompt_tokens INTEGER,
            output_tokens INTEGER,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_listing_search_month
            ON listing_search_runs(started_at, status);
        CREATE INDEX IF NOT EXISTS idx_listing_search_ward
            ON listing_search_runs(ward_code, started_at);
        CREATE TABLE IF NOT EXISTS listing_rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ward_code TEXT NOT NULL,
            rejected_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            raw_payload TEXT NOT NULL
        );
    """)
    db.executescript(NATIONAL_SCHEMA)
    ward_columns = {row[1] for row in db.execute("PRAGMA table_info(ward_registry)")}
    if "district" not in ward_columns:
        db.execute("ALTER TABLE ward_registry ADD COLUMN district TEXT NOT NULL DEFAULT ''")
    listing_columns = {row[1] for row in db.execute("PRAGMA table_info(listings)")}
    listing_additions = {
        "administrative_unit_id": "INTEGER",
        "target_rank": "INTEGER",
        "area_basis": "TEXT",
        "validation_status": "TEXT NOT NULL DEFAULT 'LEGACY_UNREVIEWED'",
        "dedup_key": "TEXT",
        "title": "TEXT NOT NULL DEFAULT ''",
        "source_website": "TEXT",
        "published_at": "TEXT",
    }
    for column_name, declaration in listing_additions.items():
        if column_name not in listing_columns:
            db.execute(f"ALTER TABLE listings ADD COLUMN {column_name} {declaration}")
    alias_columns = {row[1] for row in db.execute("PRAGMA table_info(administrative_aliases)")}
    for column_name in ("province_name", "district_name_legacy"):
        if column_name not in alias_columns:
            db.execute(f"ALTER TABLE administrative_aliases ADD COLUMN {column_name} TEXT")
    db.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_admin_unit "
        "ON listings(administrative_unit_id, property_type, active)"
    )
    db.commit()
    return db


def backup_database_before_collection_migration(path: Path) -> Path | None:
    """Create and verify a SQLite snapshot before adding collection tables."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return None
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"{path.stem}.pre_collection_{stamp}.sqlite3"
    source_db = sqlite3.connect(path)
    backup_db = sqlite3.connect(destination)
    try:
        source_db.backup(backup_db)
        integrity = backup_db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"backup integrity check failed: {integrity}")
    except Exception:
        backup_db.close()
        source_db.close()
        destination.unlink(missing_ok=True)
        raise
    backup_db.close()
    source_db.close()
    return destination


def now_utc():
    return datetime.now(timezone.utc)


def month_call_count(db, today=None):
    today = today or now_utc()
    start = today.strftime("%Y-%m-01T00:00:00")
    row = db.execute("SELECT COUNT(*) n FROM attempts WHERE attempted_at >= ?", (start,)).fetchone()
    return int(row["n"])


def ward_coverage(db):
    row = db.execute("SELECT COUNT(DISTINCT ward_code) n FROM valuations").fetchone()
    return int(row["n"])


def latest_valuation_rows(db):
    return db.execute("""
        SELECT v.* FROM valuations v
        JOIN (
          SELECT ward_code, property_type, MAX(collected_at) latest
          FROM valuations GROUP BY ward_code, property_type
        ) x ON x.ward_code = v.ward_code AND x.property_type = v.property_type
         AND x.latest = v.collected_at
        ORDER BY v.province, v.ward_name, v.property_type
    """).fetchall()


def choose_wards(db, registry, *, limit, target, refresh_days, retry_days, max_attempts, now=None):
    """Legacy valuation selection; target limits wards and is not used by the listing CLI."""
    now = now or now_utc()
    cutoff_refresh = (now - timedelta(days=refresh_days)).isoformat(timespec="seconds")
    cutoff_retry = (now - timedelta(days=retry_days)).isoformat(timespec="seconds")
    existing = {
        r["ward_code"]: r["last_at"]
        for r in db.execute(
            "SELECT ward_code, MAX(collected_at) last_at FROM valuations GROUP BY ward_code"
        )
    }
    attempts = {
        r["ward_code"]: (r["n"], r["last_at"])
        for r in db.execute(
            "SELECT ward_code, COUNT(*) n, MAX(attempted_at) last_at FROM attempts GROUP BY ward_code"
        )
    }
    current = len(existing)
    new, refresh = [], []
    for ward in registry:
        previous = attempts.get(ward.code)
        if ward.code not in existing:
            if current >= target or (previous and previous[0] >= max_attempts):
                continue
            if previous and previous[1] > cutoff_retry:
                continue
            new.append((previous is not None, ward))
        elif existing[ward.code] < cutoff_refresh:
            refresh.append((existing[ward.code], ward))
    # Never count multiple property types as multiple wards; remaining capacity is explicit.
    new.sort(key=lambda item: item[0])  # first untouched, then retries
    slots_new = max(0, target - current)
    selected = [w for _, w in new[: min(limit, slots_new)]]
    if len(selected) < limit:
        refresh.sort(key=lambda item: item[0])
        selected.extend(w for _, w in refresh[: limit - len(selected)])
    return selected


def log_attempt(
    db, run_id, ward_code, status, reason="", grounding_used=False, usage=None, at=None
):
    usage = usage or {}
    db.execute(
        """INSERT INTO attempts (
        run_id,ward_code,attempted_at,status,reason,grounding_used,prompt_tokens,output_tokens
    ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            run_id,
            ward_code,
            (at or now_utc()).isoformat(timespec="seconds"),
            status,
            str(reason)[:1000],
            int(grounding_used),
            usage.get("prompt_tokens"),
            usage.get("output_tokens"),
        ),
    )
    db.commit()


def save_results(db, run_id, items):
    for obj in items:
        db.execute(
            """INSERT INTO valuations (
            run_id,ward_code,ward_name,province,property_type,mean_vnd_m2,
            min_vnd_m2,max_vnd_m2,data_type,quality_gate,confidence,
            estimation_basis,source_urls_json,grounding_used,model,collected_at,collected_day
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (ward_code,property_type,collected_day) DO UPDATE SET
          run_id=excluded.run_id, mean_vnd_m2=excluded.mean_vnd_m2,
          min_vnd_m2=excluded.min_vnd_m2, max_vnd_m2=excluded.max_vnd_m2,
          data_type=excluded.data_type,quality_gate=excluded.quality_gate,
          confidence=excluded.confidence,estimation_basis=excluded.estimation_basis,
          source_urls_json=excluded.source_urls_json,
          grounding_used=excluded.grounding_used,model=excluded.model,
          collected_at=excluded.collected_at""",
            (
                run_id,
                obj["ward_code"],
                obj["ward_name"],
                obj["province"],
                obj["property_type"],
                obj["average_price_per_m2"],
                obj["min_estimated_price_per_m2"],
                obj["max_estimated_price_per_m2"],
                obj["data_type"],
                obj["quality_gate"],
                obj["confidence"],
                obj["estimation_basis"],
                json.dumps(obj["source_urls"], ensure_ascii=False),
                int(obj["grounding_used"]),
                obj["model"],
                obj["collected_at"],
                obj["collected_at"][:10],
            ),
        )
    db.commit()


def stats(db):
    latest = latest_valuation_rows(db)
    return {
        "wards_with_any_research_price": ward_coverage(db),
        "price_rows_latest": len(latest),
        "ai_estimate_rows": sum(1 for x in latest if x["data_type"] == "AI_ESTIMATE"),
        "market_reference_unverified_rows": sum(
            1 for x in latest if x["data_type"] == "MARKET_REFERENCE_UNVERIFIED"
        ),
        "market_verified_rows": 0,
        "api_calls_this_month": month_call_count(db),
        "attempts_total": db.execute("SELECT COUNT(*) n FROM attempts").fetchone()["n"],
        "tracked_listings": tracked_listing_count(db),
        "eligible_listings": db.execute(
            "SELECT COUNT(*) n FROM listings WHERE active=1 AND included_in_stats=1"
        ).fetchone()["n"],
        "listing_api_calls_this_month": listing_call_count(db),
    }


def import_wards(db, wards, at=None):
    """Replace the active research whitelist while preserving all collected data."""
    wards = list(wards)
    if not wards:
        raise ValueError("Ward whitelist must contain at least one ward")
    if len(wards) > 100:
        raise ValueError("Ward whitelist cannot exceed 100 wards")
    codes = [ward.code for ward in wards]
    if len(set(codes)) != len(codes):
        raise ValueError("Ward whitelist contains duplicate ward_code values")
    imported_at = (at or now_utc()).isoformat(timespec="seconds")
    with db:
        db.execute("UPDATE ward_registry SET active=0")
        db.executemany(
            """INSERT INTO ward_registry(
                ward_code,ward_name,province,district,admin_source,active,imported_at,last_search_at
            ) VALUES(?,?,?,?,?,1,?,NULL)
            ON CONFLICT(ward_code) DO UPDATE SET
                ward_name=excluded.ward_name, province=excluded.province,
                district=excluded.district,
                admin_source=excluded.admin_source, active=1, imported_at=excluded.imported_at""",
            [
                (w.code, w.name, w.province, w.district, w.source or None, imported_at)
                for w in wards
            ],
        )


def import_legacy_targets(db, targets, at=None):
    """Upsert the fixed legacy target registry without changing active wards or listings."""
    targets = list(targets)
    if len(targets) != 50 or {target.rank for target in targets} != set(range(1, 51)):
        raise ValueError("Legacy target import requires ranks 1 through 50 exactly once")
    imported_at = (at or now_utc()).isoformat(timespec="seconds")
    with db:
        db.executemany(
            """INSERT INTO ward_target_legacy(
                rank,old_province,old_district,old_ward,category,n_customers,pct,batch,
                current_province,current_ward,current_ward_code,status,mapping_note,source_url,
                imported_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(rank) DO UPDATE SET
                old_province=excluded.old_province, old_district=excluded.old_district,
                old_ward=excluded.old_ward, category=excluded.category,
                n_customers=excluded.n_customers, pct=excluded.pct, batch=excluded.batch,
                current_province=excluded.current_province, current_ward=excluded.current_ward,
                current_ward_code=excluded.current_ward_code, status=excluded.status,
                mapping_note=excluded.mapping_note, source_url=excluded.source_url,
                imported_at=excluded.imported_at""",
            [
                (
                    target.rank,
                    target.old_province,
                    target.old_district,
                    target.old_ward,
                    target.category,
                    target.n_customers,
                    target.pct,
                    target.batch,
                    target.current_province,
                    target.current_ward,
                    target.current_ward_code,
                    target.status,
                    target.mapping_note,
                    target.source_url,
                    imported_at,
                )
                for target in targets
            ],
        )


def legacy_target_rows(db):
    """Return target/mapping fields for operator review, excluding customer metrics."""
    return [
        dict(row)
        for row in db.execute(
            """SELECT rank,old_province,old_district,old_ward,category,batch,
                      current_province,current_ward,current_ward_code,status,mapping_note,source_url
               FROM ward_target_legacy ORDER BY rank"""
        ).fetchall()
    ]


def active_wards(db):
    from .registry import Ward

    rows = db.execute(
        "SELECT ward_code,ward_name,province,COALESCE(admin_source,'') source,district "
        "FROM ward_registry WHERE active=1 ORDER BY ward_code"
    ).fetchall()
    return [
        Ward(row["ward_code"], row["ward_name"], row["province"], row["source"], row["district"])
        for row in rows
    ]


def tracked_listing_count(db):
    return int(db.execute("SELECT COUNT(*) n FROM listings").fetchone()["n"])


def listing_call_count(db, today=None):
    today = today or now_utc()
    start = today.strftime("%Y-%m-01T00:00:00")
    return int(
        db.execute(
            "SELECT COUNT(*) n FROM listing_search_runs WHERE started_at >= ?", (start,)
        ).fetchone()["n"]
    )


def choose_listing_wards(db, wards, *, limit, now=None):
    """Prioritize wards with no listings, then the least recently searched wards."""
    if limit <= 0:
        return []
    counts = {
        row["ward_code"]: int(row["n"])
        for row in db.execute(
            "SELECT ward_code,COUNT(*) n FROM listings WHERE active=1 GROUP BY ward_code"
        )
    }
    searched = {
        row["ward_code"]: row["last_at"]
        for row in db.execute(
            "SELECT ward_code,MAX(started_at) last_at FROM listing_search_runs GROUP BY ward_code"
        )
    }
    return sorted(
        wards,
        key=lambda ward: (counts.get(ward.code, 0), searched.get(ward.code, ""), ward.code),
    )[:limit]


def listings_for_ward(db, ward_code, limit=20):
    rows = db.execute(
        """SELECT listing_id,property_type,address,price_vnd,area_m2,price_per_m2,
                  source_url,listed_date,evidence_status,last_seen_at
           FROM listings WHERE ward_code=? AND active=1 ORDER BY last_seen_at ASC LIMIT ?""",
        (ward_code, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def listing_statistics(db):
    """Calculate ward/type summaries from eligible current listing observations in Python."""
    from collections import defaultdict
    from statistics import mean, median

    grouped = defaultdict(list)
    rows = db.execute(
        """SELECT l.ward_code,l.ward_name,l.province,l.property_type,l.price_per_m2,
                  l.evidence_status,l.last_seen_at
           FROM listings l JOIN ward_registry w ON w.ward_code=l.ward_code AND w.active=1
           WHERE l.active=1 AND l.included_in_stats=1
           ORDER BY l.ward_code,l.property_type"""
    ).fetchall()
    for row in rows:
        grouped[(row["ward_code"], row["ward_name"], row["province"], row["property_type"])].append(row)
    results = []
    for (ward_code, ward_name, province, property_type), records in sorted(grouped.items()):
        values = [float(record["price_per_m2"]) for record in records]
        evidence = {record["evidence_status"] for record in records}
        results.append(
            {
                "ward_code": ward_code,
                "ward_name": ward_name,
                "province": province,
                "property_type": property_type,
                "listing_count": len(values),
                "mean_price_per_m2": mean(values),
                "median_price_per_m2": median(values),
                "min_price_per_m2": min(values),
                "max_price_per_m2": max(values),
                "data_quality": (
                    "HIGH" if evidence == {"SOURCE_PAGE_CONFIRMED"}
                    else "LIMITED_SNIPPET" if evidence == {"SEARCH_SNIPPET_ONLY"}
                    else "MIXED_EVIDENCE"
                ),
                "last_updated": max(record["last_seen_at"] for record in records),
            }
        )
    return results


def listing_rows(db):
    return [
        dict(row)
        for row in db.execute(
            """SELECT l.listing_id,l.ward_code,l.ward_name,l.province,l.property_type,l.price_vnd,
                      l.area_m2,l.price_per_m2,l.address,l.source_url,l.source_domain,l.listed_date,
                      l.collected_at,l.last_seen_at,l.evidence_status,l.evidence_excerpt
               FROM listings l JOIN ward_registry w ON w.ward_code=l.ward_code AND w.active=1
               WHERE l.active=1 ORDER BY l.province,l.ward_name,l.property_type,l.listed_date"""
        ).fetchall()
    ]


def record_listing(db, candidate, run_id, *, max_total=500, observed_at=None):
    """Insert or refresh a listing, maintaining source and append-only observation history."""
    observed_at = observed_at or now_utc().isoformat(timespec="seconds")
    raw_payload = candidate["raw_payload"]
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute(
            "SELECT listing_id,ward_code FROM listings WHERE identity_key=?",
            (candidate["identity_key"],),
        ).fetchone()
        if existing is None:
            existing = db.execute(
                """SELECT l.listing_id,l.ward_code FROM listing_sources s
                   JOIN listings l ON l.listing_id=s.listing_id WHERE s.canonical_url=?""",
                (candidate["identity_key"],),
            ).fetchone()
        if existing is None:
            existing = db.execute(
                """SELECT listing_id,ward_code FROM listings WHERE ward_code=? AND identity_fingerprint=?
                   ORDER BY last_seen_at DESC LIMIT 1""",
                (candidate["ward_code"], candidate["identity_fingerprint"]),
            ).fetchone()
        inserted = existing is None
        if existing and existing["ward_code"] != candidate["ward_code"]:
            db.rollback()
            return "WARD_CONFLICT"
        if inserted and tracked_listing_count(db) >= max_total:
            db.rollback()
            return "LIMIT_REACHED"
        listing_id = existing["listing_id"] if existing else candidate["listing_id"]
        if inserted:
            db.execute(
                """INSERT INTO listings(
                    listing_id,identity_key,identity_fingerprint,ward_code,ward_name,province,
                    property_type,price_vnd,area_m2,price_per_m2,address,source_url,source_domain,
                    listed_date,collected_at,last_seen_at,evidence_status,evidence_excerpt,
                    raw_payload,active,included_in_stats
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,1)""",
                (
                    listing_id, candidate["identity_key"], candidate["identity_fingerprint"],
                    candidate["ward_code"], candidate["ward_name"], candidate["province"],
                    candidate["property_type"], candidate["price_vnd"], candidate["area_m2"],
                    candidate["price_per_m2"], candidate["address"], candidate["source_url"],
                    candidate["source_domain"], candidate["listed_date"], observed_at, observed_at,
                    candidate["evidence_status"], candidate["evidence_excerpt"], raw_payload,
                ),
            )
        else:
            db.execute(
                """UPDATE listings SET identity_fingerprint=?,ward_name=?,province=?,property_type=?,price_vnd=?,
                    area_m2=?,price_per_m2=?,address=?,source_url=?,source_domain=?,
                    listed_date=COALESCE(?,listed_date),collected_at=?,last_seen_at=?,
                    evidence_status=?,evidence_excerpt=?,raw_payload=?,active=1,included_in_stats=1
                    WHERE listing_id=?""",
                (
                    candidate["identity_fingerprint"], candidate["ward_name"], candidate["province"], candidate["property_type"],
                    candidate["price_vnd"], candidate["area_m2"], candidate["price_per_m2"],
                    candidate["address"], candidate["source_url"], candidate["source_domain"],
                    candidate["listed_date"], observed_at, observed_at, candidate["evidence_status"],
                    candidate["evidence_excerpt"], raw_payload, listing_id,
                ),
            )
        db.execute(
            """INSERT INTO listing_sources(
                canonical_url,listing_id,source_url,source_domain,first_seen_at,last_seen_at
            ) VALUES(?,?,?,?,?,?) ON CONFLICT(canonical_url) DO UPDATE SET
                listing_id=excluded.listing_id,source_url=excluded.source_url,
                source_domain=excluded.source_domain,last_seen_at=excluded.last_seen_at""",
            (
                candidate["identity_key"], listing_id, candidate["source_url"],
                candidate["source_domain"], observed_at, observed_at,
            ),
        )
        db.execute(
            """INSERT INTO listing_history(
                listing_id,run_id,observed_at,price_vnd,area_m2,price_per_m2,
                evidence_status,source_url,raw_payload
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                listing_id, run_id, observed_at, candidate["price_vnd"], candidate["area_m2"],
                candidate["price_per_m2"], candidate["evidence_status"], candidate["source_url"],
                raw_payload,
            ),
        )
        db.commit()
        return "INSERTED" if inserted else "UPDATED"
    except Exception:
        db.rollback()
        raise
