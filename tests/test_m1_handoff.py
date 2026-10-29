"""Hand-off contract tests: answer_id / crawl_run_id / target_month and the append-only file."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wardprice import research_answers
from wardprice.research_answers import (
    append_to_master_jsonl,
    make_answer_id,
    make_crawl_run_id,
)

from support import admin_csv as admin_csv


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(research_answers, "DEFAULT_JSONL_DIR", tmp_path / "outputs")
    monkeypatch.setenv("OPENAI_MODEL", "gemma-4-31B-it")
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example/v1")
    monkeypatch.setenv("TAVILY_API_KEY", "k2")
    monkeypatch.setenv("LLM_ANSWERS_FILE", str(tmp_path / "data" / "llm_answers.jsonl"))
    monkeypatch.setattr("wardprice.research_provider.search_web", lambda _q, _s: [])
    return {
        "csv": admin_csv(tmp_path / "admin.csv"),
        "db": tmp_path / "answers.sqlite3",
        "master": tmp_path / "data" / "llm_answers.jsonl",
    }


def _crawl(env, period: str, master: bool = True):
    research_answers.prepare_jobs(
        period, administrative_code="00001", csv_path=env["csv"], database_path=env["db"]
    )
    return research_answers.run_batch(
        period, limit=1, database_path=env["db"], master_jsonl=env["master"] if master else None
    )


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_answer_id_depends_on_run_and_period_not_on_text():
    a = make_answer_id("run-1", "2026-10", "00001", "v1")
    assert a == make_answer_id("run-1", "2026-10", "00001", "v1")
    assert a != make_answer_id("run-1", "2026-11", "00001", "v1")  # same place, next month
    assert a != make_answer_id("run-2", "2026-10", "00001", "v1")  # same month, re-crawl
    assert len(a) == 32


def test_master_file_gets_new_fields_and_complete_lines(env):
    result = _crawl(env, "2026-10")
    assert result["master_appended"] == 1
    raw = env["master"].read_bytes()
    assert raw.endswith(b"\n")
    row = _lines(env["master"])[0]
    assert row["target_month"] == "2026-10"
    assert row["crawl_run_id"] == result["crawl_run_id"]
    assert row["answer_id"] == make_answer_id(row["crawl_run_id"], "2026-10", "00001", "nso-2026-10")


def test_appending_twice_does_not_duplicate(env):
    _crawl(env, "2026-10")
    assert append_to_master_jsonl("2026-10", env["master"], database_path=env["db"]) == 0
    assert len(_lines(env["master"])) == 1


def test_next_month_is_appended_not_overwritten(env):
    _crawl(env, "2026-10")
    _crawl(env, "2026-11")
    rows = _lines(env["master"])
    assert [r["target_month"] for r in rows] == ["2026-10", "2026-11"]
    assert rows[0]["answer_id"] != rows[1]["answer_id"]


def test_partial_last_line_is_isolated_not_glued(env):
    env["master"].parent.mkdir(parents=True)
    env["master"].write_bytes(b'{"answer_id": "broken')  # crashed writer, no newline
    _crawl(env, "2026-10")
    data = env["master"].read_text(encoding="utf-8").split("\n")
    assert data[0] == '{"answer_id": "broken'
    assert json.loads(data[1])["target_month"] == "2026-10"


def test_old_database_without_run_column_is_migrated_and_exported(env):
    research_answers.prepare_jobs(
        "2026-10", administrative_code="00001", csv_path=env["csv"], database_path=env["db"]
    )
    con = sqlite3.connect(env["db"])
    con.execute("ALTER TABLE research_answer_jobs DROP COLUMN crawl_run_id")
    con.execute(
        "UPDATE research_answer_jobs SET status='NO_RESULT', answer_text='KẾT QUẢ: CHƯA TÌM THẤY',"
        " crawled_at='2026-10-01T00:00:00Z'"
    )
    con.commit()
    con.close()
    assert append_to_master_jsonl("2026-10", env["master"], database_path=env["db"]) == 1
    assert _lines(env["master"])[0]["crawl_run_id"] == "research-2026-10-legacy"
    # opening through the normal path adds the column again
    conn = research_answers._connect(env["db"])
    research_answers._initialize(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(research_answer_jobs)")}
    conn.close()
    assert "crawl_run_id" in cols


def test_crawl_run_id_format():
    assert make_crawl_run_id("2026-10", "2026-10-28T03:30:00Z") == "research-2026-10-20261028T033000Z"


def test_cli_run_stops_when_nothing_pending(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(research_answers, "run_batch",
                        lambda *a, **k: calls.append(1) or {"status": "NO_PENDING_JOBS", "processed": 0, "job_counts": {}})
    assert research_answers.main(["run", "--period", "2026-10", "--batches", "3"]) == 0
    assert len(calls) == 1 and "NO_PENDING_JOBS" in capsys.readouterr().out


def test_master_path_priority_env_then_default(monkeypatch):
    from wardprice import config

    monkeypatch.setenv("LLM_ANSWERS_FILE", "custom/out.jsonl")
    assert research_answers._master_from_env() == config.REPO_ROOT / "custom/out.jsonl"
    monkeypatch.delenv("LLM_ANSWERS_FILE")
    assert research_answers._master_from_env() == config.REPO_ROOT / "data" / "llm_answers.jsonl"
    assert research_answers.DEFAULT_RESEARCH_DB.is_relative_to(config.DATA_DIR / "module1")
    assert research_answers.DEFAULT_ADMIN_CSV.is_file()


def test_usage_is_recorded_per_job_and_summarised(env, monkeypatch):
    from wardprice import research_provider

    research_answers.prepare_jobs(
        "2026-10", administrative_code="00001", csv_path=env["csv"], database_path=env["db"]
    )
    monkeypatch.setattr("wardprice.research_provider.search_web", lambda _q, _s: [
        {"title": "t", "url": "https://a.example/1", "content": "c", "published_date": ""}])

    def fake_summary(**kwargs):
        research_provider._record_usage(kwargs["usage_sink"], {"prompt_tokens": 1200, "completion_tokens": 300})
        return "KẾT QUẢ: TÌM THẤY\nGiá 4 tỷ [1].", "gemma"

    monkeypatch.setattr("wardprice.research_provider.summarize_search_results", fake_summary)
    result = research_answers.run_batch("2026-10", limit=1, database_path=env["db"])
    assert result["completed"] == 1
    summary = research_answers.usage_summary(period="2026-10", database_path=env["db"])
    assert summary["total"] == {"jobs": 1, "search_calls": 1, "model_calls": 1, "prompt_tokens": 1200,
                                "completion_tokens": 300, "usage_missing_calls": 0}
    assert summary["by_run"][0]["prompt_tokens"] == 1200


def test_failed_job_still_counts_the_search_and_retry_accumulates(env, monkeypatch):
    research_answers.prepare_jobs(
        "2026-10", administrative_code="00001", csv_path=env["csv"], database_path=env["db"]
    )
    monkeypatch.setattr("wardprice.research_provider.search_web", lambda _q, _s: [
        {"title": "t", "url": "https://a.example/1", "content": "c", "published_date": ""}])

    def boom(**_kwargs):
        raise RuntimeError("Gemma API trả HTTP 500.")

    monkeypatch.setattr("wardprice.research_provider.summarize_search_results", boom)
    assert research_answers.run_batch("2026-10", limit=1, database_path=env["db"])["failed"] == 1
    assert research_answers.run_batch("2026-10", limit=1, retry_failed=True, database_path=env["db"])["failed"] == 1
    total = research_answers.usage_summary(database_path=env["db"])["total"]
    assert total["search_calls"] == 2 and total["prompt_tokens"] == 0


def test_model_response_without_usage_is_counted_as_missing():
    from wardprice import research_provider

    sink: dict = {}
    research_provider._record_usage(sink, None)
    assert sink == {"model_calls": 1, "usage_missing_calls": 1}


def test_usage_summary_without_database(tmp_path):
    assert research_answers.usage_summary(database_path=tmp_path / "none.sqlite3")["total"]["jobs"] == 0
