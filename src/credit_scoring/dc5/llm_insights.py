"""Guarded LLM interpretation for anonymized phase-one simulation results."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from credit_scoring.dc5.inference import IndividualModelResult
from credit_scoring.dc5.model_evidence import ModelEvidence
from credit_scoring.dc5.simulation import OCCUPATION_STABILITY


class SafeProfile(BaseModel):
    """Explicit allowlist of non-identifier profile fields sent to the LLM."""

    model_config = ConfigDict(extra="forbid")
    age: int = Field(ge=18, le=100)
    income_million_vnd: float = Field(ge=0, le=10_000)
    occupation: Literal[
        "Nhân viên văn phòng",
        "Kinh doanh tự do",
        "Công chức/viên chức",
        "Lao động kỹ thuật",
        "Sinh viên",
        "Khác",
    ]
    employment_years: float = Field(ge=0, le=82)
    household_type: Literal["Nhà thường", "Chung cư", "Nhà trọ", "Khác"]
    dependents: int = Field(ge=0, le=20)
    service_count: int = Field(ge=0, le=10)


class InsightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: SafeProfile
    demo_index: float = Field(ge=0, le=100)
    components: dict[str, float]
    model_features: dict[str, Any] | None = None


class InsightConclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    supporting_factors: list[str]
    uncertainties: list[str]
    recommended_next_steps: list[str]
    human_review_required: Literal[True]
    disclaimer: str
    model_context_used: bool = False
    model_reference: str | None = None
    model_context_note: str | None = None
    individual_model_used: bool = False
    target_probability: float | None = None


STANDARD_DISCLAIMER = (
    "Đây là diễn giải hỗ trợ từ demo profile index, không phải CIC/credit score "
    "hoặc quyết định tín dụng. Chuyên viên phải kiểm tra trước khi sử dụng."
)


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "supporting_factors": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
        "human_review_required": {"type": "boolean", "const": True},
        "disclaimer": {"type": "string"},
    },
    "required": [
        "summary",
        "supporting_factors",
        "uncertainties",
        "recommended_next_steps",
        "human_review_required",
        "disclaimer",
    ],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = (
    "Bạn là trợ lý diễn giải kết quả nghiên cứu DC5 bằng tiếng Việt. "
    "Kết hợp thông tin hồ sơ, demo index và research_model_evidence nếu có. "
    "Phân biệt rõ quan sát của hồ sơ với metric/importance aggregate của model. "
    "Nếu inference_available=false, tuyệt đối không gọi metric aggregate là xác suất "
    "hay dự đoán CatBoost của cá nhân. Chỉ mô tả dữ liệu được cung cấp; "
    "Nếu individual_model_result có dữ liệu, hãy diễn giải target_probability và "
    "local_reasons theo đúng target_definition; direction chỉ là chiều tác động SHAP, "
    "không phải quan hệ nhân quả. "
    "không suy đoán PII, không kết luận CIC, "
    "không phê duyệt/từ chối khoản vay, không gọi đây là credit score. "
    "Khi có model evidence, nêu tên model/setting, chất lượng validation và các feature "
    "quan trọng có liên quan; không khẳng định quan hệ nhân quả. "
    "Luôn yêu cầu chuyên viên kiểm tra và nêu rõ đây là demo profile index."
)


def _configured_provider() -> str | None:
    preferred = os.getenv("LLM_PROVIDER", "").lower()
    if preferred == "openrouter" and os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if preferred == "openai" and os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def llm_status() -> dict[str, Any]:
    """Expose readiness without revealing any secret value."""

    provider = _configured_provider()
    model = (
        os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        if provider == "openrouter"
        else os.getenv("OPENAI_MODEL", "gpt-5-mini")
    )
    return {
        "configured": provider is not None,
        "provider": provider,
        "model": model,
        "data_policy": "anonymized_allowlist_only",
    }


def generate_insight(
    request: InsightRequest,
    *,
    client: Any | None = None,
    provider: str | None = None,
    model_evidence: ModelEvidence | None = None,
    individual_result: IndividualModelResult | None = None,
) -> InsightConclusion:
    """Generate and validate an interpretation through OpenAI or OpenRouter."""

    resolved_provider = provider or (_configured_provider() if client is None else "openai")
    if client is None:
        if resolved_provider is None:
            raise RuntimeError("OPENROUTER_API_KEY hoặc OPENAI_API_KEY chưa được cấu hình.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError('Cần cài dependency: pip install -e ".[web]"') from exc
        client = (
            OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"],
                default_headers={"X-OpenRouter-Title": "DC5 Customer Analysis"},
            )
            if resolved_provider == "openrouter"
            else OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        )

    safe_payload = {
        "profile_result": request.model_dump(exclude={"model_features"}),
        "research_model_evidence": (
            model_evidence.to_dict() if model_evidence is not None else None
        ),
        "individual_model_result": (
            individual_result.to_dict() if individual_result is not None else None
        ),
    }
    serialized = json.dumps(safe_payload, ensure_ascii=False)
    if resolved_provider == "openrouter":
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": serialized},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "dc5_insight_conclusion",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                },
            },
            extra_body={"provider": {"require_parameters": True}},
        )
        output_text = response.choices[0].message.content
    else:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            store=False,
            instructions=SYSTEM_INSTRUCTIONS,
            input=serialized,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "dc5_insight_conclusion",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
        )
        output_text = response.output_text
    try:
        conclusion = InsightConclusion.model_validate_json(output_text)
    except (AttributeError, ValueError) as exc:
        raise RuntimeError("LLM trả về kết quả không đúng schema an toàn.") from exc
    model_reference = None
    model_context_note = None
    if model_evidence is not None:
        model_reference = (
            f"{model_evidence.backend} {model_evidence.model_name} · "
            f"{model_evidence.setting} · run {model_evidence.run_id}"
        )
        model_context_note = model_evidence.limitation
    return conclusion.model_copy(
        update={
            "disclaimer": STANDARD_DISCLAIMER,
            "model_context_used": model_evidence is not None,
            "model_reference": model_reference,
            "model_context_note": model_context_note,
            "individual_model_used": individual_result is not None,
            "target_probability": (
                individual_result.target_probability
                if individual_result is not None
                else None
            ),
        }
    )


assert set(OCCUPATION_STABILITY) == set(SafeProfile.model_fields["occupation"].annotation.__args__)
