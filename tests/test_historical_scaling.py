import csv
import json
import sqlite3
from io import BytesIO
from urllib.error import HTTPError

import pytest

from scripts import download_tinix_historical_sample as sampler
from wardprice.historical_dataset import (
    DATASET_ID,
    LICENSE_ID,
    HistoricalDatasetImporter,
    _deal_classification,
    _sample_statistics,
    audit_sample_quality,
    pilot_lookup,
    pilot_overview,
)


def _targets():
    rows = []
    for rank in range(1, 51):
        rows.append(
            {
                "target_rank": rank,
                "original_ward": f"Phường Mẫu {rank}",
                "original_district": "Quận Mẫu",
                "original_province": "Thành phố Mẫu",
                "source_reference": "offline fixture",
            }
        )
    rows[0].update(
        {
            "original_ward": "Phường An Lạc",
            "original_district": "Quận Bình Tân",
            "original_province": "Thành phố Hồ Chí Minh",
        }
    )
    return rows


def _row(index, *, title=None, price=None, area=50.0, property_type="Nhà"):
    return {
        "source_row_index": index,
        "source_shard": f"{index // 1000:04d}.parquet",
        "source_row_in_shard": index % 1000,
        "name": title or f"Bán nhà riêng số {index} tại An Lạc",
        "property_type_name": property_type,
        "province_name": "Hồ Chí Minh",
        "district_name": "Bình Tân",
        "ward_name": "An Lạc",
        "street_name": "Đường Mẫu",
        "project_name": None,
        "price": price if price is not None else 5_000_000_000 + index * 10_000,
        "area": area,
        "published_at": "2025-11-04T09:00:00Z",
    }


def _metadata(sample_rows, *, batch_id=None):
    value = {
        "dataset_id": DATASET_ID,
        "revision": "e3-test-revision",
        "license_id": LICENSE_ID,
        "private": False,
        "gated": False,
        "full_dataset_downloaded": False,
        "commercial_use": False,
        "sample_rows": sample_rows,
        "split_rows_reported": 3_500_744,
        "sample_method": "deterministic test fixture; not statistically representative",
        "retrieved_at": "2026-10-15T00:00:00+00:00",
        "schema": [
            {"name": field}
            for field in (
                "name", "property_type_name", "province_name", "district_name", "ward_name",
                "price", "area", "published_at",
            )
        ],
    }
    if batch_id:
        value["batch_id"] = batch_id
    return value


def _inputs(tmp_path, rows, metadata=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    sample_path = tmp_path / "sample.jsonl"
    sample_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    metadata_path = tmp_path / "sample.metadata.json"
    metadata_path.write_text(
        json.dumps(metadata or _metadata(len(rows)), ensure_ascii=False), encoding="utf-8"
    )
    targets_path = tmp_path / "targets.sqlite3"
    with sqlite3.connect(targets_path) as connection:
        connection.execute(
            """CREATE TABLE priority_targets(
                 target_rank INTEGER PRIMARY KEY,original_ward TEXT,original_district TEXT,
                 original_province TEXT,source_reference TEXT)"""
        )
        connection.executemany(
            "INSERT INTO priority_targets VALUES(?,?,?,?,?)",
            [
                (
                    row["target_rank"], row["original_ward"], row["original_district"],
                    row["original_province"], row["source_reference"],
                )
                for row in _targets()
            ],
        )
    return sample_path, metadata_path, targets_path


def test_sampling_index_identity_is_deterministic_and_non_overlapping():
    blocked = {100, 101, 102}
    first = sampler._choose_non_overlapping_offset(100, 200, 5, blocked, "revision:1000:0")
    second = sampler._choose_non_overlapping_offset(100, 200, 5, blocked, "revision:1000:0")
    assert first == second
    assert set(range(first, first + 5)).isdisjoint(blocked)
    assert sampler._stratum_for_index(35_007, 3_500_744, 100) == 0
    assert sampler._identity_for_index(
        350_075,
        [
            {"filename": "0000.parquet", "row_start": 0, "row_end_exclusive": 350_075},
            {"filename": "0001.parquet", "row_start": 350_075, "row_end_exclusive": 700_150},
        ],
    ) == ("0001.parquet", 0)


def test_remote_parquet_reader_refuses_full_file_response(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"whole shard"

    monkeypatch.setattr(sampler, "urlopen", lambda *_args, **_kwargs: Response())
    reader = sampler._ParquetRangeReader("https://huggingface.co/datasets/test.parquet", 100)
    with pytest.raises(RuntimeError, match="refusing to download a complete shard"):
        reader.read(5)


def test_hugging_face_rows_rate_limit_honors_retry_after(monkeypatch):
    sleeps = []
    responses = 0

    def fake_get_json(_url):
        nonlocal responses
        responses += 1
        if responses == 1:
            raise HTTPError(
                sampler.ROWS_API,
                429,
                "rate limited",
                {"Retry-After": "7"},
                BytesIO(b"too many requests"),
            )
        return {"rows": []}

    monkeypatch.setattr(sampler, "_get_json", fake_get_json)
    monkeypatch.setattr(sampler.time, "sleep", sleeps.append)
    assert sampler._row_page(100, 10) == {"rows": []}
    assert responses == 2
    assert sleeps == [sampler.ROW_REQUEST_INTERVAL_SECONDS, 7.0]


def test_extend_sample_reuses_e2_and_fills_each_of_one_hundred_strata(tmp_path, monkeypatch):
    revision = "e3-sampler-test"
    schema = [{"name": field} for field in sampler.SAMPLE_COLUMNS]
    previous_rows = []
    for stratum in range(100):
        start = stratum * sampler.EXPECTED_SPLIT_ROWS // 100
        end = (stratum + 1) * sampler.EXPECTED_SPLIT_ROWS // 100
        width = (end - start) // 10
        for offset in range(10):
            row = _row(start + offset * width)
            previous_rows.append({key: row.get(key) for key in sampler.SAMPLE_COLUMNS} | {
                "source_row_index": start + offset * width,
            })
    existing_sample = tmp_path / "e2.jsonl"
    existing_sample.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in previous_rows), encoding="utf-8"
    )
    existing_metadata = tmp_path / "e2.metadata.json"
    existing_metadata.write_text(
        json.dumps(
            {
                "dataset_id": sampler.DATASET_ID,
                "revision": revision,
                "sample_rows": len(previous_rows),
                "sample_method": "E2 deterministic sample",
                "retrieved_at": "2026-10-14T00:00:00Z",
                "sample_offsets": [],
                "schema": schema,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sampler,
        "_revision_metadata",
        lambda: {
            "dataset_id": sampler.DATASET_ID,
            "revision": revision,
            "license_id": sampler.LICENSE_ID,
            "private": False,
            "gated": False,
        },
    )
    monkeypatch.setattr(
        sampler,
        "_parquet_manifest",
        lambda _count: (
            [{
                "filename": "0000.parquet",
                "file_bytes": 1000,
                "row_count": sampler.EXPECTED_SPLIT_ROWS,
                "row_start": 0,
                "row_end_exclusive": sampler.EXPECTED_SPLIT_ROWS,
                "row_groups": 1,
                "footer_bytes_read": 1024,
            }],
            1024,
        ),
    )

    page_calls = 0

    def fake_row_page(offset, length):
        nonlocal page_calls
        page_calls += 1
        if page_calls == 4:
            raise RuntimeError("simulated offline interruption")
        return {
            "num_rows_total": sampler.EXPECTED_SPLIT_ROWS,
            "partial": False,
            "features": schema,
            "rows": [
                {
                    "row_idx": index,
                    "row": {
                        "name": f"Bán nhà riêng số {index}",
                        "property_type_name": "Nhà",
                        "province_name": "Hồ Chí Minh",
                        "district_name": "Bình Tân",
                        "ward_name": "An Lạc",
                        "street_name": "Đường Mẫu",
                        "project_name": None,
                        "price": 5_000_000_000,
                        "area": 50.0,
                        "published_at": "2025-11-04T09:00:00Z",
                    },
                }
                for index in range(offset, offset + length)
            ],
        }

    monkeypatch.setattr(sampler, "_row_page", fake_row_page)
    monkeypatch.setattr(sampler.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="simulated offline interruption"):
        sampler.extend_sample(
            10_000, existing_sample, existing_metadata, tmp_path / "e3_sample"
        )
    assert page_calls == 4
    result = sampler.extend_sample(
        10_000, existing_sample, existing_metadata, tmp_path / "e3_sample"
    )
    metadata = json.loads((tmp_path / "e3_sample.metadata.json").read_text(encoding="utf-8"))
    with (tmp_path / "e3_sample.jsonl").open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    indexes = [row["source_row_index"] for row in rows]
    counts = [
        sum(sampler._stratum_for_index(index, sampler.EXPECTED_SPLIT_ROWS, 100) == stratum for index in indexes)
        for stratum in range(100)
    ]
    assert result["sample_rows"] == 10_000
    assert result["new_rows"] == 9_000
    assert result["reused_e2_rows"] == 1_000
    assert page_calls == 101  # 4 initial attempts, then only 97 unfinished strata.
    assert len(set(indexes)) == 10_000
    assert counts == [100] * 100
    assert metadata["previous_batch"]["sample_rows"] == 1_000
    assert metadata["schema"] == schema
    assert metadata["sampling_is_statistically_representative"] is not True
    monkeypatch.setattr(
        sampler,
        "_row_page",
        lambda *_args: (_ for _ in ()).throw(AssertionError("completed checkpoint was fetched again")),
    )
    resumed = sampler.extend_sample(
        10_000, existing_sample, existing_metadata, tmp_path / "e3_sample"
    )
    assert resumed["sample_sha256"] == result["sample_sha256"]


def test_incremental_import_resume_and_idempotency_at_ten_thousand_rows(tmp_path):
    pilot = tmp_path / "pilot.sqlite3"
    importer = None
    first_rows = [_row(index) for index in range(1_000)]
    sample1, metadata1, targets = _inputs(tmp_path / "first", first_rows)
    importer = HistoricalDatasetImporter(targets, pilot)
    first = importer.import_batch(sample1, metadata1)
    assert first["summary"]["source_rows_after_import"] == 1_000

    all_rows = [_row(index) for index in range(10_000)]
    sample2, metadata2, targets2 = _inputs(
        tmp_path / "second",
        all_rows,
        _metadata(10_000, batch_id="tinix-e3-10000-e3testrevision"),
    )
    importer = HistoricalDatasetImporter(targets2, pilot)
    dry = importer.dry_run(sample2, metadata2)
    assert dry["source_rows_already_processed"] == 1_000
    assert dry["new_source_rows_to_process"] == 9_000
    second = importer.import_batch(sample2, metadata2)
    assert second["summary"]["replayed_source_rows"] == 1_000
    assert second["summary"]["source_rows_after_import"] == 10_000
    assert second["summary"]["candidate_count_after_import"] == 10_000
    assert second["summary"]["observation_count_after_import"] == 10_000

    replay = importer.import_batch(sample2, metadata2)
    assert replay["summary"]["replayed_source_rows"] == 10_000
    assert replay["summary"]["unique_candidates_to_import"] == 0
    with sqlite3.connect(pilot) as connection:
        assert connection.execute("SELECT COUNT(*) FROM historical_source_rows").fetchone()[0] == 10_000
        assert connection.execute("SELECT COUNT(*) FROM historical_candidates").fetchone()[0] == 10_000
        assert connection.execute("SELECT COUNT(*) FROM historical_observations").fetchone()[0] == 10_000
        assert connection.execute("SELECT COUNT(*) FROM historical_dataset_batches").fetchone()[0] == 2
    overview = pilot_overview(pilot)
    assert overview["source_rows_processed"] == 10_000
    assert overview["candidate_count"] == 10_000
    lookup = pilot_lookup(pilot, 1, "NHA_RIENG")
    stats = lookup["statistics_by_property_type"][0]
    assert stats["n_samples"] == 10_000
    assert stats["p25_price_per_m2"] <= stats["median_price_per_m2"] <= stats["p75_price_per_m2"]
    assert stats["sample_quality_flags"]


def test_cross_batch_exact_and_possible_duplicates_are_reviewed(tmp_path):
    pilot = tmp_path / "pilot.sqlite3"
    targets = None
    title = "Bán nhà riêng mặt tiền đường An Lạc"
    first_rows = [_row(1, title=title, price=5_000_000_000, area=50.0)]
    sample1, metadata1, targets = _inputs(tmp_path / "first", first_rows)
    importer = HistoricalDatasetImporter(targets, pilot)
    importer.import_batch(sample1, metadata1)

    replay_content = [
        _row(2, title=title, price=5_000_000_000, area=50.0),
        _row(3, title=title, price=5_500_000_000, area=55.0),
    ]
    sample2, metadata2, targets2 = _inputs(tmp_path / "second", replay_content)
    result = HistoricalDatasetImporter(targets2, pilot).import_batch(sample2, metadata2)
    assert result["summary"]["duplicate_content_rows"] == 1
    assert result["summary"]["possible_duplicate_rows"] == 1
    with sqlite3.connect(pilot) as connection:
        assert connection.execute("SELECT COUNT(*) FROM historical_candidates").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM historical_duplicate_pairs").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM historical_candidates WHERE candidate_status='NEEDS_REVIEW'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM historical_monthly_statistics"
        ).fetchone()[0] == 0


def test_title_classification_and_small_sample_outlier_diagnostics():
    assert _deal_classification("Bán nhà đang cho thuê") == "AMBIGUOUS"
    assert _deal_classification("Cần bán hoặc cho thuê nhà") == "CONFLICT"
    small = _sample_statistics([10.0, 11.0, 12.0])
    assert small["n_samples"] == 3
    assert "SMALL_SAMPLE_N_LT_5" in small["sample_quality_flags"]
    assert small["outlier_count"] == 0
    larger = _sample_statistics([10.0, 11.0, 12.0, 13.0, 1_000.0])
    assert larger["outlier_count"] == 1
    assert larger["mean_without_outliers"] == pytest.approx(11.5)
    assert "TUKEY_IQR_OUTLIERS_PRESENT_DIAGNOSTIC_ONLY" in larger["sample_quality_flags"]


def test_quality_audit_writes_unlabeled_review_packet_and_source_report(tmp_path):
    rows = [
        _row(1, title="Bán nhà riêng số 1 tại An Lạc"),
        _row(2, title="Cho thuê nhà riêng số 2 tại An Lạc"),
        _row(3, title="Nhà riêng số 3 tại An Lạc"),
        _row(4, title="Cần bán hoặc cho thuê nhà riêng số 4 tại An Lạc"),
        _row(5, title="Bán nhà riêng số 5 tại An Lạc", price="invalid"),
        _row(6, title="Bán nhà riêng số 6 tại An Lạc", area=0.0),
    ]
    sample, metadata, targets = _inputs(tmp_path / "input", rows)
    output_dir = tmp_path / "quality"
    report = audit_sample_quality(sample, metadata, targets, output_dir)
    assert report["sample_source_rows"] == 6
    assert report["sampling_is_statistically_representative"] is False
    assert report["quality_counts"]["matched_top50_rows"] == 6
    assert report["quality_counts"]["invalid_price"] == 1
    assert report["quality_counts"]["invalid_area"] == 1
    assert report["ground_truth_labels_available"] is False
    with open(report["manual_title_review_packet"]["path"], encoding="utf-8-sig", newline="") as handle:
        review = list(csv.DictReader(handle))
    assert len(review) == 6
    assert all(row["human_label"] == "" for row in review)
    with open(report["report_file"], encoding="utf-8") as handle:
        assert json.loads(handle.read())
