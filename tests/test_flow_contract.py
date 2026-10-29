"""Module 1 -> hand-off file -> runner -> SQLite, end to end (network/LLM faked)."""

import csv
import json
import re

from claims_extractor import stats
from claims_extractor.models import AnswerRecord
from common.schema import compute_observation_answer_id
from pipeline.runner import Runner
from wardprice import research_answers

SOURCES = [{"title": "Báo cáo giá", "url": "https://nhatot.example/bao-cao", "content": "x", "published_date": "2026-10-05"}]
ANSWER = "KẾT QUẢ: TÌM THẤY\nNguồn A ghi giá chào bán nhà riêng 70 - 95 triệu/m² [1].\nGiới hạn: chỉ một nguồn."


def admin_csv(path, n=3):
    fields = ["administrative_code", "administrative_name", "administrative_level", "administrative_type",
              "province_code", "province_name", "administrative_version", "is_current", "valid_to"]
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        for i in range(1, n + 1):
            w.writerow({"administrative_code": f"{i:05d}", "administrative_name": f"Phường Số {i}",
                        "administrative_level": "COMMUNE", "administrative_type": "WARD", "province_code": "01",
                        "province_name": "Thành phố Hà Nội", "administrative_version": "nso-2026-10",
                        "is_current": "1", "valid_to": ""})
    return path


class EchoLLM:
    name = "echo"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        ward = re.search(r"tại (?:Phường )?(.+?), Thành phố", user).group(1)
        return json.dumps({"claims": [{
            "ward": ward, "province": "Hà Nội", "property_type": "NHA_RIENG", "price_basis": "MARKET",
            "metric": "typical_range", "value_low": 70000000, "value_high": 95000000,
            "unit_original": "triệu/m²", "qualifier": "giá chào bán",
            "quote": "giá chào bán nhà riêng 70 - 95 triệu/m² [1]"}]})


def crawl(monkeypatch, tmp_path, period, master, results=SOURCES, answer=ANSWER, n=3):
    monkeypatch.setattr(research_answers, "DEFAULT_JSONL_DIR", tmp_path / "outputs")
    for k, v in {"OPENAI_API_KEY": "a", "OPENAI_BASE_URL": "https://x.example/v1", "TAVILY_API_KEY": "b"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("wardprice.research_provider.search_web", lambda q, s: results)
    monkeypatch.setattr("wardprice.research_provider.summarize_search_results",
                        lambda **kw: (answer, "gemma-test"))
    db = tmp_path / "m1.sqlite3"
    research_answers.prepare_jobs(period, csv_path=admin_csv(tmp_path / "admin.csv", n), database_path=db)
    return research_answers.run_batch(period, limit=n, database_path=db, master_jsonl=master)


def test_module1_lines_satisfy_module2_contract(monkeypatch, cfg, tmp_path):
    crawl(monkeypatch, tmp_path, "2026-10", cfg.input_file)
    lines = cfg.input_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for line in lines:
        raw = json.loads(line)
        rec = AnswerRecord.model_validate(raw)
        assert rec.answer_id == raw["answer_id"] and rec.target_month == "2026-10"
        code = re.search(r"mã địa bàn (\d+)", raw["query_text"]).group(1)
        assert raw["answer_id"] == compute_observation_answer_id(
            raw["crawl_run_id"], raw["target_month"], code, "nso-2026-10")


def test_end_to_end_two_months_then_idempotent_rerun(monkeypatch, cfg, tmp_path):
    llm = EchoLLM()
    runner = Runner(cfg, llm_factory=lambda _c: llm)
    crawl(monkeypatch, tmp_path, "2026-09", cfg.input_file)
    first = runner.run_once("e2e")
    assert (first["registered"], first["ok"], first["claims"]) == (3, 3, 3)

    crawl(monkeypatch, tmp_path, "2026-10", cfg.input_file)     # same places, next month
    second = runner.run_once("e2e")
    assert (second["registered"], second["ok"], second["claims"]) == (3, 3, 3)

    third = runner.run_once("e2e")                               # nothing new
    assert third["registered"] == 0 and third["processed"] == 0 and llm.calls == 6

    with runner.open_store() as s:
        months = {r["month"]: r["claims"] for r in stats.quality(s)["by_month"]}
        assert months == {"2026-09": 3, "2026-10": 3}
        claim = next(s.iter_claims("real_estate", "2026-10"))
        assert claim["source_urls"] == ["https://nhatot.example/bao-cao"]
        assert claim["crawl_run_id"].startswith("research-2026-10-")


def test_no_result_answers_cost_no_llm_calls(monkeypatch, cfg, tmp_path):
    crawl(monkeypatch, tmp_path, "2026-10", cfg.input_file, results=[])
    llm = EchoLLM()
    out = Runner(cfg, llm_factory=lambda _c: llm).run_once("e2e")
    assert (out["empty"], out["llm_calls"]) == (3, 0) and llm.calls == 0
