import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from wardprice.api import create_app
from wardprice.ingestion_pilot import (
    DEFAULT_PILOT_DB,
    IngestionError,
    _safe_pilot_path,
    benchmark_synthetic_500,
    ingest_collector_result,
    ingest_file,
    ingest_payload,
    init_pilot_db,
    lookup_pilot,
    process_inbox,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def targets_db(tmp_path: Path) -> Path:
    path = tmp_path / "targets.sqlite3"
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE priority_targets(target_rank INTEGER PRIMARY KEY,original_ward TEXT,
           original_district TEXT,original_province TEXT,source_reference TEXT)"""
    )
    for rank in range(1, 51):
        db.execute(
            "INSERT INTO priority_targets VALUES(?,?,?,?,?)",
            (rank, f"Phường Mẫu {rank}", "Quận Thử Nghiệm", "Tỉnh Mẫu", "fixture"),
        )
    db.commit()
    db.close()
    return path


def source_registry(tmp_path: Path, *, source_id="partner-test", authorized=True,
                    extra_sources=None, capabilities=None) -> Path:
    path = tmp_path / "sources.json"
    sources = [
        {
            "source_id": source_id,
            "source_name": "Authorized test partner" if authorized else "Review required source",
            "source_type": "PARTNER_JSON",
            "permission_status": "AUTHORIZED" if authorized else "REVIEW_REQUIRED",
            "permission_evidence": "fixture contract reference" if authorized else "",
            "permitted_scope": "Top 50 listing fields in pilot database" if authorized else "",
            "permitted_frequency": "One offline test import" if authorized else "",
            "storage_permission": authorized,
            "attribution_requirements": "Attribution in fixture" if authorized else "",
            "last_reviewed_at": "2026-10-15",
            "enabled": authorized,
            "capabilities": capabilities or {},
        }
    ]
    sources.extend(extra_sources or [])
    path.write_text(json.dumps({"version": 1, "sources": sources}), encoding="utf-8")
    return path


def record(*, rank=1, suffix="a", price=3_000_000_000, area=100,
           title="Tin thử nghiệm", property_type="NHA_RIENG", transaction_type="SALE",
           source_id="partner-test", source_url_type="DIRECT_LISTING",
           source_url=None, address=None, **extra):
    return {
        "source_id": source_id,
        "source_listing_id": f"listing-{suffix}",
        "source_url": source_url or f"https://partner.example/listing/{suffix}",
        "source_url_type": source_url_type,
        "title": f"{title} {suffix}",
        "target_rank": rank,
        "original_ward": f"Phường Mẫu {rank}",
        "original_district": "Quận Thử Nghiệm",
        "original_province": "Tỉnh Mẫu",
        "property_type": property_type,
        "transaction_type": transaction_type,
        "price_vnd": price,
        "area_m2": area,
        "area_basis": "LAND_AREA",
        "address": address or f"Đường Số 1, Phường Mẫu {rank}, Quận Thử Nghiệm, Tỉnh Mẫu",
        "evidence_status": "SOURCE_PAGE_CONFIRMED",
        "price_evidence": "Giá hiển thị trên nguồn",
        "area_evidence": "Diện tích hiển thị trên nguồn",
        "address_evidence": "Địa chỉ hiển thị trên nguồn",
        **extra,
    }


def setup(tmp_path, *, authorized=True, capabilities=None):
    target_path = targets_db(tmp_path)
    registry = source_registry(tmp_path, authorized=authorized, capabilities=capabilities)
    pilot = tmp_path / "pilot.sqlite3"
    init_pilot_db(pilot, targets_db=target_path, source_registry=registry)
    return pilot, target_path, registry


def count_rows(path, table):
    db = sqlite3.connect(path)
    try:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        db.close()


def test_source_authorization_gate_blocks_review_required_source(tmp_path):
    pilot, target_path, registry = setup(tmp_path, authorized=False)
    result = ingest_payload(
        {"source_id": "partner-test", "listings": [record()]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
    )
    assert result["status"] == "BLOCKED_SOURCE"
    assert "PERMISSION_NOT_AUTHORIZED" in result["source_block_reasons"]
    assert result["network_attempted"] is False
    assert count_rows(pilot, "ingestion_listings") == 0
    assert count_rows(pilot, "ingestion_runs") == 1


def test_pilot_path_guard_protects_all_existing_warehouse_databases():
    protected_names = (
        "ward_prices.sqlite3", "ward_prices.demo.sqlite3",
        "ward_prices.historical_pilot.sqlite3", "wardprice_webpilot.sqlite3",
    )
    for name in protected_names:
        with pytest.raises(IngestionError, match="isolated SQLite"):
            _safe_pilot_path(DEFAULT_PILOT_DB.parent / name)


def test_json_preview_is_read_only_and_uses_python_price_per_m2(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    before = count_rows(pilot, "ingestion_runs")
    result = ingest_payload(
        {"source_id": "partner-test", "listings": [record(price=3_000_000_000, area=100)]},
        pilot_db=pilot, targets_db=target_path, source_registry=registry,
    )
    assert result["status"] == "PREVIEW_ONLY"
    assert result["accepted"] == 1
    assert result["inserted"] == 1
    assert result["network_attempted"] is False
    assert count_rows(pilot, "ingestion_runs") == before
    assert count_rows(pilot, "ingestion_listings") == 0


def test_csv_import_supports_same_normalization_and_uses_target_whitelist(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    csv_file = tmp_path / "batch.csv"
    row = record(source_id="partner-test")
    with csv_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    result = ingest_file(csv_file, pilot_db=pilot, targets_db=target_path,
                         source_registry=registry, apply=True)
    assert result["status"] == "APPLIED"
    assert result["inserted"] == 1
    assert lookup_pilot(pilot, target_rank=1)["listings"][0]["target_rank"] == 1
    assert count_rows(pilot, "ingestion_observations") == 1


def test_import_replay_is_idempotent_for_candidates_and_observations(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    source_file = tmp_path / "batch.json"
    source_file.write_text(json.dumps({
        "source_id": "partner-test", "snapshot_date": "2026-10-15",
        "listings": [record()],
    }), encoding="utf-8")
    first = ingest_file(source_file, pilot_db=pilot, targets_db=target_path,
                        source_registry=registry, apply=True)
    second = ingest_file(source_file, pilot_db=pilot, targets_db=target_path,
                         source_registry=registry, apply=True)
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["previously_seen"] == 1
    assert count_rows(pilot, "ingestion_listings") == 1
    assert count_rows(pilot, "ingestion_observations") == 1


def test_daily_refresh_records_price_history_and_updated_status(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    identity = record(suffix="stable")
    first = {"source_id": "partner-test", "snapshot_date": "2026-10-14", "listings": [identity]}
    result1 = ingest_payload(first, pilot_db=pilot, targets_db=target_path,
                             source_registry=registry, apply=True, file_hash="day-one",
                             at=datetime(2026, 10, 14, 10, tzinfo=TZ))
    changed = {**identity, "price_vnd": 3_300_000_000}
    second = {"source_id": "partner-test", "snapshot_date": "2026-10-15", "listings": [changed]}
    result2 = ingest_payload(second, pilot_db=pilot, targets_db=target_path,
                             source_registry=registry, apply=True, file_hash="day-two",
                             at=datetime(2026, 10, 15, 10, tzinfo=TZ))
    assert result1["inserted"] == 1
    assert result2["updated"] == 1
    assert result2["price_history_changes"] == 1
    assert count_rows(pilot, "ingestion_listings") == 1
    assert count_rows(pilot, "ingestion_observations") == 2
    assert count_rows(pilot, "ingestion_price_history") == 1


def test_only_trusted_recent_published_at_is_counted_as_newly_posted(tmp_path):
    pilot, target_path, registry = setup(
        tmp_path, capabilities={"published_at_authoritative": True}
    )
    listing = record(
        suffix="recent", published_at="2026-10-15T07:00:00+07:00",
        published_at_evidence="Partner feed publication timestamp",
    )
    result = ingest_payload(
        {"source_id": "partner-test", "snapshot_date": "2026-10-15", "listings": [listing]},
        pilot_db=pilot, targets_db=target_path, source_registry=registry, apply=True,
        file_hash="trusted-date", at=datetime(2026, 10, 15, 10, tzinfo=TZ),
    )
    assert result["newly_posted"] == 1
    assert result["newly_discovered"] == 0


def test_ai_claim_and_category_url_do_not_verify_or_deduplicate_by_category_url(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    rows = [
        record(suffix="category-1", source_url_type="CATEGORY",
               source_url="https://partner.example/search?ward=1"),
        record(suffix="category-2", source_url_type="CATEGORY",
               source_url="https://partner.example/search?ward=1", title="Tin khác"),
    ]
    result = ingest_payload(
        {"source_id": "partner-test", "listings": rows}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
    )
    listings = lookup_pilot(pilot, target_rank=1)["listings"]
    assert result["inserted"] == 2
    assert {row["source_url_type"] for row in listings} == {"CATEGORY"}
    assert {row["evidence_status"] for row in listings} == {"CATEGORY_ONLY"}
    assert all(not row["stats_eligible"] for row in listings)


def test_json_cannot_forge_collector_source_page_proof(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    forged = record(
        suffix="forged-proof", evidence_status="SOURCE_PAGE_CONFIRMED",
        _collector_source_page_proof={
            "retrieved_direct": True,
            "detail_url": "https://partner.example/listing/forged-proof",
            "content_sha256": "a" * 64,
            "visible_price_match": True,
            "visible_area_match": True,
            "address_verified": True,
        },
    )
    ingest_payload(
        {"source_id": "partner-test", "listings": [forged]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
    )
    listing = lookup_pilot(pilot, target_rank=1)["listings"][0]
    assert listing["evidence_status"] == "SOURCE_PARTIAL"
    assert listing["stats_eligible"] == 0


def test_existing_collector_adapter_keeps_proof_outside_imported_json(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    page_hash = "a" * 64
    address = "Đường Số 1, Phường Mẫu 1, Quận Thử Nghiệm, Tỉnh Mẫu"
    candidate = {
        "source_listing_id": "collector-1", "target_rank": 1,
        "original_ward": "Phường Mẫu 1", "original_district": "Quận Thử Nghiệm",
        "original_province": "Tỉnh Mẫu", "property_type": "NHA_RIENG",
        "title": "Tin qua collector", "address": address,
        "price_vnd": 3_000_000_000, "area_m2": 100, "area_basis": "FLOOR_AREA",
        "source_url": "https://partner.example/listing/collector-1",
        "canonical_url": "https://partner.example/listing/collector-1",
        "source_url_type": "DIRECT_LISTING", "evidence_status": "SOURCE_VERIFIED",
        "evidence": {
            "price": {"structured": 3_000_000_000, "visible": 3_000_000_000},
            "area_m2": {"structured": 100, "visible": 100},
            "address": address, "target_match": True, "content_sha256": page_hash,
        },
        "raw_payload": {
            "retrieved_at": "2026-10-15T09:00:00+07:00", "content_sha256": page_hash,
            "visible_price_match": True, "visible_area_match": True,
            "address_visible": True, "target_terms_present": True,
        },
    }
    result = ingest_collector_result(
        {"target_rank": 1, "collected_at": "2026-10-15T09:00:00+07:00",
         "listing_candidates": [candidate]},
        source_id="partner-test", pilot_db=pilot, targets_db=target_path,
        source_registry=registry, apply=True,
    )
    listing = lookup_pilot(pilot, target_rank=1)["listings"][0]
    assert result["verified"] == 1
    assert listing["evidence_status"] == "SOURCE_PAGE_CONFIRMED"
    assert listing["stats_eligible"] == 0  # Existing collector does not confirm sale vs rent.


def test_same_snapshot_file_replay_is_idempotent_but_next_day_is_observed(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    payload = {"source_id": "partner-test", "listings": [record(suffix="daily-same")]}
    first = ingest_payload(
        payload, pilot_db=pilot, targets_db=target_path, source_registry=registry,
        apply=True, at=datetime(2026, 10, 15, 10, tzinfo=TZ),
    )
    same_day_replay = ingest_payload(
        payload, pilot_db=pilot, targets_db=target_path, source_registry=registry,
        apply=True, at=datetime(2026, 10, 15, 11, tzinfo=TZ),
    )
    next_day_refresh = ingest_payload(
        payload, pilot_db=pilot, targets_db=target_path, source_registry=registry,
        apply=True, at=datetime(2026, 10, 16, 10, tzinfo=TZ),
    )
    assert first["inserted"] == 1
    assert same_day_replay["inserted"] == 0
    assert same_day_replay["previously_seen"] == 1
    assert next_day_refresh["inserted"] == 0
    assert next_day_refresh["previously_seen"] == 1
    assert count_rows(pilot, "ingestion_observations") == 2


def test_later_review_can_promote_candidate_into_verified_statistics(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    listing = record(suffix="promote-me")
    ingest_payload(
        {"source_id": "partner-test", "listings": [listing]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
    )
    reviewed = ingest_payload(
        {"source_id": "partner-test", "listings": [listing]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
        operator_verified=True, verified_by="reviewer", verification_reference="local-review-42",
    )
    stored = lookup_pilot(pilot, target_rank=1)["listings"][0]
    assert reviewed["updated"] == 1
    assert stored["evidence_status"] == "SOURCE_PAGE_CONFIRMED"
    assert stored["stats_eligible"] == 1
    assert lookup_pilot(pilot, target_rank=1)["statistics"][0]["listing_count"] == 1


def test_daily_refresh_preserves_expired_status_for_previously_seen_listing(tmp_path):
    pilot, target_path, registry = setup(
        tmp_path, capabilities={"expires_at_authoritative": True}
    )
    first = {**record(suffix="expires"), "expires_at": "2026-10-20"}
    ingest_payload(
        {"source_id": "partner-test", "listings": [first]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
        at=datetime(2026, 10, 14, 10, tzinfo=TZ),
    )
    expired = {**first, "expires_at": "2026-10-14"}
    result = ingest_payload(
        {"source_id": "partner-test", "listings": [expired]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
        at=datetime(2026, 10, 15, 10, tzinfo=TZ),
    )
    stored = lookup_pilot(pilot, target_rank=1)["listings"][0]
    assert result["expired"] == 1
    assert stored["freshness_status"] == "EXPIRED"
    assert stored["validity_status"] == "EXPIRED"
    assert stored["stats_eligible"] == 0


def test_mismatched_ward_is_quarantined_and_contact_fields_are_redacted(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    mismatch = record(suffix="wrong")
    mismatch["original_ward"] = "Phường Ngoài Top50"
    mismatch["description"] = "Liên hệ 0901234567 email sample@example.com"
    result = ingest_payload(
        {"source_id": "partner-test", "listings": [mismatch]}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
    )
    assert result["rejected_reasons"] == {"WARD_WHITELIST_MISMATCH": 1}
    assert count_rows(pilot, "ingestion_listings") == 0
    db = sqlite3.connect(pilot)
    try:
        raw = db.execute("SELECT raw_payload FROM ingestion_quarantine").fetchone()[0]
    finally:
        db.close()
    assert "0901234567" not in raw
    assert "sample@example.com" not in raw


def test_verified_statistics_are_python_mean_median_and_exclude_rent(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    listings = []
    for index, price_per_m2 in enumerate((10_000_000, 20_000_000, 30_000_000)):
        listings.append(record(
            suffix=f"verified-{index}", price=price_per_m2 * 100, area=100,
            title="Tin đã đối chiếu", property_type="DAT_O",
            price_evidence="Giá trên trang nguồn", area_evidence="Diện tích trên trang", address_evidence="Địa chỉ trên trang",
        ))
    listings.append(record(suffix="rent", property_type="DAT_O", transaction_type="RENT"))
    result = ingest_payload(
        {"source_id": "partner-test", "listings": listings}, pilot_db=pilot,
        targets_db=target_path, source_registry=registry, apply=True,
        operator_verified=True, verified_by="reviewer", verification_reference="review-2026-10-15",
    )
    report = lookup_pilot(pilot, target_rank=1, property_type="DAT_O")
    statistic = report["statistics"][0]
    assert result["verified"] == 4
    assert statistic["listing_count"] == 3
    assert statistic["mean_price_per_m2"] == pytest.approx(20_000_000)
    assert statistic["median_price_per_m2"] == pytest.approx(20_000_000)
    rent = next(item for item in report["listings"] if item["transaction_type"] == "RENT")
    assert rent["stats_eligible"] == 0


def test_cross_source_exact_repost_is_one_candidate_and_requires_review(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    second_source = {
        **registry_payload["sources"][0], "source_id": "partner-second",
        "source_name": "Second partner",
    }
    registry_payload["sources"].append(second_source)
    registry.write_text(json.dumps(registry_payload), encoding="utf-8")
    first = record(suffix="same-property", source_url="https://partner.example/1")
    ingest_payload({"source_id": "partner-test", "listings": [first]}, pilot_db=pilot,
                   targets_db=target_path, source_registry=registry, apply=True)
    repost = {**first, "source_id": "partner-second", "source_listing_id": "repost-1",
              "source_url": "https://second.example/listing/1"}
    second = ingest_payload({"source_id": "partner-second", "listings": [repost]},
                            pilot_db=pilot, targets_db=target_path,
                            source_registry=registry, apply=True)
    assert second["inserted"] == 0
    assert second["previously_seen"] == 1
    assert count_rows(pilot, "ingestion_listings") == 1
    db = sqlite3.connect(pilot)
    try:
        record_row = db.execute("SELECT possible_duplicate,stats_eligible FROM ingestion_listings").fetchone()
        sources = db.execute("SELECT COUNT(*) FROM ingestion_listing_sources").fetchone()[0]
    finally:
        db.close()
    assert tuple(record_row) == (1, 0)
    assert sources == 2


def test_file_drop_processes_authorized_file_and_moves_it_to_processed(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    inbox = tmp_path / "inbox"
    source_file = inbox / "batch.json"
    inbox.mkdir()
    source_file.write_text(json.dumps({"source_id": "partner-test", "listings": [record()]}), encoding="utf-8")
    result = process_inbox(
        inbox=inbox, processing=tmp_path / "processing", processed=tmp_path / "processed",
        quarantine=tmp_path / "quarantine", pilot_db=pilot, targets_db=target_path,
        source_registry=registry, apply=True, stability_seconds=0,
    )
    assert result["files_seen"] == 1
    assert result["results"][0]["status"] == "APPLIED"
    assert Path(result["results"][0]["moved_to"]).parent.name == "processed"
    assert count_rows(pilot, "ingestion_listings") == 1


def test_daily_report_exports_json_csv_without_sending_email(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    result = ingest_payload({"source_id": "partner-test", "listings": [record()]},
                            pilot_db=pilot, targets_db=target_path,
                            source_registry=registry, apply=True)
    assert result["status"] == "APPLIED"
    from wardprice.ingestion_pilot import export_daily_report

    report = export_daily_report(pilot, output_dir=tmp_path / "reports")
    assert Path(report["json_report"]).is_file()
    assert Path(report["csv_report"]).is_file()
    assert report["email_sent"] is False


def test_500_record_benchmark_is_temporary_and_replay_idempotent(tmp_path):
    targets = targets_db(tmp_path)
    result = benchmark_synthetic_500(targets_db=targets, count=500)
    assert result["status"] == "PASS"
    assert result["records_processed"] == 500
    assert result["unique_listings"] == 500
    assert result["replay_inserted"] == 0
    assert result["unique_observations"] == 500
    assert result["temporary_database_only"] is True
    assert result["synthetic_data_in_production"] is False
    assert result["network_attempted"] is False


def test_ingestion_monitoring_api_and_lookup_api_are_read_only(tmp_path):
    pilot, target_path, registry = setup(tmp_path)
    ingest_payload({"source_id": "partner-test", "listings": [record()]},
                   pilot_db=pilot, targets_db=target_path,
                   source_registry=registry, apply=True)
    app = create_app(
        db_path=tmp_path / "unused-production.sqlite3",
        historical_pilot_db_path=tmp_path / "unused-historical.sqlite3",
        ingestion_pilot_db_path=pilot,
    )
    client = TestClient(app)
    monitoring = client.get("/api/v1/ingestion/monitoring")
    listings = client.get("/api/v1/ingestion/listings?target_rank=1")
    assert monitoring.status_code == 200
    assert monitoring.json()["candidate_count"] == 1
    assert listings.status_code == 200
    assert listings.json()["candidate_count"] == 1
    assert client.get("/ingestion-pilot").status_code == 200
    assert len(monitoring.json()["target_coverage"]) == 50
    assert monitoring.json()["target_coverage"][0]["target_rank"] == 1
    assert monitoring.json()["candidate_covered_targets"] == 1
    assert monitoring.json()["production_database_written"] is False


def test_demo_api_does_not_expose_ingestion_pilot(tmp_path):
    app = create_app(
        db_path=tmp_path / "demo.sqlite3", demo_mode=True,
        historical_pilot_db_path=tmp_path / "historical.sqlite3",
        ingestion_pilot_db_path=tmp_path / "ingestion.sqlite3",
    )
    client = TestClient(app)
    assert client.get("/ingestion-pilot").status_code == 404
    assert client.get("/api/v1/ingestion/monitoring").json()["status"] == "DISABLED_DEMO_MODE"
    assert client.get("/api/v1/ingestion/listings").json()["listings"] == []

