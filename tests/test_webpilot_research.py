"""Offline tests for the Deep Research pilot; every Gemini call is mocked."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from wardprice_webpilot import __main__ as cli
from wardprice_webpilot.research import (
    CATEGORY_ONLY,
    SOURCE_PARTIAL,
    SOURCE_VERIFIED,
    UNVERIFIED,
    WEB_SEARCH_UNAVAILABLE,
    analyze_research_document,
    initialize_research_schema,
    make_deep_research_prompt,
    save_research_result,
    start_research_run,
)
from wardprice_webpilot.research_webclient import run_deep_research

TARGET = {
    "rank": 11,
    "ward": "Phường Bình Trị Đông",
    "district": "Quận Bình Tân",
    "province": "Thành phố Hồ Chí Minh",
}
DETAIL_URL = "https://muaban.net/bat-dong-san/ban-nha-binh-tri-dong-id12345678"
CATEGORY_URL = "https://muaban.net/bat-dong-san/quan-binh-tan-ho-chi-minh"


def _candidate(**overrides):
    result = {
        "title": "Nhà riêng bán Bình Trị Đông",
        "address": "Phường Bình Trị Đông, Quận Bình Tân, Thành phố Hồ Chí Minh",
        "property_type": "NHA_RIENG",
        "price_vnd": 7_800_000_000,
        "area_m2": 74.5,
        "source_citation_ids": [1],
        # A model URL is deliberately ignored; only Citation.url is eligible.
        "source_url": "https://model-invented.invalid/listing/1",
    }
    result.update(overrides)
    return result


def _report(*items):
    return (
        "Deep Research report\n\n```json\n"
        + json.dumps({"listings": list(items)}, ensure_ascii=False)
        + "\n```"
    )


def _detail_source(url=DETAIL_URL):
    return {"id": 1, "title": "Tin bán nhà", "url": url, "favicon": None}


def test_prompt_is_bounded_to_requested_ward_and_five_records():
    prompt = make_deep_research_prompt(TARGET, 5)
    assert "Phường Bình Trị Đông" in prompt
    assert "tối đa 5" in prompt
    assert "Không tự tạo" in prompt
    assert "AI_ESTIMATE" in prompt
    with pytest.raises(ValueError):
        make_deep_research_prompt(TARGET, 6)


def test_verified_candidate_uses_document_source_and_independent_page_text():
    page = (
        "Tin bán nhà riêng tại Phường Bình Trị Đông, Quận Bình Tân, "
        "Thành phố Hồ Chí Minh. Giá bán 7,8 tỷ. Diện tích 74,5 m2."
    )
    analysis = analyze_research_document(
        _report(_candidate()),
        [_detail_source()],
        TARGET,
        source_text_by_id={"1": page},
    )
    assert analysis["candidate_count"] == 1
    candidate = analysis["candidates"][0]
    assert candidate["evidence_status"] == SOURCE_VERIFIED
    assert candidate["source_url"] == DETAIL_URL
    assert candidate["source_url"] != _candidate()["source_url"]
    assert candidate["price_per_m2"] == pytest.approx(7_800_000_000 / 74.5)


def test_evidence_statuses_are_conservative():
    detail_no_page = analyze_research_document(_report(_candidate()), [_detail_source()], TARGET)
    assert detail_no_page["candidates"][0]["evidence_status"] == SOURCE_PARTIAL

    category = analyze_research_document(
        _report(_candidate()), [_detail_source(CATEGORY_URL)], TARGET
    )
    assert category["candidates"][0]["evidence_status"] == CATEGORY_ONLY

    no_citation = analyze_research_document(
        _report(_candidate(source_citation_ids=[], source_url=DETAIL_URL)),
        [_detail_source()],
        TARGET,
    )
    assert no_citation["candidates"][0]["evidence_status"] == UNVERIFIED
    assert no_citation["candidates"][0]["source_url"] is None


def test_empty_report_is_distinguished_from_empty_listing_results():
    unavailable = analyze_research_document("", [], TARGET)
    assert unavailable["web_search_status"] == WEB_SEARCH_UNAVAILABLE
    empty_results = analyze_research_document('{"listings":[]}', [], TARGET)
    assert empty_results["candidate_count"] == 0
    assert empty_results["web_search_status"] == "NO_SOURCES_RETURNED"


def test_invalid_estimate_wrong_ward_and_duplicates_are_rejected():
    duplicate = _candidate()
    wrong_ward = _candidate(
        address="Phường An Lạc, Quận Bình Tân, Thành phố Hồ Chí Minh",
        source_citation_ids=[2],
    )
    estimate = _candidate(record_type="AI_ESTIMATE", source_citation_ids=[3])
    analysis = analyze_research_document(
        _report(_candidate(), duplicate, wrong_ward, estimate),
        [
            _detail_source(),
            {"id": 2, "title": "wrong", "url": DETAIL_URL + "2"},
            {"id": 3, "title": "estimate", "url": DETAIL_URL + "3"},
        ],
        TARGET,
    )
    assert analysis["candidate_count"] == 1
    reasons = [entry["reason"] for entry in analysis["rejected_candidates"]]
    assert "exact_duplicate" in reasons
    assert "wrong_ward_quarantined" in reasons
    assert "ai_estimate_not_listing" in reasons
    assert analysis["duplicate_count"] == 1


def test_report_candidate_count_cannot_exceed_requested_count():
    items = [
        _candidate(
            title=f"Nhà riêng Bình Trị Đông số {index}",
            source_citation_ids=[index],
        )
        for index in range(1, 4)
    ]
    sources = [
        {
            "id": index,
            "title": f"listing {index}",
            "url": f"https://muaban.net/bat-dong-san/ban-nha-id1234567{index}",
        }
        for index in range(1, 4)
    ]
    analysis = analyze_research_document(
        _report(*items),
        sources,
        TARGET,
        requested_count=2,
    )
    assert analysis["candidate_count"] == 2
    assert analysis["invalid_candidate_count"] == 1


def test_sidecar_stores_raw_document_sources_and_candidates(tmp_path: Path):
    database = tmp_path / "research-audit.sqlite3"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    initialize_research_schema(connection)
    report = _report(_candidate())
    sources = [_detail_source()]
    analysis = analyze_research_document(report, sources, TARGET)
    run_id = start_research_run(
        connection,
        target_rank=11,
        requested_count=5,
        prompt_text=make_deep_research_prompt(TARGET, 5),
        status="OFFLINE_IMPORTED",
    )
    save_research_result(
        connection,
        run_id,
        status="OFFLINE_IMPORTED",
        web_search_status=analysis["web_search_status"],
        analysis=analysis,
        plan={"title": "mock plan"},
        document_id="mock-document",
        document_title="mock report",
        raw_document_text=report,
        result_metadata={"network_attempted": False},
    )
    assert (
        connection.execute(
            "SELECT raw_document_text FROM webpilot_research_runs WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        == report
    )
    assert connection.execute("SELECT COUNT(*) FROM webpilot_research_sources").fetchone()[0] == 1
    saved_candidate = connection.execute(
        "SELECT evidence_status,price_per_m2 FROM webpilot_research_candidates"
    ).fetchone()
    assert saved_candidate["evidence_status"] == SOURCE_PARTIAL
    assert saved_candidate["price_per_m2"] == pytest.approx(7_800_000_000 / 74.5)
    connection.close()


def test_gemini_client_runs_plan_start_poll_and_restores_cache_path(monkeypatch):
    events = []

    class FakeClient:
        def __init__(self, cookie, token, **kwargs):
            assert cookie == "test-cookie"
            assert token == "test-token"

        async def init(self, **kwargs):
            events.append("init")

        def start_chat(self, **kwargs):
            events.append("chat")
            return object()

        async def create_deep_research_plan(self, prompt, chat):
            events.append("plan")
            return SimpleNamespace(title="plan", query="topic", steps=["search"])

        async def start_deep_research(self, plan, chat):
            events.append("start")
            return object()

        async def wait_for_deep_research(self, plan, **kwargs):
            events.append("poll")
            document = SimpleNamespace(
                id="doc-1",
                title="report",
                content="mock report",
                sources=[SimpleNamespace(id=1, title="source", url=DETAIL_URL, favicon=None)],
            )
            return SimpleNamespace(done=True, document=document)

        async def close(self):
            events.append("close")

    package = ModuleType("gemini_webapi")
    package.GeminiClient = FakeClient
    monkeypatch.setitem(sys.modules, "gemini_webapi", package)
    monkeypatch.setenv("GEMINI_SECURE_1PSID", "test-cookie")
    monkeypatch.setenv("GEMINI_SECURE_1PSIDTS", "test-token")
    monkeypatch.setenv("GEMINI_COOKIE_PATH", "existing-cache-path")

    result = asyncio.run(run_deep_research("prompt", poll_interval=0.1, timeout=1))
    assert events == ["init", "chat", "plan", "start", "poll", "close"]
    assert result["document_text"] == "mock report"
    assert result["sources"][0]["url"] == DETAIL_URL
    assert result["plan"]["title"] == "plan"
    assert "test-cookie" not in json.dumps(result)
    assert __import__("os").environ["GEMINI_COOKIE_PATH"] == "existing-cache-path"


def test_cli_dry_run_and_unconfirmed_live_do_not_write_or_call(tmp_path, monkeypatch, capsys):
    targets_db = tmp_path / "targets.sqlite3"
    audit_db = tmp_path / "audit.sqlite3"
    monkeypatch.setattr(cli, "load_targets", lambda path: {11: TARGET})
    monkeypatch.setattr(
        "wardprice_webpilot.research_webclient.run_deep_research",
        lambda *args, **kwargs: pytest.fail("live function must not be called"),
    )

    assert (
        cli.main(
            ["--targets-db", str(targets_db), "--db", str(audit_db), "research", "--rank", "11"]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "DRY_RUN_ONLY"
    assert output["network_attempted"] is False
    assert not audit_db.exists()

    with pytest.raises(ValueError, match="confirm-single-live-deep-research"):
        cli.main(
            [
                "--targets-db",
                str(targets_db),
                "--db",
                str(audit_db),
                "research",
                "--rank",
                "11",
                "--live",
            ]
        )
    assert not audit_db.exists()


def test_cli_research_import_stores_only_in_sidecar(tmp_path, monkeypatch, capsys):
    targets_db = tmp_path / "main-targets.sqlite3"
    audit_db = tmp_path / "research-sidecar.sqlite3"
    report_file = tmp_path / "report.md"
    sources_file = tmp_path / "sources.json"
    report_file.write_text(_report(_candidate()), encoding="utf-8")
    sources_file.write_text(json.dumps([_detail_source()]), encoding="utf-8")
    monkeypatch.setattr(cli, "load_targets", lambda path: {11: TARGET})

    assert (
        cli.main(
            [
                "--targets-db",
                str(targets_db),
                "--db",
                str(audit_db),
                "research-import",
                "--rank",
                "11",
                "--file",
                str(report_file),
                "--sources-file",
                str(sources_file),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "OFFLINE_IMPORTED"
    assert result["candidate_evidence_counts"] == {SOURCE_PARTIAL: 1}
    assert result["production_database_written"] is False
    assert not targets_db.exists()
    with sqlite3.connect(audit_db) as connection:
        assert connection.execute(
            "SELECT raw_document_text FROM webpilot_research_runs"
        ).fetchone()[0] == report_file.read_text(encoding="utf-8")
        assert (
            connection.execute("SELECT COUNT(*) FROM webpilot_research_candidates").fetchone()[0]
            == 1
        )


def test_daily_deep_research_cap_blocks_before_client_call(tmp_path, monkeypatch):
    targets_db = tmp_path / "main.sqlite3"
    audit_db = tmp_path / "audit.sqlite3"
    connection = sqlite3.connect(audit_db)
    initialize_research_schema(connection)
    start_research_run(
        connection,
        target_rank=11,
        requested_count=5,
        prompt_text="previous live attempt",
    )
    connection.close()
    monkeypatch.setattr(cli, "load_targets", lambda path: {11: TARGET})
    monkeypatch.setattr(cli, "_check_deep_research_prerequisites", lambda: None)
    monkeypatch.setattr(
        "wardprice_webpilot.research_webclient.run_deep_research",
        lambda *args, **kwargs: pytest.fail("daily cap must block before Gemini"),
    )

    with pytest.raises(ValueError, match="daily workflow cap reached"):
        cli.main(
            [
                "--targets-db",
                str(targets_db),
                "--db",
                str(audit_db),
                "research",
                "--rank",
                "11",
                "--live",
                "--confirm-single-live-deep-research",
            ]
        )

    with sqlite3.connect(audit_db) as stored:
        assert stored.execute("SELECT COUNT(*) FROM webpilot_research_runs").fetchone()[0] == 1


def test_mock_live_cli_persists_report_and_citations_only_to_sidecar(tmp_path, monkeypatch, capsys):
    targets_db = tmp_path / "main.sqlite3"
    audit_db = tmp_path / "audit.sqlite3"
    inbox = tmp_path / "deep-research"
    report = _report(_candidate())
    sources = [_detail_source()]
    monkeypatch.setattr(cli, "load_targets", lambda path: {11: TARGET})
    monkeypatch.setattr(cli, "_check_deep_research_prerequisites", lambda: None)

    async def fake_live(prompt, **kwargs):
        assert "Phường Bình Trị Đông" in prompt
        return {
            "plan": {"title": "mock plan"},
            "done": True,
            "document_id": "mock-doc",
            "document_title": "mock report",
            "document_text": report,
            "sources": sources,
        }

    monkeypatch.setattr("wardprice_webpilot.research_webclient.run_deep_research", fake_live)
    assert (
        cli.main(
            [
                "--targets-db",
                str(targets_db),
                "--db",
                str(audit_db),
                "research",
                "--rank",
                "11",
                "--count",
                "5",
                "--live",
                "--confirm-single-live-deep-research",
                "--save-to-inbox",
                str(inbox),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["candidate_count"] == 1
    assert result["candidate_evidence_counts"] == {SOURCE_PARTIAL: 1}
    assert result["production_database_written"] is False
    assert Path(result["raw_document_file"]).read_text(encoding="utf-8") == report
    assert json.loads(Path(result["sources_file"]).read_text(encoding="utf-8")) == sources
    assert not targets_db.exists()
    with sqlite3.connect(audit_db) as stored:
        assert stored.execute(
            "SELECT status,raw_document_text FROM webpilot_research_runs"
        ).fetchone() == ("LIVE_COMPLETE", report)
        assert stored.execute("SELECT COUNT(*) FROM webpilot_research_sources").fetchone()[0] == 1
        assert (
            stored.execute("SELECT COUNT(*) FROM webpilot_research_candidates").fetchone()[0] == 1
        )
