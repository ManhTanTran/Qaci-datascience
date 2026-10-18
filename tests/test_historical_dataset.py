import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wardprice.api import create_app
from wardprice.historical_dataset import (
    DATASET_ID,
    LICENSE_ID,
    HistoricalDatasetImporter,
    _deal_type,
    _property_type,
    _sample_quality_level,
    pilot_lookup,
    plan_import,
    refresh_title_supported_property_mappings,
)


def _targets():
    targets = [
        {
            "target_rank": rank,
            "original_ward": f"Phường Mẫu {rank}",
            "original_district": "Quận Mẫu",
            "original_province": "Thành phố Mẫu",
            "source_reference": "test fixture",
        }
        for rank in range(1, 51)
    ]
    targets[0].update(
        {
            "original_ward": "Phường An Lạc",
            "original_district": "Quận Bình Tân",
            "original_province": "Thành phố Hồ Chí Minh",
        }
    )
    return targets


def _row(row_index, *, title="Bán nhà riêng ở An Lạc", property_type="Nhà", price=5_000_000_000):
    return {
        "source_row_index": row_index,
        "name": title,
        "property_type_name": property_type,
        "province_name": "Hồ Chí Minh",
        "district_name": "Bình Tân",
        "ward_name": "An Lạc",
        "street_name": "Đường Mẫu",
        "project_name": None,
        "price": price,
        "area": 50.0,
        "published_at": "2025-03-04T09:00:00Z",
    }


def _metadata(sample_rows):
    return {
        "dataset_id": DATASET_ID,
        "revision": "test-revision",
        "license_id": LICENSE_ID,
        "private": False,
        "gated": False,
        "full_dataset_downloaded": False,
        "commercial_use": False,
        "sample_rows": sample_rows,
        "split_rows_reported": 3_500_744,
        "sample_method": "offline fixture",
        "retrieved_at": "2026-10-14T00:00:00+00:00",
        "schema": [
            {"name": field}
            for field in (
                "name", "property_type_name", "province_name", "district_name", "ward_name",
                "price", "area", "published_at",
            )
        ],
    }


def _write_inputs(tmp_path, rows):
    sample_path = tmp_path / "sample.jsonl"
    sample_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    metadata_path = tmp_path / "sample.metadata.json"
    metadata_path.write_text(
        json.dumps(_metadata(len(rows)), ensure_ascii=False), encoding="utf-8"
    )
    targets_db = tmp_path / "targets.sqlite3"
    connection = sqlite3.connect(targets_db)
    connection.execute(
        """CREATE TABLE priority_targets(
             target_rank INTEGER PRIMARY KEY,original_ward TEXT,original_district TEXT,
             original_province TEXT,source_reference TEXT)"""
    )
    connection.executemany(
        "INSERT INTO priority_targets VALUES(?,?,?,?,?)",
        [
            (
                target["target_rank"], target["original_ward"], target["original_district"],
                target["original_province"], target["source_reference"],
            )
            for target in _targets()
        ],
    )
    connection.commit()
    connection.close()
    return sample_path, metadata_path, targets_db


def test_transaction_and_property_classification_are_conservative():
    assert _deal_type("Căn hộ có ban công, nội thất cơ bản") == "UNCLASSIFIED"
    assert _deal_type("Chính chủ cần bán căn hộ") == "EXPLICIT_SALE"
    assert _deal_type("Cho thuê nhà riêng") == "EXPLICIT_RENT"
    assert _deal_type("Cần bán hoặc cho thuê nhà") == "AMBIGUOUS"
    assert _property_type("Căn hộ chung cư") == ("CHUNG_CU", None)
    assert _property_type("Đất") == (None, "LAND_UNSPECIFIED")
    assert _property_type("Đất", "Bán đất thổ cư tại An Lạc") == (
        "DAT_O",
        "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED",
    )
    assert _property_type("Đất", "Bán đất nền tại An Lạc") == (None, "LAND_UNSPECIFIED")
    assert _property_type("Đất", "Bán đất nông nghiệp, có thổ cư") == (None, "LAND_UNSPECIFIED")
    assert _property_type("Đất", "Bán thửa đất ODT 1439m2") == (None, "LAND_UNSPECIFIED")
    assert _property_type("Biệt thự/Nhà liền kề", "Bán đất thổ cư") == (
        None,
        "HOUSE_SUBTYPE_REVIEW",
    )
    assert [_sample_quality_level(n) for n in (0, 4, 5, 9, 10)] == [
        "INSUFFICIENT_SAMPLE",
        "INSUFFICIENT_SAMPLE",
        "LOW_CONFIDENCE",
        "LOW_CONFIDENCE",
        "DESCRIPTIVE_SAMPLE",
    ]


def test_plan_matches_full_legacy_geography_and_deduplicates_content():
    first = _row(1)
    duplicate = {**first, "source_row_index": 2}
    rows = [
        first,
        duplicate,
        _row(3, title="Cho thuê căn hộ tại An Lạc", property_type="Căn hộ chung cư"),
        _row(4, title="Căn hộ có ban công tại An Lạc", property_type="Căn hộ chung cư"),
        _row(5, title="Bán đất ở An Lạc", property_type="Đất"),
        _row(6, title="Bán nhà ngoài whitelist", price=8_000_000_000)
        | {"province_name": "Đà Nẵng", "district_name": "Hải Châu", "ward_name": "Hải Châu 1"},
        _row(7, price=None),
    ]
    plan = plan_import(rows, _targets(), _metadata(len(rows)))
    summary = plan["summary"]
    assert summary["matched_top50_rows"] == 6
    assert summary["rejected_outside_top50"] == 1
    assert summary["quarantined_invalid_core_fields"] == 1
    assert summary["duplicate_content_rows"] == 1
    assert summary["unique_candidates_to_import"] == 4
    assert summary["eligible_historical_sales"] == 2
    assert summary["explicit_rent_candidates"] == 1
    assert summary["unclassified_transaction_candidates"] == 1
    assert summary["unmapped_property_candidates"] == 0
    assert summary["matched_target_ranks"] == [1]
    assert all(item["target_rank"] in {None, 1} for item in plan["source_rows"])


def test_historical_import_is_separate_and_idempotent(tmp_path):
    rows = [
        _row(1),
        {**_row(1), "source_row_index": 2},
        _row(3, title="Cho thuê căn hộ tại An Lạc", property_type="Căn hộ chung cư"),
        _row(4, title="Căn hộ có ban công tại An Lạc", property_type="Căn hộ chung cư"),
        _row(5, title="Bán đất ở An Lạc", property_type="Đất"),
        _row(6, title="Bán nhà ngoài whitelist")
        | {"province_name": "Đà Nẵng", "district_name": "Hải Châu", "ward_name": "Hải Châu 1"},
        _row(7, price=None),
    ]
    sample, metadata, targets_db = _write_inputs(tmp_path, rows)
    pilot_db = tmp_path / "pilot.sqlite3"

    importer = HistoricalDatasetImporter(targets_db, pilot_db)
    dry = importer.dry_run(sample, metadata)
    assert dry["pilot_database_written"] is False
    assert not pilot_db.exists()

    first = importer.import_batch(sample, metadata)
    assert first["summary"]["candidate_count_after_import"] == 4
    assert first["summary"]["observation_count_after_import"] == 4
    assert first["summary"]["statistics_eligible_candidates"] == 2
    assert first["summary"]["quarantined_invalid_core_fields"] == 1

    lookup = pilot_lookup(pilot_db, 1, "NHA_RIENG")
    assert lookup["statistics_eligible_count"] == 1
    assert lookup["mean_price_per_m2"] == pytest.approx(100_000_000)
    assert lookup["median_price_per_m2"] == pytest.approx(100_000_000)
    assert lookup["statistics_by_property_type"][0]["sample_quality_level"] == "INSUFFICIENT_SAMPLE"
    assert lookup["monthly_statistics"][0]["sample_quality_level"] == "INSUFFICIENT_SAMPLE"
    assert lookup["candidates"][0]["evidence_status"] == "HISTORICAL_DATASET_UNVERIFIED"

    second = importer.import_batch(sample, metadata)
    assert second["summary"]["replayed_source_rows"] == len(rows)
    assert second["summary"]["unique_candidates_to_import"] == 0
    assert second["summary"]["candidate_count_after_import"] == 4
    assert second["summary"]["observation_count_after_import"] == 4

    connection = sqlite3.connect(pilot_db)
    try:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "historical_candidates" in names
        assert "historical_observations" in names
        assert "historical_monthly_statistics" in names
        assert "listings" not in names
        assert "listing_observations" not in names
        assert "ward_price_statistics" not in names
        assert connection.execute("SELECT COUNT(*) FROM historical_target_registry").fetchone()[0] == 50
        assert connection.execute("SELECT COUNT(*) FROM historical_import_runs").fetchone()[0] == 2
        assert connection.execute(
            "SELECT commercial_use,full_dataset_downloaded FROM historical_dataset_registry"
        ).fetchone() == (0, 0)
    finally:
        connection.close()


def test_refresh_title_supported_property_mapping_is_backed_up_and_idempotent(tmp_path):
    legacy_row = _row(1, title="Bán đất nền ở An Lạc", property_type="Đất")
    sample, metadata, targets_db = _write_inputs(tmp_path, [legacy_row])
    pilot_db = tmp_path / "pilot.sqlite3"
    HistoricalDatasetImporter(targets_db, pilot_db).import_batch(sample, metadata)

    connection = sqlite3.connect(pilot_db)
    candidate = connection.execute(
        "SELECT candidate_id,raw_payload FROM historical_candidates"
    ).fetchone()
    raw_payload = json.loads(candidate[1])
    raw_payload["name"] = "Bán đất thổ cư ở An Lạc"
    connection.execute(
        "UPDATE historical_candidates SET title=?,raw_payload=? WHERE candidate_id=?",
        (raw_payload["name"], json.dumps(raw_payload, ensure_ascii=False), candidate[0]),
    )
    connection.commit()
    connection.close()

    refreshed = refresh_title_supported_property_mappings(pilot_db)

    assert refreshed["candidates_reclassified"] == 1
    assert refreshed["backup_integrity_check"] == "ok"
    assert (tmp_path / "backups").is_dir()
    assert Path(refreshed["backup_path"]).is_file()
    assert refreshed["statistics_eligible_count_after"] == 1
    assert refreshed["monthly_statistics_groups_after"] == 1
    connection = sqlite3.connect(pilot_db)
    row = connection.execute(
        "SELECT property_type,candidate_status,evidence_status,review_reason "
        "FROM historical_candidates"
    ).fetchone()
    assert row[0] == "DAT_O"
    assert row[1] == "ELIGIBLE_HISTORICAL_SALE"
    assert row[2] == "HISTORICAL_DATASET_UNVERIFIED"
    assert "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED" in row[3]
    connection.close()

    replay = refresh_title_supported_property_mappings(pilot_db)
    assert replay["candidates_reclassified"] == 0
    assert replay["statistics_eligible_count_after"] == 1


def test_historical_ui_and_api_only_serve_pilot_data(tmp_path):
    sample, metadata, targets_db = _write_inputs(tmp_path, [_row(1)])
    pilot_db = tmp_path / "pilot.sqlite3"
    HistoricalDatasetImporter(targets_db, pilot_db).import_batch(sample, metadata)
    app = create_app(
        db_path=tmp_path / "current.sqlite3",
        historical_pilot_db_path=pilot_db,
    )

    with TestClient(app) as client:
        page = client.get("/historical-pilot")
        assert page.status_code == 200
        assert "NGHIÊN CỨU · PHI THƯƠNG MẠI" in page.text
        assert "CC BY-NC 4.0" in page.text
        script = client.get("/assets/historical-pilot.js?v=20261015-e4a")
        assert script.status_code == 200
        assert "INSUFFICIENT_SAMPLE" in script.text
        assert "chưa xác minh quyền sử dụng" in script.text
        assert 'const showMean = Number(row.sample_count) >= 5;' in script.text
        assert "Ẩn trung bình vì cỡ mẫu dưới 5" in script.text

        overview = client.get("/api/v1/research/historical/overview")
        assert overview.status_code == 200
        assert overview.json()["research_only"] is True
        assert overview.json()["current_verified"] is False
        assert overview.json()["ai_context_enabled"] is False

        targets = client.get("/api/v1/research/historical/targets")
        assert targets.status_code == 200
        assert len(targets.json()["targets"]) == 50

        lookup = client.get(
            "/api/v1/research/historical/lookup",
            params={"target_rank": 1, "property_type": "NHA_RIENG"},
        )
        assert lookup.status_code == 200
        assert lookup.json()["statistics_eligible_count"] == 1
        assert lookup.json()["candidates"][0]["evidence_status"] == "HISTORICAL_DATASET_UNVERIFIED"
        assert lookup.json()["statistics_by_property_type"][0]["sample_quality_level"] == "INSUFFICIENT_SAMPLE"
        assert lookup.json()["monthly_statistics"][0]["sample_quality_level"] == "INSUFFICIENT_SAMPLE"

        all_types = client.get(
            "/api/v1/research/historical/lookup", params={"target_rank": 1}
        ).json()
        assert all_types["mean_price_per_m2"] is None
        assert {row["property_type"] for row in all_types["statistics_by_property_type"]} == {
            "NHA_RIENG"
        }
