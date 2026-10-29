from claims_extractor import stats
from claims_extractor.domains.real_estate.sources import (
    declares_no_result, resolve_citations, split_sources)
from claims_extractor.ingest import ingest_file
from claims_extractor.pipeline import process_pending
from support import FakeLLM, claims_json, make_claim
import json

ANSWER = """KẾT QUẢ: TÌM THẤY
Nguồn A (cập nhật 10/2026) ghi giá chào bán 70 - 95 triệu/m² cho nhà riêng [1].
Nguồn B ghi giá trung vị 82 triệu/m² [2].

Nguồn tìm kiếm (Tavily; chỉ lưu URL và tiêu đề):
[1] Báo cáo A · ngày nguồn: 2026-10-05 — https://a.example/report
[2] Báo cáo B — https://b.example/x
"""


def test_split_sources_and_citations():
    body, urls = split_sources(ANSWER)
    assert "Nguồn tìm kiếm" not in body and urls == {1: "https://a.example/report", 2: "https://b.example/x"}
    assert resolve_citations("giá 70 - 95 triệu/m² [1][2][9]", urls) == [
        "https://a.example/report", "https://b.example/x"]
    assert declares_no_result("kết quả: chưa tìm thấy\n...") == "no_result_declared"
    assert declares_no_result(ANSWER) is None


def test_claim_gets_source_url_and_month(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    f.write_text(json.dumps({
        "answer_id": "z1", "crawl_run_id": "run-1", "target_month": "2026-10",
        "crawled_at": "2026-10-28T10:00:00Z", "chatbot": "Gemma",
        "query_text": "Tra cứu giá rao tháng 2026-10 tại Phường Bồ Đề, Hà Nội", "answer_text": ANSWER,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    ingest_file(store, f)
    llm = FakeLLM(claims_json(
        make_claim(ward="Bồ Đề", district=None, value_low=70_000_000, value_high=95_000_000,
                   quote="giá chào bán 70 - 95 triệu/m² cho nhà riêng [1]", qualifier="giá chào bán")))
    process_pending(store, make_extractor(llm))
    claim = next(store.iter_claims())
    assert claim["source_urls"] == ["https://a.example/report"]
    assert (claim["target_month"], claim["crawl_run_id"]) == ("2026-10", "run-1")
    assert "Nguồn tìm kiếm" not in llm.calls[0][1]  # sources block not sent to the LLM


def test_quality_report_counts_and_alerts(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    lines = []
    for i in range(30):
        lines.append(json.dumps({"answer_id": f"a{i}", "target_month": "2026-10",
                                 "crawled_at": "2026-10-28T10:00:00Z", "chatbot": "gemma",
                                 "query_text": "q", "answer_text": "Giá phổ biến 200 - 430 triệu/m² tại Bồ Đề"},
                                ensure_ascii=False))
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ingest_file(store, f)
    bad = make_claim(quote="câu không có trong văn bản")
    good = make_claim(quote="200 - 430 triệu/m²")
    process_pending(store, make_extractor(FakeLLM(claims_json(good, bad))))
    q = stats.quality(store, current_version="x", thresholds=stats.Thresholds(min_sample=10))
    assert q["claims"] == 30 and q["rejected"] == 30 and q["rates"]["rejected"] == 0.5
    assert q["rejected_reasons"] == {"quote_not_in_answer": 30}
    assert q["stale_answers"] == 30
    assert {a["code"] for a in q["alerts"]} >= {"high_rejected_rate", "stale_extractor"}
    assert q["by_month"][0]["month"] == "2026-10" and q["by_month"][0]["claims"] == 30
    assert stats.list_answers(store, status="ok")["total"] == 30
    assert stats.answer_detail(store, "a0")["rejected_items"][0]["reason"] == "quote_not_in_answer"
