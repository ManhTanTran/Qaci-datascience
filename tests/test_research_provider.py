"""Offline tests for the Tavily + OpenAI-compatible sourced Q&A pipeline."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from wardprice import research_answers, research_provider
from wardprice.api import create_app
from wardprice.config import ResearchAPISettings


def _settings() -> ResearchAPISettings:
    return ResearchAPISettings(
        model="gemma-4-31B-it",
        model_api_key="model-test-secret",
        model_base_url="https://inference.example/v1",
        search_api_key="search-test-secret",
    )


def _admin_csv(path: Path) -> Path:
    fields = [
        "administrative_code",
        "administrative_name",
        "administrative_level",
        "administrative_type",
        "province_code",
        "province_name",
        "administrative_version",
        "is_current",
        "valid_to",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "administrative_code": "00001",
                "administrative_name": "Phường Minh Hòa",
                "administrative_level": "COMMUNE",
                "administrative_type": "WARD",
                "province_code": "01",
                "province_name": "Thành phố Hà Nội",
                "administrative_version": "nso-2026-10",
                "is_current": "1",
                "valid_to": "",
            }
        )
    return path


def test_tavily_search_covers_open_web_and_rejects_non_https_urls(monkeypatch):
    captured = {}

    def fake_json(request, **_kwargs):
        captured["request"] = request
        return {
            "results": [
                {
                    "title": "Tin hợp lệ",
                    "url": "https://revalue.vn/gia-nha-dat/phuong-an-hoi-tay",
                    "content": "  Giá rao 4 tỷ.  ",
                    "published_date": "2026-10-01",
                },
                {"title": "Nguồn ngoài danh sách cũ", "url": "https://example.org/report", "content": "Báo cáo giá."},
                {"title": "Sai giao thức", "url": "http://nhatot.com/ad", "content": "x"},
                {"title": "Lặp URL", "url": "https://revalue.vn/gia-nha-dat/phuong-an-hoi-tay", "content": "trùng"},
            ]
        }

    monkeypatch.setattr(research_provider, "_request_json", fake_json)
    results = research_provider.search_web("giá nhà Minh Hòa Hà Nội", _settings())

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://api.tavily.com/search"
    assert request.get_header("Authorization") == "Bearer search-test-secret"
    assert body["search_depth"] == "basic"
    assert body["max_results"] == 12
    assert "include_domains" not in body
    assert "include_domains_mode" not in body
    assert len(results) == 2
    assert results[0]["content"] == "Giá rao 4 tỷ."
    assert results[1]["url"] == "https://example.org/report"


def test_provider_http_errors_identify_service_without_echoing_credentials(monkeypatch):
    def unauthorized(*_args, **_kwargs):
        raise HTTPError(
            "https://provider.example/search",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(research_provider, "urlopen", unauthorized)
    request = Request("https://provider.example/search", headers={"Authorization": "Bearer secret"})

    with pytest.raises(research_provider.ResearchProviderError, match="Tavily Search trả HTTP 401"):
        research_provider._request_json(request, service_name="Tavily Search")


def test_model_call_uses_openai_compatible_endpoint_and_sourced_prompt(monkeypatch):
    captured = {}

    def fake_json(request, **_kwargs):
        captured["request"] = request
        return {
            "model": "gemma-4-31B-it",
            "choices": [{"message": {"content": "KẾT QUẢ: TÌM THẤY\nGiá rao 4 tỷ [1]."}}],
        }

    monkeypatch.setattr(research_provider, "_request_json", fake_json)
    answer, model = research_provider.summarize_search_results(
        query_text="mã địa bàn 00001, Thành phố Hà Nội",
        search_query="giá nhà Minh Hòa Hà Nội 2026-10",
        results=[
            {
                "title": "Tin nhà",
                "url": "https://nhatot.com/ad/1",
                "content": "Giá rao 4 tỷ",
                "published_date": "2026-10-01",
            }
        ],
        settings=_settings(),
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://inference.example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer model-test-secret"
    assert body["model"] == "gemma-4-31B-it"
    assert "00001" in body["messages"][1]["content"]
    assert "https://nhatot.com/ad/1" in body["messages"][1]["content"]
    assert "Giá rao 4 tỷ" in body["messages"][1]["content"]
    assert "KẾT QUẢ: TÌM THẤY" in answer
    assert model == "gemma-4-31B-it"


def test_research_config_api_reports_provider_readiness_without_secret_values(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OPENAI_MODEL", "gemma-4-31B-it")
    monkeypatch.setenv("OPENAI_API_KEY", "model-test-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example/v1")
    monkeypatch.setenv("TAVILY_API_KEY", "search-test-secret")

    response = TestClient(create_app(tmp_path / "api.sqlite3")).get(
        "/api/v1/research-answers/config"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "model": "gemma-4-31B-it",
        "model_api_configured": True,
        "base_url_configured": True,
        "search_api_configured": True,
        "ready": True,
        "search_provider": "Tavily",
    }
    assert "model-test-secret" not in response.text
    assert "search-test-secret" not in response.text


def test_batch_without_search_results_skips_model_and_exports_partner_schema(
    monkeypatch, tmp_path
):
    admin_csv = _admin_csv(tmp_path / "admin.csv")
    database = tmp_path / "answers.sqlite3"
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(research_answers, "DEFAULT_JSONL_DIR", output_dir)
    monkeypatch.setenv("OPENAI_MODEL", "gemma-4-31B-it")
    monkeypatch.setenv("OPENAI_API_KEY", "model-test-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example/v1")
    monkeypatch.setenv("TAVILY_API_KEY", "search-test-secret")

    research_answers.prepare_jobs(
        "2026-10", administrative_code="00001", csv_path=admin_csv, database_path=database
    )
    calls = {"search": 0, "model": 0}

    def empty_search(_query, _settings):
        calls["search"] += 1
        return []

    def forbidden_model(**_kwargs):
        calls["model"] += 1
        raise AssertionError("Không được gọi model khi không có nguồn.")

    monkeypatch.setattr("wardprice.research_provider.search_web", empty_search)
    monkeypatch.setattr("wardprice.research_provider.summarize_search_results", forbidden_model)
    result = research_answers.run_batch("2026-10", limit=1, database_path=database)

    output_path = Path(result["jsonl_path"])
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert result["no_result"] == 1
    assert calls == {"search": 1, "model": 0}
    assert set(rows[0]) == {
        "crawled_at",
        "chatbot",
        "model_name",
        "query_text",
        "answer_text",
    }
    assert rows[0]["chatbot"] == "Gemma"
    assert rows[0]["model_name"] is None
    assert "00001" in rows[0]["query_text"]
    assert "CHƯA TÌM THẤY" in rows[0]["answer_text"]


def test_batch_includes_source_citations_in_answer_text(monkeypatch, tmp_path):
    admin_csv = _admin_csv(tmp_path / "admin.csv")
    database = tmp_path / "answers.sqlite3"
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(research_answers, "DEFAULT_JSONL_DIR", output_dir)
    monkeypatch.setenv("OPENAI_MODEL", "gemma-4-31B-it")
    monkeypatch.setenv("OPENAI_API_KEY", "model-test-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example/v1")
    monkeypatch.setenv("TAVILY_API_KEY", "search-test-secret")
    research_answers.prepare_jobs(
        "2026-10", administrative_code="00001", csv_path=admin_csv, database_path=database
    )
    monkeypatch.setattr(
        "wardprice.research_provider.search_web",
        lambda _query, _settings: [
            {
                "title": "Tin nhà",
                "url": "https://nhatot.com/ad/1",
                "content": "Bán nhà tại Minh Hòa, giá 4 tỷ.",
                "published_date": "2026-10-01",
            }
        ],
    )
    monkeypatch.setattr(
        "wardprice.research_provider.summarize_search_results",
        lambda **_kwargs: ("KẾT QUẢ: TÌM THẤY\nGiá rao 4 tỷ [1].", "gemma-4-31B-it"),
    )

    result = research_answers.run_batch("2026-10", limit=1, database_path=database)
    record = json.loads(Path(result["jsonl_path"]).read_text(encoding="utf-8").splitlines()[0])
    assert result["completed"] == 1
    assert "Giá rao 4 tỷ [1]" in record["answer_text"]
    assert "https://nhatot.com/ad/1" in record["answer_text"]


def test_export_does_not_create_empty_jsonl_without_completed_jobs(monkeypatch, tmp_path):
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(research_answers, "DEFAULT_JSONL_DIR", output_dir)
    database = tmp_path / "answers.sqlite3"
    connection = research_answers._connect(database)
    try:
        research_answers._initialize(connection)
    finally:
        connection.close()

    output_path = research_answers._export_jsonl("2026-10", database_path=database)

    assert output_path is None
    assert not output_dir.exists()
