"""Offline tests for permission-gated listing discovery, storage and monitoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from wardprice.collectors.models import FetchResponse
from wardprice.collectors.orchestrator import local_now, plan_collection, run_live_collection
from wardprice.collectors.parsing import (
    discover_listing_urls,
    extract_listing_detail,
    parse_area_m2,
    parse_price_vnd,
)
from wardprice.collectors.policy import CollectionBlocked, RobotsAwareClient
from wardprice.collectors.source_registry import source_readiness, sync_registry
from wardprice.collectors.storage import (
    collection_targets,
    ensure_collection_schema,
    monitoring_summary,
    store_candidate,
    store_discovered_url,
    store_rejection,
)
from wardprice.database import backup_database_before_collection_migration, connect

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "collectors"
LISTING_URL = "https://fixture.test/listing/abc-001"


def _insert_mapped_target(db):
    now = "2026-10-14T00:00:00+00:00"
    db.execute(
        """INSERT INTO administrative_units(
             administrative_code,administrative_name,normalized_name,normalized_province,
             administrative_level,administrative_type,province_code,province_name,
             district_name_legacy,administrative_version,is_current,mapping_status,
             source_reference,created_at,updated_at
           ) VALUES('00001','Phường Trung Tâm','phuong trung tam','tinh demo',
             'COMMUNE','PHUONG','01','Tỉnh Demo','Quận Demo','fixture-v1',1,
             'REVIEWED_RESOLUTION','offline test fixture',?,?)""",
        (now, now),
    )
    unit_id = db.execute(
        "SELECT id FROM administrative_units WHERE administrative_code='00001'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO priority_targets(
             target_rank,original_ward,original_district,original_province,current_ward,
             current_province,administrative_unit_id,mapping_status,source_reference,updated_at
           ) VALUES(1,'Phường Trung Tâm','Quận Demo','Tỉnh Demo','Phường Trung Tâm',
             'Tỉnh Demo',?,'REVIEWED_RESOLUTION','offline test fixture',?)""",
        (unit_id, now),
    )
    db.execute(
        """INSERT INTO priority_target_mappings(
             target_rank,administrative_unit_id,relationship_type,mapping_status,
             source_reference,effective_date,created_at
           ) VALUES(1,?,'RENAMED','REVIEWED_RESOLUTION','offline test fixture',NULL,?)""",
        (unit_id, now),
    )
    db.commit()
    return unit_id


def _seed_collection_db(path):
    db = connect(path)
    ensure_collection_schema(db)
    _insert_mapped_target(db)
    sync_registry(db)
    db.execute(
        """UPDATE collection_settings SET global_live_enabled=1,
           auto_ingest_verified=1,global_daily_request_budget=30 WHERE singleton=1"""
    )
    db.execute(
        """UPDATE collection_sources SET base_url='https://fixture.test/',
           robots_url='https://fixture.test/robots.txt',terms_url='',robots_status='ALLOW',
           policy_status='APPROVED',permission_reference='offline fixture only',enabled=1,
           auto_ingest_verified=1,crawl_delay_seconds=1,daily_request_budget=30,
           search_url_template='https://fixture.test/search?q={query}&type={property_type}',
           detail_path_regex='^/listing/[a-z0-9-]+$',listing_id_regex='listing/([a-z0-9-]+)$'
           WHERE source_id='batdongsan.com.vn'"""
    )
    db.commit()
    return db


def _response(url: str, body: bytes, status: int = 200, headers=None):
    response_headers = headers or {"content-type": "text/html; charset=utf-8"}
    return FetchResponse(
        url=url,
        status_code=status,
        headers=response_headers,
        body=body,
        fetched_at=local_now().isoformat(timespec="seconds"),
        retry_after=response_headers.get("retry-after"),
    )


def test_url_discovery_distinguishes_direct_listing_from_category():
    html = (FIXTURE_DIR / "search.html").read_bytes()
    urls = discover_listing_urls(
        html,
        page_url="https://fixture.test/search",
        domains=["fixture.test"],
        detail_path_regex=r"^/listing/[a-z0-9-]+$",
    )
    assert [(row.url_type, urlsplit(row.canonical_url).path) for row in urls] == [
        ("DIRECT_LISTING", "/listing/abc-001"),
        ("CATEGORY", "/nha-dat"),
    ]


def test_jsonld_and_visible_evidence_validate_price_area_and_target():
    candidate = extract_listing_detail(
        (FIXTURE_DIR / "listing.html").read_bytes(),
        target_rank=1,
        target_ward="Phường Trung Tâm",
        target_district="Quận Demo",
        target_province="Tỉnh Demo",
        source_url=LISTING_URL,
        source_id="abc-001",
        fetched_at="2026-10-14T08:00:00+07:00",
    )
    assert candidate["evidence_status"] == "SOURCE_VERIFIED"
    assert candidate["validity_status"] == "SOURCE_VERIFIED"
    assert candidate["property_type"] == "NHA_RIENG"
    assert candidate["price_vnd"] == 8_000_000_000
    assert candidate["area_m2"] == 100
    assert candidate["price_per_m2"] == 80_000_000
    assert candidate["area_basis"] == "FLOOR_AREA"
    assert candidate["source_url"] == LISTING_URL
    assert candidate["evidence"]["target_match"] is True


def test_geo_mismatch_and_expired_listing_are_not_verified():
    source = (FIXTURE_DIR / "listing.html").read_text(encoding="utf-8")
    wrong_ward = source.replace("Phường Trung Tâm", "Phường Khác")
    mismatch = extract_listing_detail(
        wrong_ward,
        target_rank=1,
        target_ward="Phường Trung Tâm",
        target_district="Quận Demo",
        target_province="Tỉnh Demo",
        source_url=LISTING_URL,
    )
    assert mismatch["validity_status"] == "GEO_MISMATCH"
    assert mismatch["evidence_status"] == "SOURCE_CONFLICT"

    expired_source = source.replace(
        '"datePosted": "2026-10-13"',
        '"datePosted": "2026-10-13", "availabilityEnds": "2020-01-01"',
    )
    expired = extract_listing_detail(
        expired_source,
        target_rank=1,
        target_ward="Phường Trung Tâm",
        target_district="Quận Demo",
        target_province="Tỉnh Demo",
        source_url=LISTING_URL,
    )
    assert expired["validity_status"] == "EXPIRED"
    assert expired["evidence_status"] == "EXPIRED"


def test_price_area_normalization_and_missing_evidence():
    assert parse_price_vnd("8,5 tỷ") == 8_500_000_000
    assert parse_area_m2("1.250,5 m²") == 1250.5
    assert parse_price_vnd("Thỏa thuận") is None
    assert parse_area_m2("không rõ") is None


def test_target_registry_uses_legacy_top50_rows_when_mapping_registry_is_empty(tmp_path):
    db = connect(tmp_path / "legacy-target.sqlite3")
    ensure_collection_schema(db)
    db.execute(
        """INSERT INTO ward_target_legacy(
             rank,old_province,old_district,old_ward,category,n_customers,pct,batch,
             current_province,current_ward,current_ward_code,status,mapping_note,source_url,imported_at
           ) VALUES(1,'Tỉnh Cũ','Quận Cũ','Phường A','PHƯỜNG',10,0.1,1,'','',NULL,
             'PENDING_ADMIN_MAPPING','','','2026-10-14')"""
    )
    db.commit()
    try:
        rows = collection_targets(db)
        assert len(rows) == 1
        assert rows[0].rank == 1
        assert rows[0].ward == "Phường A"
        assert rows[0].district == "Quận Cũ"
        assert rows[0].province == "Tỉnh Cũ"
        assert rows[0].administrative_unit_id is None
    finally:
        db.close()


def test_storage_deduplicates_same_source_and_quarantines_cross_source(tmp_path):
    db = _seed_collection_db(tmp_path / "storage.sqlite3")
    try:
        row = extract_listing_detail(
            (FIXTURE_DIR / "listing.html").read_bytes(),
            target_rank=1,
            target_ward="Phường Trung Tâm",
            target_district="Quận Demo",
            target_province="Tỉnh Demo",
            source_url=LISTING_URL,
            source_id="abc-001",
            fetched_at="2026-10-14T08:00:00+07:00",
        )
        first = store_candidate(db, run_id="run-a", source_id="batdongsan.com.vn", candidate=row, at="2026-10-14T08:00:00+07:00")
        second = store_candidate(db, run_id="run-b", source_id="batdongsan.com.vn", candidate=row, at="2026-10-14T09:00:00+07:00")
        assert first["inserted"] is True
        assert second["inserted"] is False
        assert db.execute("SELECT COUNT(*) FROM collection_candidates").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM collection_candidate_observations").fetchone()[0] == 1

        db.execute(
            "INSERT INTO collection_sources(source_id,display_name,base_url,robots_url,updated_at) VALUES('other','Other','https://other.test/','https://other.test/robots.txt','2026-10-14')"
        )
        other = dict(row)
        other["source_url"] = "https://other.test/listing/abc-001"
        other["canonical_url"] = other["source_url"]
        other["source_domain"] = "other.test"
        result = store_candidate(db, run_id="run-c", source_id="other", candidate=other, at="2026-10-14T10:00:00+07:00")
        assert result["possible_duplicate"] is True
        record = db.execute("SELECT validity_status,review_status FROM collection_candidates WHERE candidate_id=?", (result["candidate_id"],)).fetchone()
        assert tuple(record) == ("NEEDS_REVIEW", "NEEDS_REVIEW")
    finally:
        db.close()


def test_category_urls_are_audit_only_not_listing_identity(tmp_path):
    db = _seed_collection_db(tmp_path / "urls.sqlite3")
    try:
        from wardprice.collectors.models import DiscoveredUrl

        category = DiscoveredUrl("https://fixture.test/nha-dat", "https://fixture.test/nha-dat", "CATEGORY")
        assert store_discovered_url(db, run_id="run-a", source_id="batdongsan.com.vn", target_rank=1, item=category, at="2026-10-14T08:00:00+07:00")
        assert not store_discovered_url(db, run_id="run-a", source_id="batdongsan.com.vn", target_rank=1, item=category, at="2026-10-14T08:01:00+07:00")
        assert db.execute("SELECT COUNT(*) FROM collection_candidates").fetchone()[0] == 0
        assert db.execute("SELECT source_url_type FROM collection_discovered_urls").fetchone()[0] == "CATEGORY"
    finally:
        db.close()


def test_rejection_audit_is_idempotent(tmp_path):
    db = _seed_collection_db(tmp_path / "reject.sqlite3")
    try:
        db.execute(
            "INSERT INTO collection_runs(run_id,run_date,mode,status,started_at,selection_json,total_targets) VALUES('reject-run','2026-10-14','LIVE','RUNNING','2026-10-14T08:00:00+07:00','[1]',1)"
        )
        db.commit()
        payload = {"source_url": LISTING_URL}
        assert store_rejection(db, run_id="reject-run", source_id="batdongsan.com.vn", target_rank=1, at="2026-10-14T08:00:00+07:00", reason="BAD_SOURCE", raw_payload=payload)
        assert not store_rejection(db, run_id="reject-run", source_id="batdongsan.com.vn", target_rank=1, at="2026-10-14T08:01:00+07:00", reason="BAD_SOURCE", raw_payload=payload)
        assert db.execute("SELECT COUNT(*) FROM collection_rejections").fetchone()[0] == 1
    finally:
        db.close()


def test_dry_run_is_read_only_and_live_gate_blocks_unapproved_sources(tmp_path):
    db_path = tmp_path / "gated.sqlite3"
    db = connect(db_path)
    ensure_collection_schema(db)
    _insert_mapped_target(db)
    sync_registry(db)
    before = db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
    plan = plan_collection(db, ranks={1}, limit=3)
    assert plan["network_attempted"] is False
    assert db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == before
    db.close()

    db = connect(db_path)
    try:
        result = run_live_collection(db, ranks={1}, limit=3, max_requests=10, transport=lambda *_args, **_kwargs: pytest.fail("network must remain blocked"))
        assert result["status"] == "BLOCKED_NO_AUTHORIZED_SOURCE"
        assert result["network_attempted"] is False
        assert db.execute("SELECT COUNT(*) FROM collection_http_attempts").fetchone()[0] == 0
    finally:
        db.close()


def test_offline_transport_runs_end_to_end_and_is_idempotent(tmp_path):
    db = _seed_collection_db(tmp_path / "e2e.sqlite3")
    search_html = (FIXTURE_DIR / "search.html").read_bytes()
    listing_html = (FIXTURE_DIR / "listing.html").read_bytes()
    call_log = []

    def transport(url, *, timeout, headers):
        del timeout, headers
        call_log.append(url)
        path = urlsplit(url).path
        if path == "/robots.txt":
            return _response(url, b"User-agent: *\nAllow: /\n", headers={"content-type": "text/plain"})
        if path == "/search":
            return _response(url, search_html)
        if path == "/listing/abc-001":
            return _response(url, listing_html)
        return _response(url, b"", status=404)

    try:
        first = run_live_collection(db, ranks={1}, limit=1, max_requests=10, transport=transport, sleeper=lambda _seconds: None)
        assert first["status"] == "COMPLETED"
        assert first["requests_made"] == 3
        assert first["source_verified"] == 1
        assert first["new_listings"] == 1
        assert first["candidates_discovered"] == 1
        assert first["candidates_inserted"] == 1
        assert first["candidates_updated"] == 0
        assert first["candidates_deduplicated"] == 0
        assert first["candidates_found"] == 1  # legacy alias: newly inserted unique candidates
        assert first["observations_inserted"] == 1
        assert len(call_log) == 3
        assert db.execute("SELECT COUNT(*) FROM collection_candidates").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM listings WHERE included_in_stats=1").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM listing_observations").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM ward_price_statistics WHERE sample_count=1").fetchone()[0] == 1

        second = run_live_collection(db, ranks={1}, limit=3, max_requests=10, transport=transport, sleeper=lambda _seconds: None)
        assert second["candidates_found"] == 0
        assert second["candidates_discovered"] == 1
        assert second["candidates_inserted"] == 0
        assert second["candidates_updated"] == 0
        assert second["candidates_deduplicated"] == 1
        assert second["observations_inserted"] == 0
        assert second["observations_updated"] == 0
        assert second["observations_deduplicated"] == 1
        assert second["duplicates"] == 1
        assert db.execute("SELECT COUNT(*) FROM collection_candidates").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM listing_observations").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM collection_candidate_observations").fetchone()[0] == 1
        row = db.execute(
            "SELECT candidates_found,summary_json FROM collection_runs WHERE run_id=?",
            (second["run_id"],),
        ).fetchone()
        assert row["candidates_found"] == 0
        summary = json.loads(row["summary_json"])
        assert summary["candidates_discovered"] == 1
        assert summary["candidates_deduplicated"] == 1
        assert summary["attempt_metrics"][0]["observations_deduplicated"] == 1
        attempt = db.execute(
            "SELECT candidate_count,duplicate_count FROM collection_target_attempts WHERE run_id=?",
            (second["run_id"],),
        ).fetchone()
        assert tuple(attempt) == (1, 1)
    finally:
        db.close()


def test_resume_interrupted_run_and_refuse_second_active_writer(tmp_path):
    db = _seed_collection_db(tmp_path / "resume.sqlite3")
    now = local_now().isoformat(timespec="seconds")
    today = local_now().date().isoformat()
    selection = json.dumps([1])
    db.execute(
        """INSERT INTO collection_runs(run_id,run_date,mode,status,started_at,selection_json,total_targets)
           VALUES('interrupted',?,'LIVE','INTERRUPTED',?,?,1)""",
        (today, now, selection),
    )
    db.execute(
        """INSERT INTO collection_target_attempts(
             run_id,source_id,target_rank,started_at,finished_at,status
           ) VALUES('interrupted','batdongsan.com.vn',1,?,?,'NO_LISTINGS')""",
        (now, now),
    )
    db.commit()
    try:
        resumed = run_live_collection(
            db,
            ranks={1},
            limit=1,
            max_requests=10,
            resume=True,
            transport=lambda *_args, **_kwargs: pytest.fail("completed checkpoint should not refetch"),
        )
        assert resumed["run_id"] == "interrupted"
        assert resumed["resumed"] is True
        assert resumed["requests_made"] == 0

        db.execute("UPDATE collection_runs SET status='RUNNING',finished_at=NULL WHERE run_id='interrupted'")
        db.commit()
        with pytest.raises(RuntimeError, match="COLLECTION_ALREADY_RUNNING"):
            run_live_collection(db, ranks={1}, limit=1, max_requests=10, resume=True)
    finally:
        db.close()


def test_robots_policy_and_shared_request_budget_fail_closed():
    source = {
        "base_url": "https://fixture.test/",
        "robots_url": "https://fixture.test/robots.txt",
        "user_agent": "WardPriceDailyCollector/0.2",
        "daily_request_budget": 10,
        "crawl_delay_seconds": 0,
    }
    attempts = []
    blocked_client = RobotsAwareClient(
        source,
        transport=lambda url, **_kwargs: _response(url, b"User-agent: *\nDisallow: /private\n"),
        min_delay_seconds=0,
        sleeper=lambda _seconds: None,
        on_attempt=attempts.append,
        shared_budget={"remaining": 3},
    )
    with pytest.raises(CollectionBlocked, match="robots.txt disallows"):
        blocked_client.fetch("https://fixture.test/private/item")
    assert blocked_client.requests_made == 1
    assert len(attempts) == 1

    exhausted = RobotsAwareClient(
        source,
        transport=lambda *_args, **_kwargs: pytest.fail("budget should stop before transport"),
        min_delay_seconds=0,
        shared_budget={"remaining": 0},
    )
    with pytest.raises(CollectionBlocked, match="Global daily request budget exhausted"):
        exhausted.fetch("https://fixture.test/item")

    calls = []

    def rate_limited_transport(url, **_kwargs):
        calls.append(url)
        if urlsplit(url).path == "/robots.txt":
            return _response(url, b"User-agent: *\nAllow: /\n")
        return _response(url, b"blocked", status=429, headers={"retry-after": "120"})

    limited = RobotsAwareClient(
        source,
        transport=rate_limited_transport,
        min_delay_seconds=0,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(CollectionBlocked) as error:
        limited.fetch("https://fixture.test/item")
    assert error.value.code == "HTTP_429"
    assert len(calls) == 2  # robots.txt and one page request; no retry
    with pytest.raises(CollectionBlocked, match="Source cooldown is active"):
        limited.fetch("https://fixture.test/another")


def test_collection_monitoring_and_migration_backup_are_auditable(tmp_path):
    db_path = tmp_path / "backup.sqlite3"
    db = connect(db_path)
    _insert_mapped_target(db)
    db.close()
    backup = backup_database_before_collection_migration(db_path)
    assert backup is not None and backup.exists()

    db = connect(db_path)
    try:
        ensure_collection_schema(db)
        sync_registry(db)
        summary = monitoring_summary(db, run_date="2026-10-14")
        assert summary["target_count"] == 1
        assert summary["processed_target_count_today"] == 0
        assert summary["unprocessed_target_count_today"] == 1
        assert summary["scheduler_activation_by_pipeline"] == "NOT_ACTIVATED"
        assert source_readiness(db)["ready_count"] == 0
    finally:
        db.close()

    snapshot = connect(backup)
    try:
        assert not snapshot.execute(
            "SELECT 1 FROM sqlite_master WHERE name='collection_runs'"
        ).fetchone()
        assert snapshot.execute("SELECT COUNT(*) FROM priority_targets").fetchone()[0] == 1
    finally:
        snapshot.close()


def test_fixture_listing_candidate_has_sha256_lineage():
    row = extract_listing_detail(
        (FIXTURE_DIR / "listing.html").read_bytes(),
        target_rank=1,
        target_ward="Phường Trung Tâm",
        target_district="Quận Demo",
        target_province="Tỉnh Demo",
        source_url=LISTING_URL,
        fetched_at="2026-10-14T08:00:00+07:00",
    )
    assert len(row["evidence"]["content_sha256"]) == 64
    assert row["raw_payload"]["content_sha256"] == row["evidence"]["content_sha256"]
    assert json.loads(json.dumps(row["raw_payload"]))["source_url"] == LISTING_URL


def test_retry_after_source_cooldown_expires_in_readiness(tmp_path):
    db = _seed_collection_db(tmp_path / "cooldown.sqlite3")
    try:
        db.execute(
            "UPDATE collection_sources SET cooldown_until='2000-01-01T00:00:00+00:00' WHERE source_id='batdongsan.com.vn'"
        )
        db.commit()
        assert source_readiness(db)["ready_count"] == 1
        db.execute(
            "UPDATE collection_sources SET cooldown_until='2999-01-01T00:00:00+00:00' WHERE source_id='batdongsan.com.vn'"
        )
        db.commit()
        assert source_readiness(db)["ready_count"] == 0
    finally:
        db.close()


def test_scheduler_registration_script_requires_explicit_flags():
    script = (Path(__file__).parents[1] / "scripts" / "register_collector_task.ps1").read_text(encoding="utf-8")
    assert "[switch]$PilotPassed" in script
    assert "[switch]$Register" in script
    assert "if (-not $PilotPassed -or -not $Register)" in script
    assert "SE Asia Standard Time" in script
    assert "Register-ScheduledTask" in script


def test_cli_initializes_with_backup_and_dry_run_does_not_create_run(tmp_path, monkeypatch, capsys):
    from wardprice.__main__ import main

    database = tmp_path / "cli.sqlite3"
    db = connect(database)
    _insert_mapped_target(db)
    db.close()
    monkeypatch.setenv("WARDPRICE_DEMO_MODE", "false")
    monkeypatch.setattr(sys, "argv", ["wardprice", "collection-init", "--db", str(database)])
    main()
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["status"] == "INITIALIZED"
    assert initialized["backup"]
    assert Path(initialized["backup"]).is_file()
    assert initialized["top50_targets_loaded"] == 1

    db = connect(database)
    before = db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
    db.close()
    monkeypatch.setattr(sys, "argv", ["wardprice", "collect-daily", "--rank", "1", "--dry-run", "--db", str(database)])
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "DRY_RUN_ONLY"
    assert output["selected"] == 1
    assert output["network_attempted"] is False

    db = connect(database)
    try:
        assert db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == before
    finally:
        db.close()

    monkeypatch.setattr(sys, "argv", ["wardprice", "collection-report", "--db", str(database), "--output", str(tmp_path / "outputs")])
    main()
    report_result = json.loads(capsys.readouterr().out)
    assert Path(report_result["report_file"]).is_file()
    assert report_result["report"]["network_attempted"] is False

