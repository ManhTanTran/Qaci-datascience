"""Interactive EPI-style employee reasoning demo.

The module intentionally uses a transparent synthetic baseline until an
approved EPI training table and target are supplied. It demonstrates the
integration contract between a model, a live knowledge base and an agent
harness without pretending the baseline is a production employee model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TargetName = Literal["promotion_readiness", "kpi_delivery", "training_priority"]


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=1, max_length=120)
    years_experience: float = Field(ge=0, le=60)
    projects_delivered: int = Field(ge=0, le=100)
    kpi_attainment: float = Field(ge=0, le=1)
    skill_match: float = Field(ge=0, le=1)
    certifications: int = Field(ge=0, le=30)


class AgentDemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: EmployeeProfile | None = None
    scenario_id: str | None = None
    target: TargetName = "promotion_readiness"
    use_llm: bool = True


class RuleFinding(BaseModel):
    rule_id: str
    message: str
    action: str


class AgentConclusion(BaseModel):
    # OpenRouter's strict JSON-schema mode (including Azure/OpenAI routes)
    # requires object schemas to reject undeclared keys and to list every
    # output field as required.  Keeping this contract on the Pydantic model
    # prevents provider-specific 400s when the generated schema is forwarded.
    model_config = ConfigDict(extra="forbid")
    summary: str
    evidence: list[str]
    uncertainties: list[str]
    recommended_actions: list[str]
    human_review_required: Literal[True]


class AgentDemoResponse(BaseModel):
    target: TargetName
    model_name: str
    model_score: float
    model_interpretation: str
    rule_findings: list[RuleFinding]
    conclusion: AgentConclusion
    trace: list[str]
    knowledge_base_version: str
    llm_provider: str
    llm_used: bool


DEFAULT_KB_PATH = Path("configs/agent_demo_knowledge.json")

SYNTHETIC_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "steady_analyst",
        "label": "Analyst ổn định",
        "summary": "Kết quả tốt, kỹ năng phù hợp và có delivery đều.",
        "profile": {
            "role": "Data Analyst",
            "years_experience": 3,
            "projects_delivered": 4,
            "kpi_attainment": 0.86,
            "skill_match": 0.78,
            "certifications": 1,
        },
    },
    {
        "id": "high_delivery_gap",
        "label": "Delivery tốt, cần bù skill",
        "summary": "Delivery và KPI cao nhưng mức khớp kỹ năng còn thấp.",
        "profile": {
            "role": "Product Analyst",
            "years_experience": 5,
            "projects_delivered": 6,
            "kpi_attainment": 0.94,
            "skill_match": 0.52,
            "certifications": 1,
        },
    },
    {
        "id": "training_priority",
        "label": "Ưu tiên đào tạo",
        "summary": "Kinh nghiệm và KPI thấp hơn, phù hợp để minh họa action đào tạo.",
        "profile": {
            "role": "Junior Data Specialist",
            "years_experience": 1,
            "projects_delivered": 1,
            "kpi_attainment": 0.62,
            "skill_match": 0.48,
            "certifications": 0,
        },
    },
)


def synthetic_demo_scenarios() -> list[dict[str, Any]]:
    """Return the versioned, non-PII profiles used by the Agent Demo UI."""

    return [
        {
            "id": str(item["id"]),
            "label": str(item["label"]),
            "summary": str(item["summary"]),
            "profile": dict(item["profile"]),
        }
        for item in SYNTHETIC_SCENARIOS
    ]


def synthetic_demo_profile(scenario_id: str) -> EmployeeProfile:
    """Resolve one synthetic scenario without accepting user-entered employee data."""

    for scenario in SYNTHETIC_SCENARIOS:
        if scenario["id"] == scenario_id:
            return EmployeeProfile.model_validate(scenario["profile"])
    raise ValueError(f"Synthetic scenario không tồn tại: {scenario_id}")


def resolve_demo_profile(request: AgentDemoRequest) -> EmployeeProfile:
    """Resolve a backward-compatible request into a profile for the harness."""

    if request.profile is not None and request.scenario_id is not None:
        raise ValueError("Chỉ gửi profile hoặc scenario_id, không gửi cả hai.")
    if request.scenario_id is not None:
        return synthetic_demo_profile(request.scenario_id)
    if request.profile is not None:
        return request.profile
    return synthetic_demo_profile("steady_analyst")


def load_knowledge_base(path: str | Path = DEFAULT_KB_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise TypeError("Knowledge base phải là object có danh sách rules.")
    return payload


def _match_rule(profile: EmployeeProfile, rule: dict[str, Any]) -> bool:
    actual = getattr(profile, str(rule["field"]), None)
    expected = rule["value"]
    operator = rule["operator"]
    if actual is None:
        return False
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    raise ValueError(f"Knowledge base operator không hỗ trợ: {operator}")


def evaluate_rules(profile: EmployeeProfile, knowledge_base: dict[str, Any]) -> list[RuleFinding]:
    return [
        RuleFinding(rule_id=str(rule["id"]), message=str(rule["message"]), action=str(rule["action"]))
        for rule in knowledge_base["rules"]
        if _match_rule(profile, rule)
    ]


def _model_score(profile: EmployeeProfile, target: TargetName) -> float:
    delivery = min(profile.projects_delivered / 5, 1.0)
    experience = min(profile.years_experience / 10, 1.0)
    if target == "training_priority":
        raw = 0.55 * (1 - profile.skill_match) + 0.25 * (1 - profile.kpi_attainment) + 0.20 * (1 - experience)
    elif target == "kpi_delivery":
        raw = 0.40 * profile.kpi_attainment + 0.35 * delivery + 0.15 * profile.skill_match + 0.10 * experience
    else:
        raw = 0.30 * profile.kpi_attainment + 0.25 * delivery + 0.25 * profile.skill_match + 0.20 * experience
    return round(max(0.0, min(raw, 1.0)), 4)


def _fallback_conclusion(
    profile: EmployeeProfile,
    target: TargetName,
    score: float,
    findings: list[RuleFinding],
) -> AgentConclusion:
    target_label = {
        "promotion_readiness": "mức sẵn sàng cho vai trò mục tiêu",
        "kpi_delivery": "khả năng đạt KPI",
        "training_priority": "mức ưu tiên đào tạo",
    }[target]
    evidence = [
        f"Model baseline ước lượng {target_label} ở mức {score:.1%}.",
        f"Hồ sơ demo thuộc vai trò {profile.role}, có {profile.projects_delivered} dự án hoàn thành.",
    ]
    evidence.extend(item.message for item in findings)
    uncertainties = [
        "Đây là baseline tổng hợp minh họa, chưa được train trên dữ liệu EPI thật.",
        "Chưa kiểm tra chất lượng và phạm vi ảnh hưởng thực tế của từng dự án.",
    ]
    actions = [item.action for item in findings]
    if not actions:
        actions.append("Bổ sung bằng chứng định lượng và để quản lý chuyên môn review.")
    return AgentConclusion(
        summary=f"Hồ sơ có tín hiệu cho {target_label}, cần đối chiếu thêm bằng chứng trước khi quyết định.",
        evidence=evidence,
        uncertainties=uncertainties,
        recommended_actions=actions,
        human_review_required=True,
    )


def _llm_provider() -> str | None:
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _generate_llm_conclusion(
    payload: dict[str, Any],
    *,
    client: Any,
    provider: str,
) -> AgentConclusion:
    schema = AgentConclusion.model_json_schema()
    system = (
        "Bạn là agent diễn giải hồ sơ nhân viên bằng tiếng Việt. Chỉ dùng evidence "
        "được cung cấp, phân biệt score baseline với rule, không suy đoán PII, không "
        "tự quyết định tuyển dụng/thăng chức và luôn yêu cầu human review."
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    if provider == "openrouter":
        response = client.chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": serialized}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "epi_agent_conclusion", "strict": True, "schema": schema},
            },
            extra_body={"provider": {"require_parameters": True}},
        )
        content = response.choices[0].message.content
    else:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            store=False,
            instructions=system,
            input=serialized,
            text={"format": {"type": "json_schema", "name": "epi_agent_conclusion", "strict": True, "schema": schema}},
        )
        content = response.output_text
    return AgentConclusion.model_validate_json(content)


def run_agent_demo(
    request: AgentDemoRequest,
    *,
    knowledge_base: dict[str, Any],
    client: Any | None = None,
    provider: str | None = None,
) -> AgentDemoResponse:
    """Run model → rules → harness → optional LLM and return the full trace."""

    profile = resolve_demo_profile(request)
    score = _model_score(profile, request.target)
    findings = evaluate_rules(profile, knowledge_base)
    resolved_provider = provider or _llm_provider()
    trace = [
        (
            "1. Extract: dữ liệu synthetic đã được validate theo allowlist employee fields "
            f"(scenario={request.scenario_id or 'profile_compatibility'})."
        ),
        f"2. Model: employee-readiness-v0 tính score cho target={request.target}.",
        f"3. Knowledge base: evaluated {len(knowledge_base['rules'])} rules, matched {len(findings)}.",
        "4. Harness: hợp nhất model score, rule findings và uncertainty.",
    ]
    safe_payload = {
        "target": request.target,
        "model": {"name": "employee-readiness-v0", "score": score, "research_candidate": True},
        "rule_findings": [item.model_dump() for item in findings],
        "knowledge_base_version": str(knowledge_base.get("version", "unknown")),
    }
    llm_used = False
    if request.use_llm and client is None and resolved_provider is not None:
        try:
            from openai import OpenAI

            client = (
                OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"],
                    default_headers={"X-OpenRouter-Title": "EPI Agent Demo"},
                )
                if resolved_provider == "openrouter"
                else OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError('Cần cài dependency: pip install -e ".[web]"') from exc
    if request.use_llm and client is not None and resolved_provider is not None:
        conclusion = _generate_llm_conclusion(safe_payload, client=client, provider=resolved_provider)
        llm_used = True
        trace.append(f"5. LLM: generated structured conclusion via {resolved_provider}.")
    else:
        conclusion = _fallback_conclusion(profile, request.target, score, findings)
        trace.append("5. LLM: chưa cấu hình API key, dùng fallback deterministic cho demo.")
    trace.append("6. Output: trả kết luận, bằng chứng, uncertainty và recommended actions.")
    return AgentDemoResponse(
        target=request.target,
        model_name="employee-readiness-v0",
        model_score=score,
        model_interpretation="Baseline minh họa; chưa phải model EPI production.",
        rule_findings=findings,
        conclusion=conclusion,
        trace=trace,
        knowledge_base_version=str(knowledge_base.get("version", "unknown")),
        llm_provider=resolved_provider or "fallback",
        llm_used=llm_used,
    )
