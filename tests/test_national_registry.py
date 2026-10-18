"""Offline tests for versioned national administrative data and local lookup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wardprice.database import connect
from wardprice.national_registry import (
    import_admin_file,
    import_crosswalk_csv,
    lookup_ward_price,
    national_coverage,
    search_administrative_units,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nso_admin_fixture.xml"


def _insert_legacy_target(db):
    db.execute(
        """INSERT INTO ward_target_legacy(
           rank,old_province,old_district,old_ward,category,n_customers,pct,batch,
           current_province,current_ward,current_ward_code,status,mapping_note,source_url,
           imported_at
           ) VALUES(1,?,?,?,?,?,?,?,?,?,NULL,'REVIEWED_RESOLUTION',?,?,?)""",
        (
            "Tỉnh Demo",
            "Quận Cũ",
            "Phường Cũ",
            "PHƯỜNG",
            17,
            0.17,
            1,
            "Tỉnh Demo",
            "Phường Trung Tâm",
            "reviewed in imported legacy mapping",
            "https://example.org/crosswalk",
            "2026-10-01T00:00:00+00:00",
        ),
    )
    db.commit()


def test_import_is_idempotent_and_keeps_top50_mapping_separate(tmp_path):
    db = connect(tmp_path / "national.sqlite3")
    try:
        _insert_legacy_target(db)
        before = dict(db.execute("SELECT * FROM ward_target_legacy WHERE rank=1").fetchone())
        first = import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/admin",
        )
        second = import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/admin",
        )

        assert first["commune_count"] == 3
        assert first["province_count"] == 2
        assert second["record_count"] == first["record_count"]
        assert db.execute(
            "SELECT COUNT(*) FROM administrative_units WHERE administrative_level='COMMUNE'"
        ).fetchone()[0] == 3
        assert dict(db.execute("SELECT * FROM ward_target_legacy WHERE rank=1").fetchone()) == before
        assert db.execute("SELECT COUNT(*) FROM priority_targets").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM priority_target_mappings").fetchone()[0] == 1

        by_code = search_administrative_units(db, "00001")
        by_plain_name = search_administrative_units(db, "phuong trung tam", province="tinh demo")
        by_old_name = search_administrative_units(db, "Phường Cũ", include_historical=True)
        assert by_code[0]["administrative_code"] == "00001"
        assert by_plain_name[0]["name"] == "Phường Trung Tâm"
        assert by_old_name[0]["matched_alias"] == "Phường Cũ"
        assert lookup_ward_price(db, target_rank=1)["status"] == "NO_PRICE_DATA"
        assert national_coverage(db)["administrative_coverage"]["commune_count"] == 3
    finally:
        db.close()


def test_duplicate_names_across_provinces_are_ambiguous(tmp_path):
    db = connect(tmp_path / "ambiguous.sqlite3")
    try:
        import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/admin",
        )
        matches = search_administrative_units(db, "Xa Trung")
        assert len(matches) == 2
        assert lookup_ward_price(db, "Xã Trùng")["status"] == "AMBIGUOUS"
        assert lookup_ward_price(db, "Xã Trùng", province="Tỉnh Demo")["status"] == "NO_PRICE_DATA"
    finally:
        db.close()


def test_old_snapshot_is_retained_but_never_becomes_current_implicitly(tmp_path):
    db = connect(tmp_path / "versions.sqlite3")
    try:
        historical = import_admin_file(
            db,
            FIXTURE,
            as_of_date="2024-12-31",
            is_current=False,
            source_reference="https://official.example/history",
        )
        coverage = national_coverage(db)
        assert historical["is_current"] is False
        assert coverage["registry_status"] == "NATIONWIDE_READY_AWAITING_DATA"
        assert coverage["administrative_coverage"]["historical_commune_count"] == 3
        import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/current",
        )
        with pytest.raises(ValueError, match="older than the current registry"):
            import_admin_file(
                db,
                FIXTURE,
                as_of_date="2024-12-31",
                is_current=True,
                source_reference="https://official.example/history",
            )
    finally:
        db.close()


def test_partial_transfer_crosswalk_stays_unresolved(tmp_path):
    csv_path = tmp_path / "crosswalk.csv"
    csv_path.write_text(
        "alias_name,province_name,district_name_legacy,target_code,relationship_type,"
        "mapping_status,effective_date,source_reference\n"
        "Xã Trùng,Tỉnh Demo,Quận Cũ,00001,PARTIAL_TRANSFER,"
        "PARTIAL_TRANSFER_UNRESOLVED,2025-07-01,https://official.example/resolution\n",
        encoding="utf-8",
    )
    db = connect(tmp_path / "crosswalk.sqlite3")
    try:
        import_admin_file(
            db,
            FIXTURE,
            as_of_date="2025-07-01",
            is_current=True,
            source_reference="https://official.example/admin",
        )
        result = import_crosswalk_csv(
            db,
            csv_path,
            source_reference="https://official.example/crosswalk",
        )
        alias = search_administrative_units(
            db, "Xã Trùng", province="Tỉnh Demo", include_historical=True
        )
        assert result["unresolved_aliases"] == 1
        assert db.execute("SELECT COUNT(*) FROM administrative_relationships").fetchone()[0] == 1
        unresolved = [item for item in alias if item.get("mapping_status") == "PARTIAL_TRANSFER_UNRESOLVED"]
        assert len(unresolved) == 1
        assert unresolved[0]["unit_id"] is None
        assert lookup_ward_price(
            db, "Xã Trùng", province="Tỉnh Demo"
        )["status"] == "AMBIGUOUS"
    finally:
        db.close()


def test_migration_adds_schema_without_changing_existing_rows(tmp_path):
    path = tmp_path / "pre-migration.sqlite3"
    raw = sqlite3.connect(path)
    raw.executescript(
        """CREATE TABLE ward_target_legacy(
               rank INTEGER PRIMARY KEY,old_province TEXT,old_district TEXT,old_ward TEXT,
               category TEXT,n_customers INTEGER,pct REAL,batch INTEGER,current_province TEXT,
               current_ward TEXT,current_ward_code TEXT,status TEXT,mapping_note TEXT,
               source_url TEXT,imported_at TEXT);
           INSERT INTO ward_target_legacy VALUES(1,'P','D','W','PHƯỜNG',17,0.17,1,'P','W',NULL,
               'PENDING_ADMIN_MAPPING','','','2026-10-01');
           CREATE TABLE listings(
               listing_id TEXT PRIMARY KEY,identity_key TEXT UNIQUE,identity_fingerprint TEXT,
               ward_code TEXT,ward_name TEXT,province TEXT,property_type TEXT,price_vnd REAL,
               area_m2 REAL,price_per_m2 REAL,address TEXT,source_url TEXT,source_domain TEXT,
               listed_date TEXT,collected_at TEXT,last_seen_at TEXT,evidence_status TEXT,
               evidence_excerpt TEXT,raw_payload TEXT,active INTEGER,included_in_stats INTEGER);
           INSERT INTO listings VALUES('L1','K','F','W1','W','P','DAT_O',100,20,5,'A',
               'https://example.org/1','example.org',NULL,'2026-10-01','2026-10-01',
               'UNVERIFIED','','{}',1,0);"""
    )
    raw.commit()
    raw.close()

    db = connect(path)
    try:
        legacy = dict(db.execute("SELECT * FROM ward_target_legacy WHERE rank=1").fetchone())
        listing = dict(db.execute("SELECT * FROM listings WHERE listing_id='L1'").fetchone())
        assert legacy["n_customers"] == 17
        assert legacy["pct"] == 0.17
        assert listing["price_vnd"] == 100
        assert listing["validation_status"] == "LEGACY_UNREVIEWED"
        assert "administrative_units" in {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        db.close()
