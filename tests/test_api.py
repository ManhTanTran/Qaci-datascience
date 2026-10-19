"""FastAPI contracts against a temporary SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from wardprice.api import create_app
from wardprice.collectors.storage import ensure_collection_schema
from wardprice.database import connect
from wardprice.national_registry import import_admin_file

FIXTURE = Path(__file__).parent / "fixtures" / "nso_admin_fixture.xml"


def test_api_search_lookup_coverage_openapi_and_priority_privacy(tmp_path):
    database = tmp_path / "api.sqlite3"
    db = connect(database)
    try:
        db.execute(
            """INSERT INTO ward_target_legacy(
               rank,old_province,old_district,old_ward,category,n_customers,pct,batch,
               current_province,current_ward,status,mapping_note,source_url,imported_at
               ) VALUES(1,'Tỉnh Demo','Quận Cũ','Phường Cũ','PHƯỜNG',99,0.99,1,
                 'Tỉnh Demo','Phường Trung Tâm','REVIEWED_RESOLUTION','internal','',
                 '2026-10-01')"""
        )
        db.commit()
        import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/admin",
        )
    finally:
        db.close()

    client = TestClient(create_app(database))
    assert client.get("/api/v1/health").json()["external_provider_enabled"] is False

    search = client.get("/api/v1/administrative-units/search", params={"q": "00001"}).json()
    assert search["status"] == "FOUND"
    assert search["results"][0]["administrative_code"] == "00001"

    price = client.get("/api/v1/ward-prices/lookup", params={"q": "00001"}).json()
    assert price["status"] == "NO_PRICE_DATA"

    coverage = client.get("/api/v1/coverage").json()
    assert coverage["registry_status"] == "NATIONWIDE_REGISTRY_LOADED"
    assert coverage["administrative_coverage"]["commune_count"] == 3

    priority = client.get("/api/v1/priority-targets").json()
    assert priority["status"] == "FOUND"
    assert "n_customers" not in str(priority)
    assert '"pct"' not in str(priority)

    plan = client.get("/api/v1/collection-priorities", params={"limit": 3}).json()
    assert plan["tier_counts"]["P0"]["unit_count"] == 1
    assert plan["tier_counts"]["P2"]["unit_count"] == 2
    assert "n_customers" not in str(plan)
    assert '"pct"' not in str(plan)

    schema = client.get("/openapi.json").json()
    assert "/api/v1/administrative-units/search" in schema["paths"]
    assert "/api/v1/ward-prices/lookup" in schema["paths"]
    assert "/api/v1/collection-priorities" in schema["paths"]


def test_collection_monitoring_api_is_read_only_and_reports_initialization(tmp_path):
    database = tmp_path / "collection-api.sqlite3"
    db = connect(database)
    try:
        client = TestClient(create_app(database))
        uninitialized = client.get("/api/v1/collection/monitoring").json()
        assert uninitialized["status"] == "NOT_INITIALIZED"
        ensure_collection_schema(db)
        db.commit()
    finally:
        db.close()

    summary = TestClient(create_app(database)).get("/api/v1/collection/monitoring").json()
    assert summary["status"] == "OK"
    assert summary["network_attempted"] is False
    assert summary["scheduler_activation_by_pipeline"] == "NOT_ACTIVATED"


def test_province_search_shows_four_sources_and_stops_before_network_when_unapproved(tmp_path):
    pilot_database = tmp_path / "historical-pilot.sqlite3"
    with sqlite3.connect(pilot_database) as pilot:
        pilot.executescript(
            """
            CREATE TABLE historical_dataset_registry(
                dataset_id TEXT, revision TEXT, retrieved_at TEXT
            );
            CREATE TABLE historical_target_registry(
                target_rank INTEGER, original_ward TEXT, original_district TEXT,
                original_province TEXT, source_reference TEXT
            );
            CREATE TABLE historical_candidates(
                candidate_id TEXT, target_rank INTEGER, dataset_id TEXT,
                dataset_revision TEXT, candidate_status TEXT, deal_type TEXT,
                dedupe_classification TEXT, deal_classification TEXT
            );
            INSERT INTO historical_dataset_registry VALUES(
                'tinixai/vietnam-real-estates','rev-test','2026-10-19'
            );
            INSERT INTO historical_target_registry VALUES(
                1,'Phường Demo','Quận Demo','Tỉnh Demo','fixture'
            );
            """
        )

    collection_database = tmp_path / "collection.sqlite3"
    client = TestClient(create_app(
        collection_database,
        historical_pilot_db_path=pilot_database,
    ))

    readiness = client.get(
        "/api/v1/collection/province-search/readiness",
        params={"province": "tinh demo"},
    )
    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["target_count"] == 1
    assert len(readiness_body["sources"]) == 4
    assert all(source["status"] == "BLOCKED" for source in readiness_body["sources"])
    assert readiness_body["network_attempted"] is False

    search = client.post(
        "/api/v1/collection/province-search",
        json={"province": "Tỉnh Demo"},
    )
    assert search.status_code == 200
    search_body = search.json()
    assert search_body["status"] == "BLOCKED_NO_AUTHORIZED_SOURCE"
    assert search_body["target_count"] == 1
    assert len(search_body["sources"]) == 4
    assert search_body["network_attempted"] is False
    assert search_body["database_written"] is False
    assert not collection_database.exists()
