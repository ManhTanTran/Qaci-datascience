from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wardprice_webpilot import __main__ as cli
from wardprice_webpilot.candidate_batch import (
    apply_batch,
    assert_isolated_audit_database,
    backup_before_candidate_schema,
    ensure_schema,
    prepare_batch,
    preview_against_database,
)
from wardprice_webpilot.core import connect, export
from wardprice_webpilot.ui_service import recent_candidates

TARGETS = {
    2: {
        "rank": 2,
        "ward": "Phường Hiệp Bình Chánh",
        "district": "Thành phố Thủ Đức",
        "province": "Thành phố Hồ Chí Minh",
    },
    3: {
        "rank": 3,
        "ward": "Phường Linh Trung",
        "district": "Thành phố Thủ Đức",
        "province": "Thành phố Hồ Chí Minh",
    },
}


def _item(index: int, **overrides):
    item = {
        "target_rank": 2,
        "original_ward": "Phường Hiệp Bình Chánh",
        "property_type": "CHUNG_CU" if index >= 4 else "NHA_RIENG",
        "title": f"Tin rao mẫu số {index} tại Hiệp Bình Chánh",
        "address": f"Số {index} đường mẫu, Phường Hiệp Bình Chánh, TP. Thủ Đức",
        "price_vnd": 3_000_000_000 + index * 100_000_000,
        "area_m2": 50 + index,
        "source_website": "example.vn",
        "source_url": "https://example.vn/bat-dong-san/hiep-binh-chanh",
        "source_url_type": "CATEGORY",
        "listed_date": "2026-10-10",
        "evidence_status": "SEARCH_SNIPPET_ONLY",
    }
    item.update(overrides)
    return item


def _batch():
    items = [_item(index) for index in range(1, 5)]
    items.append(
        _item(
            5,
            title="Bán căn hộ Opal Garden 2 phòng ngủ",
            address="Đường 20, Phường Hiệp Bình Chánh, TP. Thủ Đức",
            possible_duplicate=True,
            source_url_type="DIRECT_LISTING",
            source_url="https://example.vn/listing/opal-garden-5",
        )
    )
    return {
        "target_rank": 2,
        "original_ward": "Phường Hiệp Bình Chánh",
        "run_date": "2026-10-14",
        "target_count": 10,
        "actual_collected": 5,
        "warnings": [
            "Opal Garden: nguồn xung đột, có thể là cùng một tin rao; cần rà soát thủ công."
        ],
        "listings": items,
    }


def _targets_database(path: Path, *, tables: tuple[str, ...] = ()):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ward_target_legacy(rank INTEGER PRIMARY KEY)")
        for rank in range(1, 51):
            db.execute("INSERT INTO ward_target_legacy VALUES(?)", (rank,))
        for table in tables:
            db.execute(f'CREATE TABLE "{table}" (key TEXT PRIMARY KEY)')


def test_preview_preserves_snippet_candidates_and_conflict_without_writes():
    raw = json.dumps(_batch(), ensure_ascii=False)
    prepared = prepare_batch(raw, TARGETS, expected_rank=2)
    preview = preview_against_database(prepared, None)

    assert preview["received"] == preview["accepted_count"] == 5
    assert (
        preview["quarantined_count"] == preview["duplicate_count"] == preview["rejected_count"] == 0
    )
    assert preview["statistics_eligible_count"] == 0
    candidates = [row for row in preview["rows"] if row.get("candidate_fingerprint")]
    assert len({row["candidate_fingerprint"] for row in candidates}) == 5
    assert {row["target_rank"] for row in candidates} == {2}
    assert {row["original_ward"] for row in candidates} == {"Phường Hiệp Bình Chánh"}
    assert all(row["evidence_status"] == "SEARCH_SNIPPET_ONLY" for row in candidates)
    assert all(row["verification_label"] == "Chưa xác minh nguồn" for row in candidates)
    opal = next(row for row in candidates if "Opal Garden" in row["title"])
    assert opal["review_status"] == "SOURCE_CONFLICT"
    assert "xung đột" in opal["review_warning"]
    assert opal["source_url_type"] == "DIRECT_LISTING"
    assert preview["source_url_type_counts"] == {"CATEGORY": 4, "DIRECT_LISTING": 1}
    assert candidates[0]["price_per_m2"] == pytest.approx(
        candidates[0]["price_vnd"] / candidates[0]["area_m2"]
    )


def test_import_batch_cli_defaults_to_read_only_dry_run(tmp_path, monkeypatch, capsys):
    batch_file = tmp_path / "gemini_rank02.json"
    batch_file.write_text(json.dumps(_batch(), ensure_ascii=False), encoding="utf-8")
    audit_db = tmp_path / "sidecar.sqlite3"
    monkeypatch.setattr(cli, "load_targets", lambda _path: TARGETS)

    exit_code = cli.main(
        [
            "--targets-db",
            str(tmp_path / "targets.sqlite3"),
            "--db",
            str(audit_db),
            "import-batch",
            "--rank",
            "2",
            "--file",
            str(batch_file),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "DRY_RUN"
    assert output["received"] == output["accepted"] == 5
    assert output["network_attempted"] is False
    assert output["production_database_written"] is False
    assert not audit_db.exists()


def test_category_url_is_not_a_deduplication_key_and_reimport_is_idempotent(tmp_path):
    raw = json.dumps(_batch(), ensure_ascii=False, indent=2)
    prepared = prepare_batch(raw, TARGETS, expected_rank=2)
    db = connect(tmp_path / "candidate-sidecar.sqlite3")
    ensure_schema(db)

    first = apply_batch(db, prepared, source_file="batch.json")
    assert first["status"] == "IMPORTED"
    assert first["inserted_candidates"] == 5
    assert first["observations_added"] == 5
    assert db.execute("SELECT COUNT(*) FROM webpilot_batch_candidates").fetchone()[0] == 5
    assert db.execute("SELECT COUNT(*) FROM webpilot_batch_observations").fetchone()[0] == 5

    replay = apply_batch(db, prepared, source_file="batch.json")
    assert replay["status"] == "ALREADY_IMPORTED"
    assert replay["inserted_candidates"] == 0
    assert replay["observations_added"] == 0
    assert replay["duplicate_count"] == 5
    assert db.execute("SELECT COUNT(*) FROM webpilot_batch_candidates").fetchone()[0] == 5
    assert db.execute("SELECT COUNT(*) FROM webpilot_batch_observations").fetchone()[0] == 5

    # Same semantic listings in a differently formatted file still hit the
    # multi-field identity; category page URLs do not collapse or identify them.
    reserialized = json.dumps(_batch(), ensure_ascii=False, separators=(",", ":"))
    second_prepared = prepare_batch(reserialized, TARGETS, expected_rank=2)
    second_preview = preview_against_database(second_prepared, db)
    assert second_preview["accepted_count"] == 0
    assert second_preview["duplicate_count"] == 5
    db.close()


def test_wrong_ward_is_quarantined_and_demo_synthetic_is_rejected(tmp_path):
    batch = _batch()
    batch["listings"][0]["address"] = "Phường Linh Trung, Thành phố Thủ Đức"
    batch["listings"][1]["evidence_status"] = "DEMO_SYNTHETIC"
    prepared = prepare_batch(json.dumps(batch, ensure_ascii=False), TARGETS, expected_rank=2)

    assert prepared["quarantined_count"] == 1
    assert prepared["rejected_count"] == 1
    assert prepared["accepted_count"] == 3
    assert prepared["statistics_eligible_count"] == 0
    quarantined = next(row for row in prepared["rows"] if row["disposition"] == "QUARANTINED")
    rejected = next(row for row in prepared["rows"] if row["disposition"] == "REJECTED")
    assert quarantined["reason"] == "GEO_MISMATCH"
    assert rejected["reason"] == "demo_synthetic_not_allowed_in_candidate_import"


def test_batch_import_respects_global_500_candidate_limit(tmp_path):
    batch = _batch()
    batch["listings"] = batch["listings"][:2]
    batch["actual_collected"] = 2
    prepared = prepare_batch(json.dumps(batch, ensure_ascii=False), TARGETS, expected_rank=2)
    database = sqlite3.connect(tmp_path / "limit.sqlite3")
    database.execute(
        "CREATE TABLE webpilot_batch_candidates(candidate_fingerprint TEXT PRIMARY KEY)"
    )
    database.executemany(
        "INSERT INTO webpilot_batch_candidates VALUES(?)",
        [(f"existing-{index}",) for index in range(499)],
    )
    preview = preview_against_database(prepared, database)
    assert preview["tracked_candidate_count_before_import"] == 499
    assert preview["accepted_count"] == 1
    assert preview["rejected_count"] == 1
    assert preview["rows"][1]["reason"] == "candidate_limit_reached"
    database.close()


def test_ui_exposes_imported_candidates_with_unverified_label(tmp_path):
    audit_db = tmp_path / "candidate-sidecar.sqlite3"
    db = connect(audit_db)
    prepared = prepare_batch(json.dumps(_batch(), ensure_ascii=False), TARGETS, expected_rank=2)
    apply_batch(db, prepared, source_file="batch.json")
    db.close()

    shown = recent_candidates(audit_db, 2, limit=10)
    assert len(shown) == 5
    assert all(row["verification_label"] == "Chưa xác minh nguồn" for row in shown)
    assert all(row["evidence_status"] == "SEARCH_SNIPPET_ONLY" for row in shown)
    opal = next(row for row in shown if "Opal Garden" in row["title"])
    assert opal["review_status"] == "SOURCE_CONFLICT"
    assert "xung đột" in opal["review_warning"]

    export_db = connect(audit_db)
    export_result = export(export_db, tmp_path / "exported")
    export_db.close()
    summary = json.loads(Path(export_result["summary"]).read_text(encoding="utf-8"))
    assert summary["candidate_count"] == 5
    assert summary["canonical_handoff_count"] == 0
    assert summary["evidence_status_counts"] == {"SEARCH_SNIPPET_ONLY": 5}


def test_sidecar_backup_and_production_demo_guards(tmp_path):
    existing = tmp_path / "sidecar.sqlite3"
    with sqlite3.connect(existing) as db:
        db.execute("CREATE TABLE sample(value TEXT)")
        db.execute("INSERT INTO sample VALUES('kept')")
    backup = backup_before_candidate_schema(existing)
    assert backup is not None and backup.exists()
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT value FROM sample").fetchone()[0] == "kept"

    production = tmp_path / "production.sqlite3"
    _targets_database(production)
    with pytest.raises(ValueError, match="canonical"):
        assert_isolated_audit_database(production, tmp_path / "targets.sqlite3")

    demo = tmp_path / "demo.sqlite3"
    with sqlite3.connect(demo) as db:
        db.execute("CREATE TABLE demo_meta(key TEXT)")
    with pytest.raises(ValueError, match="DEMO_MODE"):
        assert_isolated_audit_database(demo, tmp_path / "targets.sqlite3")
