from claims_extractor.extract import parse_claims_payload
from support import FakeLLM, claims_json, make_claim

import pytest

from claims_extractor.extract import ExtractionError


def test_parse_accepts_fenced_json_prose_and_bare_list():
    assert parse_claims_payload('```json\n{"claims": [{"a": 1}]}\n```') == [{"a": 1}]
    assert parse_claims_payload('Đây là kết quả: {"claims": []} cảm ơn') == []
    assert parse_claims_payload('[{"a": 1}]') == [{"a": 1}]


@pytest.mark.parametrize("bad", ["", "not json", '{"claims": "x"}', '{"other": []}'])
def test_parse_rejects_bad_payloads(bad):
    with pytest.raises(ExtractionError):
        parse_claims_payload(bad)


def test_extract_ok_dedupes_and_rejects_hallucinated_quotes(answer, make_extractor):
    llm = FakeLLM(claims_json(
        make_claim(),
        make_claim(),  # duplicate
        make_claim(ward="Việt Hưng", quote="không hề có trong văn bản 123 triệu/m²"),
    ))
    output = make_extractor(llm).extract(answer)
    assert output.extract_status == "ok"
    assert len(output.claims) == 1
    assert [r["reason"] for r in output.rejected] == ["quote_not_in_answer"]
    assert output.extractor_model == "fake-llm" and len(output.prompt_hash) == 12
    assert "<answer>" in llm.calls[0][1] and answer.answer_text in llm.calls[0][1]


def test_extract_empty_when_no_claims(answer, make_extractor):
    output = make_extractor(FakeLLM('{"claims": []}')).extract(answer)
    assert output.extract_status == "empty" and output.claims == []


def test_malformed_json_is_repaired_once(answer, make_extractor):
    llm = FakeLLM("xin lỗi, không phải JSON", claims_json(make_claim()))
    output = make_extractor(llm).extract(answer)
    assert output.extract_status == "ok" and len(llm.calls) == 2
    assert "không hợp lệ" in llm.calls[1][1]


def test_failed_after_repair_budget(answer, make_extractor):
    llm = FakeLLM("garbage")
    output = make_extractor(llm).extract(answer)
    assert output.extract_status == "failed" and len(llm.calls) == 2
    assert "invalid LLM output" in output.error


def test_llm_exception_becomes_failed_status(answer, make_extractor):
    output = make_extractor(FakeLLM(TimeoutError("boom"))).extract(answer)
    assert output.extract_status == "failed" and "TimeoutError" in output.error
