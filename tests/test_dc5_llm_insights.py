import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from credit_scoring.dc5.inference import IndividualModelResult, LocalReason
from credit_scoring.dc5.llm_insights import (
    STANDARD_DISCLAIMER,
    InsightRequest,
    generate_insight,
    llm_status,
)
from credit_scoring.dc5.model_evidence import FeatureEvidence, ModelEvidence

VALID_REQUEST = {
    "profile": {
        "age": 35,
        "income_million_vnd": 15,
        "occupation": "Nhân viên văn phòng",
        "employment_years": 3,
        "household_type": "Chung cư",
        "dependents": 1,
        "service_count": 2,
    },
    "demo_index": 62.5,
    "components": {"income": 30.0, "employment_tenure": 30.0},
}


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "summary": "Hồ sơ demo có một số tín hiệu tích cực.",
                    "supporting_factors": ["Thâm niên làm việc đã được cung cấp."],
                    "uncertainties": ["Chưa có CIC model được phê duyệt."],
                    "recommended_next_steps": ["Chuyên viên kiểm tra dữ liệu đầu vào."],
                    "human_review_required": True,
                    "disclaimer": "Đây không phải CIC score hoặc quyết định tín dụng.",
                },
                ensure_ascii=False,
            )
        )


class FakeChatCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        content = json.dumps(
            {
                "summary": "Hồ sơ demo có một số tín hiệu tích cực.",
                "supporting_factors": ["Thâm niên làm việc đã được cung cấp."],
                "uncertainties": ["Chưa có CIC model được phê duyệt."],
                "recommended_next_steps": ["Chuyên viên kiểm tra dữ liệu đầu vào."],
                "human_review_required": True,
                "disclaimer": "Đây không phải CIC score hoặc quyết định tín dụng.",
            },
            ensure_ascii=False,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeResponsesWithEquivalentDisclaimer(FakeResponses):
    def create(self, **kwargs):
        response = super().create(**kwargs)
        payload = json.loads(response.output_text)
        payload["disclaimer"] = (
            "Kết quả chỉ mang tính tham khảo, không được dùng để phê duyệt "
            "hoặc từ chối khoản vay; chuyên viên phải kiểm tra lại."
        )
        response.output_text = json.dumps(payload, ensure_ascii=False)
        return response


def test_llm_request_rejects_pii_and_unknown_fields() -> None:
    payload = {**VALID_REQUEST, "profile": {**VALID_REQUEST["profile"], "full_name": "A"}}
    with pytest.raises(ValidationError, match="full_name"):
        InsightRequest.model_validate(payload)


def test_generate_insight_uses_no_store_and_structured_output() -> None:
    responses = FakeResponses()
    result = generate_insight(
        InsightRequest.model_validate(VALID_REQUEST),
        client=SimpleNamespace(responses=responses),
    )
    assert result.human_review_required is True
    assert responses.kwargs["store"] is False
    assert responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert "full_name" not in responses.kwargs["input"]


def test_generate_insight_supports_openrouter_structured_output() -> None:
    completions = FakeChatCompletions()
    result = generate_insight(
        InsightRequest.model_validate(VALID_REQUEST),
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        provider="openrouter",
    )
    assert result.human_review_required is True
    assert completions.kwargs["response_format"]["type"] == "json_schema"
    assert completions.kwargs["response_format"]["json_schema"]["strict"] is True
    assert completions.kwargs["extra_body"]["provider"]["require_parameters"] is True
    assert "full_name" not in completions.kwargs["messages"][1]["content"]


def test_generate_insight_accepts_equivalent_safe_disclaimer() -> None:
    result = generate_insight(
        InsightRequest.model_validate(VALID_REQUEST),
        client=SimpleNamespace(responses=FakeResponsesWithEquivalentDisclaimer()),
    )
    assert result.human_review_required is True
    assert result.disclaimer == STANDARD_DISCLAIMER


def test_generate_insight_includes_aggregate_model_evidence() -> None:
    responses = FakeResponses()
    evidence = ModelEvidence(
        run_id="run-123",
        backend="catboost",
        model_name="M4",
        setting="No City",
        model_description="M1 cộng hành vi Telco.",
        target_definition="target_high_telco_monetary",
        roc_auc=0.69,
        pr_auc=0.33,
        positive_rate=0.18,
        top_features=(FeatureEvidence(feature="telco_usage", importance=42.0),),
        inference_available=False,
        limitation="Aggregate validation only; no individual inference.",
    )
    result = generate_insight(
        InsightRequest.model_validate(VALID_REQUEST),
        client=SimpleNamespace(responses=responses),
        model_evidence=evidence,
    )
    sent = json.loads(responses.kwargs["input"])
    assert sent["research_model_evidence"]["model_name"] == "M4"
    assert sent["research_model_evidence"]["inference_available"] is False
    assert result.model_context_used is True
    assert result.model_reference == "catboost M4 · No City · run run-123"
    assert result.model_context_note == evidence.limitation


def test_generate_insight_sends_prediction_and_reasons_without_raw_model_features() -> None:
    responses = FakeResponses()
    request_payload = {
        **VALID_REQUEST,
        "model_features": {"internal_telco_feature": 4},
    }
    individual = IndividualModelResult(
        target_probability=0.72,
        target_definition="target_high_telco_monetary",
        model_name="M4-safe",
        setting="No City",
        run_id="run-123",
        local_reasons=(
            LocalReason(feature="telco_usage", contribution=0.4, direction="tăng"),
        ),
    )
    result = generate_insight(
        InsightRequest.model_validate(request_payload),
        client=SimpleNamespace(responses=responses),
        individual_result=individual,
    )
    sent = json.loads(responses.kwargs["input"])
    assert "model_features" not in sent["profile_result"]
    assert "internal_telco_feature" not in responses.kwargs["input"]
    assert sent["individual_model_result"]["target_probability"] == 0.72
    assert result.individual_model_used is True
    assert result.target_probability == 0.72


def test_status_never_exposes_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    status = llm_status()
    assert status["configured"] is True
    assert status["provider"] == "openai"
    assert "secret-value" not in str(status)


def test_status_auto_detects_openrouter_without_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-secret")
    status = llm_status()
    assert status["configured"] is True
    assert status["provider"] == "openrouter"
    assert status["model"] == "openai/gpt-4o-mini"
    assert "openrouter-secret" not in str(status)
