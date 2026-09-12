from __future__ import annotations

import json
from types import SimpleNamespace

from credit_scoring.dc5.agent_demo import (
    AgentConclusion,
    AgentDemoRequest,
    EmployeeProfile,
    evaluate_rules,
    run_agent_demo,
    synthetic_demo_profile,
    synthetic_demo_scenarios,
)

KB = {
    "version": "kb-test-v1",
    "rules": [
        {
            "id": "R-KPI",
            "field": "kpi_attainment",
            "operator": "gte",
            "value": 0.9,
            "message": "KPI cao",
            "action": "Review delivery",
        },
        {
            "id": "R-SKILL",
            "field": "skill_match",
            "operator": "lt",
            "value": 0.6,
            "message": "Skill gap",
            "action": "Mentoring",
        },
    ],
}


PROFILE = EmployeeProfile(
    role="Analyst",
    years_experience=3,
    projects_delivered=4,
    kpi_attainment=0.95,
    skill_match=0.5,
    certifications=1,
)


def test_agent_conclusion_schema_is_strict_and_all_fields_required() -> None:
    schema = AgentConclusion.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_rules_and_fallback_surface_full_agent_state() -> None:
    result = run_agent_demo(
        AgentDemoRequest(profile=PROFILE, target="promotion_readiness", use_llm=False),
        knowledge_base=KB,
    )

    assert [finding.rule_id for finding in evaluate_rules(PROFILE, KB)] == ["R-KPI", "R-SKILL"]
    assert result.llm_used is False
    assert result.llm_provider == "fallback"
    assert result.knowledge_base_version == "kb-test-v1"
    assert 0 <= result.model_score <= 1
    assert len(result.trace) == 6
    assert "KPI cao" in result.conclusion.evidence


def test_synthetic_scenario_runs_without_employee_input() -> None:
    scenarios = synthetic_demo_scenarios()
    assert len(scenarios) == 3
    assert {item["id"] for item in scenarios} == {
        "steady_analyst",
        "high_delivery_gap",
        "training_priority",
    }

    profile = synthetic_demo_profile("steady_analyst")
    result = run_agent_demo(
        AgentDemoRequest(scenario_id="steady_analyst", target="promotion_readiness", use_llm=False),
        knowledge_base=KB,
    )

    assert profile.role == "Data Analyst"
    assert result.llm_used is False
    assert result.trace[0].startswith("1. Extract: dữ liệu synthetic")


def test_unknown_synthetic_scenario_is_rejected() -> None:
    try:
        synthetic_demo_profile("missing")
    except ValueError as exc:
        assert "không tồn tại" in str(exc)
    else:
        raise AssertionError("Unknown synthetic scenario should fail")


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        content = {
            "summary": "Cần review thêm bằng chứng.",
            "evidence": ["KPI cao"],
            "uncertainties": ["Chưa có dữ liệu EPI thật."],
            "recommended_actions": ["Review delivery"],
            "human_review_required": True,
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))]
        )


def test_openrouter_agent_uses_structured_output() -> None:
    completions = FakeCompletions()
    result = run_agent_demo(
        AgentDemoRequest(profile=PROFILE, target="kpi_delivery", use_llm=True),
        knowledge_base=KB,
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        provider="openrouter",
    )

    assert result.llm_used is True
    assert result.llm_provider == "openrouter"
    assert completions.kwargs["response_format"]["type"] == "json_schema"
    sent_schema = completions.kwargs["response_format"]["json_schema"]["schema"]
    assert sent_schema["additionalProperties"] is False
    assert set(sent_schema["required"]) == set(sent_schema["properties"])
    sent = json.loads(completions.kwargs["messages"][1]["content"])
    assert sent["knowledge_base_version"] == "kb-test-v1"
    assert sent["model"]["score"] == result.model_score
