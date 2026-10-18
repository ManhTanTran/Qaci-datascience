"""Offline acceptance tests for the isolated 500-record synthetic demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wardprice.api import create_app
from wardprice.config import Settings
from wardprice.database import connect
from wardprice.demo import (
    FIXTURE_DIR,
    DemoImportError,
    demo_database,
    demo_history,
    demo_lookup,
    import_demo_batch,
    open_demo_db,
    run_demo_scheduler,
    validate_demo_database,
)
from wardprice.price_warehouse import prepare_listing_import


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("WARDPRICE_DEMO_MODE", "1")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("WARDPRICE_DB_PATH", raising=False)


def fresh_db(path: Path):
    return open_demo_db(path)


def test_demo_mode_defaults_to_separate_database_and_blocks_production_path(
    demo_env, monkeypatch, tmp_path
):
    assert Settings.from_env().database_path.name == "ward_prices.demo.sqlite3"
    monkeypatch.setenv("WARDPRICE_DB_PATH", str(tmp_path / "ward_prices.sqlite3"))
    with pytest.raises(ValueError, match="requires state/ward_prices.demo.sqlite3"):
        _ = Settings.from_env().database_path
    with pytest.raises(DemoImportError, match="production database path"):
        open_demo_db(Path(__file__).parents[1] / "state" / "ward_prices.sqlite3")


def test_synthetic_records_are_rejected_without_demo_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("WARDPRICE_DEMO_MODE", "0")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    with pytest.raises(DemoImportError, match="require WARDPRICE_DEMO_MODE"):
        open_demo_db(tmp_path / "blocked.sqlite3")


def test_import_500_records_counts_targets_types_and_expected_statistics(demo_env, tmp_path):
    database = tmp_path / "demo.sqlite3"
    with demo_database(database) as db:
        results = [
            import_demo_batch(db, FIXTURE_DIR / "batches" / f"demo_group_{index:02d}_50.json")
            for index in range(1, 11)
        ]
        report = validate_demo_database(db)
        assert sum(result["inserted"] for result in results) == 500
        assert report["target_count"] == 50
        assert report["wards_with_data"] == 50
        assert report["listings"] == 500
        assert report["daily_observations"] == 500
        assert report["property_type_counts"] == {
            "DAT_O": 200,
            "NHA_RIENG": 200,
            "CHUNG_CU": 100,
        }
        assert report["statistics_expected_groups"] == 150
        assert report["sqlite_integrity"] == "ok"
        assert report["target_mapping_mismatches"] == 0
        assert report["price_calculation_mismatches"] == 0
        assert report["lineage_missing"] == 0
        assert report["foreign_key_errors"] == 0
        assert db.execute("SELECT COUNT(DISTINCT target_rank) FROM demo_listings").fetchone()[0] == 50
        assert db.execute("SELECT COUNT(DISTINCT ward_code) FROM demo_listings").fetchone()[0] == 50
        assert db.execute(
            "SELECT COUNT(*) FROM demo_listings WHERE price_per_m2 != price_vnd/area_m2"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM demo_daily_observations WHERE evidence_status!='UNVERIFIED'"
        ).fetchone()[0] == 0
        columns = {row[1] for row in db.execute("PRAGMA table_info(demo_listings)")}
        assert {
            "listing_id",
            "ward_code",
            "ward_name",
            "province",
            "property_type",
            "price_vnd",
            "area_m2",
            "price_per_m2",
            "source_url",
            "source_domain",
            "collected_at",
            "evidence_status",
            "raw_payload",
            "first_import_run_id",
            "last_import_run_id",
        } <= columns
        assert db.execute("SELECT COUNT(*) FROM demo_listings WHERE source_domain IS NOT NULL").fetchone()[0] == 0
        first = db.execute(
            "SELECT * FROM demo_statistics WHERE target_rank=1 AND property_type='DAT_O'"
        ).fetchone()
        assert first["listing_count"] == first["sample_count"] == 4
        assert first["mean_price_per_m2"] == pytest.approx(71_998_936.17)
        assert first["median_price_per_m2"] == pytest.approx(71_500_000.0)
        raw = json.loads(db.execute("SELECT raw_payload FROM demo_listings LIMIT 1").fetchone()[0])
        assert raw["source_website"] == "DEMO_SYNTHETIC"


def test_replay_is_idempotent_and_exact_duplicates_do_not_add_observations(demo_env, tmp_path):
    with demo_database(tmp_path / "demo.sqlite3") as db:
        first = import_demo_batch(db, FIXTURE_DIR / "batches" / "demo_group_01_50.json")
        second = import_demo_batch(db, FIXTURE_DIR / "batches" / "demo_group_01_50.json")
        replay = import_demo_batch(db, FIXTURE_DIR / "replay_rank01_duplicate_test.json")
        assert first["inserted"] == 50
        assert second["duplicates_exact"] == 50
        assert replay["duplicates_exact"] == 10
        assert second["observations_added"] == replay["observations_added"] == 0
        assert db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0] == 50
        assert db.execute("SELECT COUNT(*) FROM demo_daily_observations").fetchone()[0] == 50


def test_500_listing_cap_rejects_whole_overflow_batch(demo_env, tmp_path):
    fixture = json.loads((FIXTURE_DIR / "wardpricedaily_demo500_all.json").read_text(encoding="utf-8"))
    payload = dict(fixture)
    payload["listings"] = [dict(row) for row in fixture["listings"]]
    extra = dict(payload["listings"][0])
    extra["title"] += " EXTRA UNIQUE"
    extra["address"] += " EXTRA UNIQUE"
    payload["listings"].append(extra)
    payload["actual_collected"] = 501
    with demo_database(tmp_path / "demo.sqlite3") as db:
        with pytest.raises(DemoImportError, match="cap is 500"):
            import_demo_batch(db, payload)
        assert db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0] == 0
        assert db.execute("SELECT status FROM demo_import_runs").fetchone()[0] == "REJECTED"


def test_rank_whitelist_and_legacy_mapping_are_enforced(demo_env, tmp_path):
    payload = json.loads(
        (FIXTURE_DIR / "batches" / "demo_group_01_50.json").read_text(encoding="utf-8")
    )
    payload["listings"][0]["target_rank"] = 2
    with demo_database(tmp_path / "demo.sqlite3") as db:
        with pytest.raises(DemoImportError, match="configured ward whitelist"):
            import_demo_batch(db, payload)
        assert db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0] == 0


def test_price_history_and_daily_refresh_persist(demo_env, tmp_path):
    payload = json.loads(
        (FIXTURE_DIR / "batches" / "demo_group_01_50.json").read_text(encoding="utf-8")
    )
    with demo_database(tmp_path / "demo.sqlite3") as db:
        import_demo_batch(db, payload)
        refreshed = json.loads(json.dumps(payload))
        refreshed["group_id"] = "next-day-refresh"
        refreshed["listings"][0]["collected_at"] = "2026-10-15"
        result = import_demo_batch(db, refreshed)
        assert result["updated"] == 0
        assert result["duplicates_exact"] == 50
        assert result["observations_added"] == 1
        history = demo_history(db, 1, property_type="DAT_O")
        assert len(history["observations"]) == 5
        assert {row["observation_date"] for row in history["observations"]} == {
            "2026-10-14",
            "2026-10-15",
        }


def test_demo_lookup_in_and_outside_top50(demo_env, tmp_path):
    with demo_database(tmp_path / "demo.sqlite3") as db:
        for index in range(1, 11):
            import_demo_batch(db, FIXTURE_DIR / "batches" / f"demo_group_{index:02d}_50.json")
        for ward in ("Phường Bình Hưng Hòa", "Phường Đại Kim", "Phường Hiệp Bình Chánh"):
            result = demo_lookup(db, ward)
            assert result["status"] == "FOUND"
            assert result["targets"][0]["statistics"]
        assert demo_lookup(db, "Phường Ngoài Top 50")["status"] == "NOT_IN_TOP50"
        filtered = demo_lookup(db, "Phường Đại Kim", property_type="CHUNG_CU")
        assert [row["property_type"] for row in filtered["targets"][0]["statistics"]] == ["CHUNG_CU"]


def test_scheduler_failure_resume_and_idempotency(demo_env, tmp_path):
    database = tmp_path / "demo.sqlite3"
    failed = run_demo_scheduler(database, schedule_id="test-day", fail_after_batch=5)
    assert failed["status"] == "FAILED"
    assert failed["last_group_index"] == 5
    assert failed["coverage"]["listings"] == 250
    assert failed["network_called"] is False
    resumed = run_demo_scheduler(database, schedule_id="test-day")
    assert resumed["status"] == "SUCCEEDED"
    assert resumed["resumed_from_group"] == 5
    assert resumed["groups_processed"] == 5
    assert resumed["coverage"]["listings"] == 500
    rerun = run_demo_scheduler(database, schedule_id="second-day")
    assert rerun["status"] == "SUCCEEDED"
    assert rerun["coverage"]["listings"] == 500
    with demo_database(database) as db:
        assert db.execute("SELECT COUNT(*) FROM demo_listings").fetchone()[0] == 500
        assert db.execute("SELECT COUNT(*) FROM demo_daily_observations").fetchone()[0] == 500
        assert db.execute(
            "SELECT SUM(duplicates) FROM demo_import_runs WHERE status='SUCCEEDED'"
        ).fetchone()[0] == 500
    repeated_same_id = run_demo_scheduler(database, schedule_id="test-day")
    assert repeated_same_id["groups_processed"] == 0


def test_demo_api_reads_only_demo_database(demo_env, tmp_path):
    database = tmp_path / "demo.sqlite3"
    with demo_database(database) as db:
        for index in range(1, 11):
            import_demo_batch(db, FIXTURE_DIR / "batches" / f"demo_group_{index:02d}_50.json")
    client = TestClient(create_app(database, demo_mode=True))
    assert client.get("/api/v1/health").json()["demo_mode"] is True
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Sổ tay giá" in dashboard.text
    assert client.get("/assets/dashboard.css").status_code == 200
    ward_registry = client.get("/api/v1/demo/wards").json()["targets"]
    assert len(ward_registry) == 50
    assert sum(row["listing_count"] for row in ward_registry) == 500
    coverage = client.get("/api/v1/demo/coverage").json()
    assert coverage["listings"] == 500
    lookup = client.get(
        "/api/v1/demo/lookup", params={"q": "Phường Hiệp Bình Chánh", "property_type": "NHA_RIENG"}
    ).json()
    assert lookup["status"] == "FOUND"
    assert lookup["targets"][0]["statistics"][0]["sample_count"] == 4
    history = client.get("/api/v1/demo/history", params={"target_rank": 2}).json()
    assert len(history["observations"]) == 10
    assert history["synthetic"] is True


def test_canonical_warehouse_never_accepts_synthetic_fixture(demo_env, tmp_path):
    payload = json.loads(
        (FIXTURE_DIR / "batches" / "demo_group_01_50.json").read_text(encoding="utf-8")
    )
    db = connect(tmp_path / "canonical.sqlite3")
    try:
        with pytest.raises(ValueError, match="isolated wardprice.demo importer"):
            prepare_listing_import(db, payload)
        assert db.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0
    finally:
        db.close()
