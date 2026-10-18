import csv
import json

import pytest

from wardprice.historical_review_e5 import (
    _classification_packet_rows,
    _property_review_rows,
    _sensitivity_report,
    source_row_id,
    validate_property_review_csv,
)


def _candidate(
    candidate_id,
    *,
    target_rank=1,
    title="Bán nhà riêng",
    property_type="NHA_RIENG",
    property_type_raw="Nhà",
    review_reason=None,
    raw_payload=None,
    price_per_m2=100.0,
):
    return {
        "candidate_id": candidate_id,
        "target_rank": target_rank,
        "original_ward": f"Phường thử {target_rank}",
        "original_district": "Quận thử",
        "original_province": "Tỉnh thử",
        "title": title,
        "property_type_raw": property_type_raw,
        "property_type": property_type,
        "deal_type": "EXPLICIT_SALE",
        "deal_classification": "SALE_CONFIRMED_BY_TEXT",
        "dedupe_classification": "DISTINCT",
        "candidate_status": "ELIGIBLE_HISTORICAL_SALE",
        "published_date": "2025-01-01",
        "price_vnd": 1_000_000_000.0,
        "area_m2": 100.0,
        "price_per_m2": price_per_m2,
        "review_reason": review_reason,
        "evidence_status": "HISTORICAL_DATASET_UNVERIFIED",
        "source_dataset_url": "https://huggingface.co/datasets/tinixai/vietnam-real-estates",
        "source_row_index": 1,
        "source_shard": "0000.parquet",
        "raw_payload": json.dumps(raw_payload or {}),
    }


def test_classification_packet_keeps_original_fields_and_blank_human_labels():
    rows = _classification_packet_rows(
        [
            {
                "source_row_index": "42",
                "source_shard": "0001.parquet",
                "target_rank": "11",
                "province_name": "Hồ Chí Minh",
                "district_name": "Bình Tân",
                "ward_name": "Bình Trị Đông",
                "title": "Bán nhà riêng, ví dụ giả định",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "human_label": "",
                "review_notes": "",
            }
        ],
        "revision-1",
        {("0001.parquet", "42"): {"price": 1, "area": 70, "project_name": "Dự án ví dụ"}},
    )

    row = rows[0]
    assert row["source_row_id"] == source_row_id("revision-1", "0001.parquet", "42")
    assert row["title"] == "Bán nhà riêng, ví dụ giả định"
    assert row["rule_predicted_label"] == "SALE"
    assert row["e4_rule_version"] == "E4"
    assert row["rule_confidence"] == ""
    assert row["human_label"] == ""
    assert row["review_status"] == "NOT_REVIEWED"
    assert row["province_name"] == "Hồ Chí Minh"
    assert row["source_project_name"] == "Dự án ví dụ"
    assert row["source_price_present"] == "true"
    assert row["source_area_present"] == "true"
    assert row["source_listing_detail_url_present"] == "false"


def test_property_packet_includes_e4_land_unknown_and_title_conflict_cases():
    candidates = [
        _candidate("land", property_type="DAT_O", property_type_raw="Đất"),
        _candidate("unknown", property_type=None, property_type_raw="Đất"),
        _candidate("house-conflict", title="Căn hộ chung cư đang bán"),
        _candidate("apartment-conflict", title="Bán nhà riêng có sân", property_type="CHUNG_CU"),
        _candidate("normal-house", title="Bán nhà riêng đẹp"),
    ]

    rows = _property_review_rows(candidates, "revision-1")
    by_id = {row["candidate_id"]: row for row in rows}
    assert set(by_id) == {"land", "unknown", "house-conflict", "apartment-conflict"}
    assert by_id["land"]["human_property_label"] == ""
    assert by_id["land"]["review_status"] == "NOT_REVIEWED"
    assert by_id["land"]["evidence_status"] == "HISTORICAL_DATASET_UNVERIFIED"
    assert "TITLE_CUE_CONFLICT" in by_id["house-conflict"]["property_review_reason"]


def test_sensitivity_reports_no_source_or_area_basis_without_removing_rows():
    mapped = _candidate(
        "mapped",
        property_type="DAT_O",
        property_type_raw="Đất",
        review_reason="PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED",
    )
    direct = _candidate("direct", target_rank=2)
    report = _sensitivity_report(
        [mapped, direct],
        [
            {"target_rank": 1, "original_ward": "Phường thử 1"},
            {"target_rank": 2, "original_ward": "Phường thử 2"},
        ],
        duplicate_pair_count=0,
    )

    scenarios = {item["scenario"]: item for item in report["sensitivity_scenarios"]}
    assert scenarios["E4_BASELINE"]["eligible_count"] == 2
    assert scenarios["EXCLUDE_TITLE_DERIVED_DAT_O"]["eligible_count"] == 1
    assert scenarios["REQUIRE_PER_LISTING_SOURCE_URL"]["eligible_count"] == 0
    assert scenarios["REQUIRE_EXPLICIT_AREA_BASIS"]["eligible_count"] == 0
    assert report["eligible_record_audit"]["per_listing_source_url_present_count"] == 0
    assert report["eligible_record_audit"]["area_basis_present_count"] == 0
    assert report["eligible_record_audit"]["sale_evidence_scope"].startswith("E4 title rules")


def test_property_review_validation_requires_valid_labels_and_status(tmp_path):
    path = tmp_path / "property-review.csv"
    fields = ["candidate_id", "source_row_id", "e4_property_type", "human_property_label", "review_status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "candidate-1",
                "source_row_id": "row-1",
                "e4_property_type": "UNKNOWN",
                "human_property_label": "",
                "review_status": "NOT_REVIEWED",
            }
        )
    result = validate_property_review_csv(path)
    assert result["unreviewed_count"] == 1
    assert result["metrics_available"] is False
    assert result["source_verified_count"] == 0

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "candidate-1",
                "source_row_id": "row-1",
                "e4_property_type": "UNKNOWN",
                "human_property_label": "AI_ESTIMATE",
                "review_status": "REVIEWED",
            }
        )
    with pytest.raises(ValueError, match="Invalid human_property_label"):
        validate_property_review_csv(path)
