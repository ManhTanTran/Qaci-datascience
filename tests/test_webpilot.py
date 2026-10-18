"""Offline tests for the isolated Gemini Web candidate adapter."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from wardprice.__main__ import main as wardprice_main
from wardprice.database import connect as connect_wardprice
from wardprice_webpilot import __main__ as webpilot_cli
from wardprice_webpilot.core import (
    EVIDENCE_UNVERIFIED,
    connect,
    export,
    geo_check,
    import_payload,
    import_response,
    load_targets,
    make_prompt,
    parse_json_text,
    process_response_for_run,
    start_run,
    status,
    validate_listing,
)
from wardprice_webpilot.pipeline_bridge import (
    import_webpilot_handoff,
    preview_webpilot_handoff,
)
from wardprice_webpilot.webclient import collect_from_web

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "gemini_batch50_as_received.txt"
MAIN_DB = ROOT / "state" / "ward_prices.sqlite3"


def _fixture_targets() -> dict[int, dict[str, str]]:
    return {
        rank: {
            "rank": rank,
            "ward": f"Phường Mẫu {rank}",
            "district": "Quận Mẫu",
            "province": "Thành phố Mẫu",
        }
        for rank in range(1, 51)
    }


def _listing(targets=None, rank: int = 2, **overrides):
    registry = targets or _fixture_targets()
    target = registry[rank]
    row = {
        "target_rank": rank,
        "original_ward": target["ward"],
        "property_type": "CHUNG_CU",
        "title": "Căn hộ hai phòng ngủ gần công viên",
        "address": f"{target['ward']}, {target['district']}",
        "price_vnd": 3_500_000_000,
        "area_m2": 70,
        "source_website": "example.com",
        "source_url": None,
    }
    row.update(overrides)
    return row


def _canonical_counts(database: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "ward_target_legacy",
                "ward_registry",
                "listings",
                "listing_history",
                "listing_search_runs",
                "valuations",
            )
        }
    finally:
        connection.close()


def _canonical_test_database(path: Path):
    database = connect_wardprice(path)
    database.execute(
        """INSERT INTO ward_registry(
            ward_code,ward_name,province,district,admin_source,active,imported_at
        ) VALUES(?,?,?,?,?,1,?)""",
        (
            "TOP50-001",
            "Phường Bình Hưng Hòa",
            "Thành phố Hồ Chí Minh",
            "Quận Bình Tân",
            None,
            "2026-10-12T00:00:00+00:00",
        ),
    )
    database.execute(
        """INSERT INTO ward_target_legacy(
            rank,old_province,old_district,old_ward,category,n_customers,pct,batch,
            current_province,current_ward,current_ward_code,status,mapping_note,source_url,
            imported_at
        ) VALUES(1,?,?,?,?,?,?,?,?,?,NULL,'PENDING_ADMIN_MAPPING',?,?,?)""",
        (
            "Thành phố Hồ Chí Minh",
            "Quận Bình Tân",
            "Phường Bình Hưng Hòa",
            "PHƯỜNG",
            0,
            0.0,
            1,
            "",
            "",
            "Mapping intentionally left pending",
            "",
            "2026-10-12T00:00:00+00:00",
        ),
    )
    database.commit()
    return database


def _handoff_listing(**overrides):
    listing = {
        "target_rank": 1,
        "original_ward": "Phường Bình Hưng Hòa",
        "original_district": "Quận Bình Tân",
        "original_province": "Thành phố Hồ Chí Minh",
        "property_type": "DAT_O",
        "title": "Đất thổ cư gần đường số 5",
        "address": "Phường Bình Hưng Hòa, Quận Bình Tân, Thành phố Hồ Chí Minh",
        "price_vnd": 3_000_000_000,
        "area_m2": 60,
        "source_url": "https://example.com/listing/1",
        "published_at": None,
        "evidence_status": "SEARCH_SNIPPET_ONLY",
        "source_page_read": False,
        "price_evidence": "Giá bán 3 tỷ đồng",
        "area_evidence": "Diện tích 60 m2",
        "evidence_excerpt": "Giá bán 3 tỷ đồng, diện tích 60 m2",
        "grounded_urls": ["https://www.example.com/listing/1?utm_source=search"],
    }
    listing.update(overrides)
    return listing


def test_loads_50_targets_read_only_from_ward_target_legacy(tmp_path):
    database = tmp_path / "targets.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE ward_target_legacy(rank INTEGER, old_ward TEXT, old_district TEXT, old_province TEXT)"
    )
    connection.executemany(
        "INSERT INTO ward_target_legacy VALUES(?,?,?,?)",
        [
            (rank, f"Phường Mẫu {rank}", "Quận Mẫu", "Thành phố Mẫu")
            for rank in range(1, 51)
        ],
    )
    connection.commit()
    connection.close()

    assert len(load_targets(database)) == 50
    check = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        assert check.execute("SELECT COUNT(*) FROM ward_target_legacy").fetchone()[0] == 50
        assert "n_customers" not in " ".join(
            row[1] for row in check.execute("PRAGMA table_info(ward_target_legacy)")
        )
    finally:
        check.close()


def test_batch_size_limit_is_500(tmp_path):
    targets = _fixture_targets()
    records = [_listing(targets, rank=(index % 50) + 1) for index in range(501)]
    database = connect(tmp_path / "audit.sqlite3")
    try:
        with pytest.raises(ValueError, match="500"):
            import_payload(database, records, targets)
    finally:
        database.close()


def test_exact_duplicate_is_ignored_on_reimport(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    payload = {"listings": [_listing()]}
    first = import_payload(database, payload, _fixture_targets())
    second = import_payload(database, payload, _fixture_targets())

    assert first["inserted_candidates"] == 1
    assert second["duplicates_exact"] == 1
    assert status(database)["candidate_count"] == 1
    database.close()


def test_whitelist_and_geo_quarantine(tmp_path):
    targets = _fixture_targets()
    targets[1]["ward"] = "Phường Bình Hưng Hòa"
    database = connect(tmp_path / "audit.sqlite3")
    wrong_rank = _listing(targets, rank=1, original_ward="Phường Mẫu 2")
    wrong_geo = _listing(
        targets,
        rank=1,
        address="Phường Bình Hưng Hòa B, Quận Bình Tân",
    )
    result = import_payload(database, {"listings": [wrong_rank, wrong_geo]}, targets)

    assert result["rejected"] == 1
    assert result["rejected_reasons"] == {"target_ward_disagrees_with_registry": 1}
    assert status(database)["candidate_count"] == 1
    assert status(database)["geo_mismatch"] == 1
    assert status(database)["quarantined"] == 1
    database.close()


def test_geo_check_detects_specific_old_ward_mismatch():
    assert (
        geo_check("Phường Bình Hưng Hòa B, Quận Bình Tân", "Phường Bình Hưng Hòa")
        == "MISMATCH"
    )
    assert (
        geo_check("Phường Bình Hưng Hòa, Quận Bình Tân", "Phường Bình Hưng Hòa")
        == "MATCH"
    )
    assert geo_check("Đường Vĩnh Lộc, Huyện Bình Chánh", "Xã Vĩnh Lộc A") == "REVIEW"


def test_empty_gemini_response_is_persisted_without_candidates(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    result = import_response(database, "", _fixture_targets(), origin="fake_gemini")

    assert result["status"] == "EMPTY_RESPONSE"
    assert status(database)["candidate_count"] == 0
    assert database.execute("SELECT status FROM webpilot_runs").fetchone()[0] == "EMPTY_RESPONSE"
    database.close()


def test_invalid_gemini_json_schema_is_recorded(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    result = import_response(
        database,
        '{"listings": {"not": "an array"}}',
        _fixture_targets(),
        origin="fake_gemini",
    )

    assert result["status"] == "SCHEMA_FAILURE"
    run = database.execute(
        "SELECT status,raw_response_text FROM webpilot_runs"
    ).fetchone()
    assert run["status"] == "SCHEMA_FAILURE"
    assert run["raw_response_text"] == '{"listings": {"not": "an array"}}'
    database.close()


def test_listing_price_per_square_meter_and_evidence_stay_unverified():
    listing = _listing(price_vnd=3_500_000_000, area_m2=70)
    validated, error = validate_listing(listing, _fixture_targets())

    assert error is None
    assert validated["price_per_m2"] == 50_000_000
    assert validated["evidence_status"] == EVIDENCE_UNVERIFIED


def test_self_reported_search_and_model_evidence_do_not_promote_listing(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    listing = _listing(
        source_url="https://example.com/listing/123",
        evidence_status="SOURCE_PAGE_CONFIRMED",
        source_page_read=True,
    )
    result = import_payload(
        database,
        {"web_search_used": True, "listings": [listing]},
        _fixture_targets(),
        citations=[{"title": "Listing", "url": "https://www.example.com/listing/123?ref=search"}],
        raw_response_text='{"web_search_used":true}',
    )

    row = database.execute(
        "SELECT evidence_status,source_url FROM webpilot_candidates"
    ).fetchone()
    run = database.execute(
        "SELECT citation_count,citation_url_match_count,raw_response_text FROM webpilot_runs"
    ).fetchone()
    assert result["web_search_claim"] == "SELF_REPORTED_SEARCH"
    assert row["evidence_status"] == "UNVERIFIED"
    assert run["citation_count"] == 1
    assert run["citation_url_match_count"] == 1
    assert run["raw_response_text"] == '{"web_search_used":true}'
    database.close()


def test_actual_citation_and_price_area_quotes_enable_snippet_handoff(tmp_path):
    targets = {
        1: {
            "rank": 1,
            "ward": "Phường Bình Hưng Hòa",
            "district": "Quận Bình Tân",
            "province": "Thành phố Hồ Chí Minh",
        }
    }
    sidecar = connect(tmp_path / "audit.sqlite3")
    row = _listing(
        targets,
        rank=1,
        source_url="https://example.com/listing/1",
        address="Phường Bình Hưng Hòa, Quận Bình Tân, Thành phố Hồ Chí Minh",
        evidence_status="SOURCE_PAGE_CONFIRMED",
        source_page_read=True,
        price_evidence="Giá bán 3 tỷ đồng",
        area_evidence="Diện tích 60 m2",
        evidence_excerpt="Giá bán 3 tỷ đồng, diện tích 60 m2",
    )
    imported = import_payload(
        sidecar,
        {"web_search_used": False, "listings": [row]},
        targets,
        citations=[{"title": "Tin rao", "url": "https://www.example.com/listing/1?ref=search"}],
    )

    status_row = sidecar.execute(
        "SELECT evidence_status,source_page_read,raw_payload FROM webpilot_candidates"
    ).fetchone()
    assert imported["web_search_claim"] == "NO_WEB_SEARCH"
    assert imported["listing_urls_matching_citations"] == 1
    assert imported["price_area_valid_count"] == 1
    assert imported["evidence_status_counts"] == {"SEARCH_SNIPPET_ONLY": 1}
    assert imported["source_verified_count"] == 0
    assert imported["wrapper_citations"][0]["url"].startswith("https://www.example.com/")
    assert imported["listing_source_urls"] == ["https://example.com/listing/1"]
    assert status_row["evidence_status"] == "SEARCH_SNIPPET_ONLY"
    assert status_row["source_page_read"] == 0
    assert json.loads(status_row["raw_payload"])["source_page_read"] is True
    sidecar.close()

    audit = connect(tmp_path / "audit-export.sqlite3")
    import_payload(
        audit,
        {"listings": [row]},
        targets,
        citations=[{"title": "Tin rao", "url": "https://www.example.com/listing/1?ref=search"}],
    )
    files = export(audit, tmp_path / "handoff")
    handoff = json.loads(Path(files["import_json"]).read_text(encoding="utf-8"))
    assert files["eligible_candidates"] == 1
    assert handoff["listings"][0]["grounded_urls"] == [
        "https://www.example.com/listing/1?ref=search"
    ]

    canonical = _canonical_test_database(tmp_path / "canonical.sqlite3")
    preview = preview_webpilot_handoff(canonical, handoff)
    assert preview["eligible_count"] == 1
    assert canonical.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0

    first = import_webpilot_handoff(canonical, handoff)
    second = import_webpilot_handoff(canonical, handoff)
    assert first["inserted"] == 1
    assert second["updated"] == 1
    assert canonical.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
    assert canonical.execute("SELECT COUNT(*) FROM listing_history").fetchone()[0] == 2
    assert canonical.execute(
        "SELECT evidence_status FROM listings"
    ).fetchone()[0] == "SEARCH_SNIPPET_ONLY"
    assert canonical.execute(
        "SELECT current_ward_code FROM ward_target_legacy WHERE rank=1"
    ).fetchone()[0] is None
    audit.close()
    canonical.close()


def test_gemini_web_import_cli_previews_by_default_and_applies_only_explicitly(
    tmp_path, capsys, monkeypatch
):
    canonical = _canonical_test_database(tmp_path / "canonical.sqlite3")
    canonical.close()
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(
        json.dumps({"listings": [_handoff_listing()]}, ensure_ascii=False),
        encoding="utf-8",
    )
    args = ["import-gemini-web", "--file", str(handoff_file), "--db", str(tmp_path / "canonical.sqlite3")]

    monkeypatch.setattr(sys, "argv", ["wardprice", *args])
    assert wardprice_main() is None
    preview = json.loads(capsys.readouterr().out)
    assert preview["mode"] == "DRY_RUN"
    assert preview["eligible_count"] == 1, preview.get("rejected")
    check = sqlite3.connect(tmp_path / "canonical.sqlite3")
    assert check.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0
    check.close()

    monkeypatch.setattr(sys, "argv", ["wardprice", *args, "--apply"])
    assert wardprice_main() is None
    applied = json.loads(capsys.readouterr().out)
    assert applied["mode"] == "APPLY"
    assert applied["inserted"] == 1
    check = sqlite3.connect(tmp_path / "canonical.sqlite3")
    assert check.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
    check.close()


def test_export_keeps_unverified_candidates_out_of_canonical_handoff(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    import_payload(database, {"listings": [_listing()]}, _fixture_targets())
    paths = export(database, tmp_path / "out")

    handoff = json.loads(Path(paths["import_json"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    assert paths["eligible_candidates"] == 0
    assert handoff["listings"] == []
    assert summary["statistics_computed"] is False
    assert "mean" not in Path(paths["summary"]).read_text(encoding="utf-8").casefold()
    database.close()


def test_response_raw_prompt_metadata_and_empty_parse_are_audited(tmp_path):
    database = connect(tmp_path / "audit.sqlite3")
    run_id = start_run(
        database,
        origin="fake_gemini",
        requested_rank=2,
        prompt_text="one ward prompt",
        request_metadata={"model": "mock", "attempt": 1},
    )
    result = process_response_for_run(database, run_id, "not json", _fixture_targets())
    row = database.execute(
        """SELECT prompt_text,request_metadata_json,raw_response_text,status
           FROM webpilot_runs WHERE run_id=?""",
        (run_id,),
    ).fetchone()

    assert result["status"] == "PARSE_FAILURE"
    assert row["prompt_text"] == "one ward prompt"
    assert json.loads(row["request_metadata_json"]) == {"attempt": 1, "model": "mock"}
    assert row["raw_response_text"] == "not json"
    assert row["status"] == "PARSE_FAILURE"
    database.close()


def test_prompt_excludes_customer_fields():
    prompt = make_prompt(_fixture_targets()[1], count=5)
    assert "n_customers" not in prompt
    assert "pct" not in prompt
    assert "tối đa 5" in prompt


def test_json_parser_handles_markdown_and_rejects_empty():
    parsed = parse_json_text('```json\n{"listings": []}\n```')
    assert parsed == {"listings": []}
    with pytest.raises(ValueError, match="empty"):
        parse_json_text("  ")


def test_webclient_makes_one_fake_generation_call_without_printing_session(
    monkeypatch, capsys, tmp_path
):
    calls = {"init": 0, "generate": 0, "close": 0, "kwargs": {}}

    class FakeGeminiClient:
        def __init__(self, cookie, token, proxy=None, verbose=False):
            calls["credentials_received"] = bool(cookie) and token is None
            calls["proxy"] = proxy
            calls["verbose"] = verbose

        async def init(self, **kwargs):
            calls["init"] += 1
            calls["init_kwargs"] = kwargs

        async def generate_content(self, prompt, **kwargs):
            calls["generate"] += 1
            calls["kwargs"] = kwargs
            return SimpleNamespace(
                text='{"listings": []}',
                citations=[SimpleNamespace(title="Source", url="https://example.com")],
            )

        async def close(self):
            calls["close"] += 1
            cache_path = Path(os.environ["GEMINI_COOKIE_PATH"])
            calls["temporary_cache"] = cache_path
            (cache_path / "mock-cookie-cache.txt").write_text("test-session-secret")

    fake_module = ModuleType("gemini_webapi")
    fake_module.GeminiClient = FakeGeminiClient
    monkeypatch.setitem(sys.modules, "gemini_webapi", fake_module)
    monkeypatch.setenv("GEMINI_SECURE_1PSID", "test-session-secret")
    monkeypatch.delenv("GEMINI_SECURE_1PSIDTS", raising=False)
    monkeypatch.setenv("GEMINI_COOKIE_PATH", str(tmp_path / "original-cache"))

    response_text, citations = asyncio.run(collect_from_web("fake prompt", model="mock-model"))

    assert calls["init"] == calls["generate"] == calls["close"] == 1
    assert calls["kwargs"] == {"current_retry": 0, "model": "mock-model"}
    assert calls["init_kwargs"]["auto_refresh"] is False
    assert response_text == '{"listings": []}'
    assert citations == [{"title": "Source", "url": "https://example.com"}]
    assert not calls["temporary_cache"].exists()
    assert sys.modules["gemini_webapi"] is fake_module
    assert os.environ["GEMINI_COOKIE_PATH"] == str(tmp_path / "original-cache")
    assert "test-session-secret" not in capsys.readouterr().out


def test_live_cli_allows_three_attempts_per_day_and_blocks_the_fourth(
    tmp_path, capsys, monkeypatch
):
    calls = []
    audit_path = tmp_path / "webpilot.sqlite3"
    inbox_path = tmp_path / "inbox"

    async def fake_collect(prompt, model=None):
        calls.append((prompt, model))
        return '{"listings": []}', []

    monkeypatch.setattr(webpilot_cli, "load_targets", lambda _path: _fixture_targets())
    monkeypatch.setattr(webpilot_cli.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr("wardprice_webpilot.webclient.collect_from_web", fake_collect)
    monkeypatch.setenv("GEMINI_SECURE_1PSID", "fake-test-session")

    base_args = [
        "--targets-db",
        str(tmp_path / "targets.sqlite3"),
        "--db",
        str(audit_path),
        "collect",
        "--rank",
        "11",
        "--count",
        "1",
        "--live",
        "--confirm-single-live-call",
        "--save-to-inbox",
        str(inbox_path),
    ]
    for _ in range(3):
        assert webpilot_cli.main(base_args) == 0
        capsys.readouterr()

    with pytest.raises(ValueError, match=r"Daily live call cap reached \(3/3\)"):
        webpilot_cli.main(base_args)

    assert len(calls) == 3
    audit = connect(audit_path)
    assert audit.execute(
        "SELECT COUNT(*) FROM webpilot_runs WHERE origin='gemini_web_attempt'"
    ).fetchone()[0] == 3
    metadata = json.loads(
        audit.execute(
            "SELECT request_metadata_json FROM webpilot_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()[0]
    )
    assert metadata["daily_call_cap"] == 3
    assert metadata["daily_call_number"] == 3
    audit.close()


@pytest.mark.skipif(not MAIN_DB.is_file(), reason="local Top50 SQLite registry is unavailable")
def test_supplied_batch50_offline_uses_temp_audit_db_and_is_idempotent(tmp_path):
    targets = load_targets(MAIN_DB)
    before = _canonical_counts(MAIN_DB)
    response_text = SAMPLE.read_text(encoding="utf-8-sig")
    audit = connect(tmp_path / "sample-audit.sqlite3")

    first = import_response(
        audit,
        response_text,
        targets,
        origin="sample_batch50",
        request_metadata={"source_file": str(SAMPLE), "mode": "offline_test"},
    )
    second = import_response(
        audit,
        response_text,
        targets,
        origin="sample_batch50_reimport",
        request_metadata={"source_file": str(SAMPLE), "mode": "offline_test"},
    )
    current = status(audit)
    files = export(audit, tmp_path / "sample-output")
    handoff = json.loads(Path(files["import_json"]).read_text(encoding="utf-8"))

    assert first["received"] == 50
    assert first["rejected"] == 0
    assert first["inserted_candidates"] == 50
    assert second["duplicates_exact"] == 50
    assert current["candidate_count"] == 50
    assert current["geo_match"] == 44
    assert current["geo_mismatch"] == 5
    assert current["geo_review"] == 1
    assert current["url_present_unverified"] == 0
    assert current["verified_listing_count"] == 0
    assert audit.execute(
        "SELECT COUNT(DISTINCT evidence_status) FROM webpilot_candidates"
    ).fetchone()[0] == 1
    assert audit.execute(
        "SELECT MIN(evidence_status) FROM webpilot_candidates"
    ).fetchone()[0] == "UNVERIFIED"
    assert files["eligible_candidates"] == 0
    assert handoff["listings"] == []
    assert _canonical_counts(MAIN_DB) == before
    audit.close()
