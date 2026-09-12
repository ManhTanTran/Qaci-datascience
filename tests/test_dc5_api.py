import json

from fastapi.testclient import TestClient

from credit_scoring.dc5.api import app

client = TestClient(app)

VALID_LEAD = {
    "schema_version": "dc5-lead-v1",
    "age": 35,
    "income_million_vnd": 15,
    "occupation": "Nhân viên văn phòng",
    "employment_years": 3,
    "household_type": "Chung cư",
    "dependents": 1,
    "service_count": 2,
    "cic_score": None,
}


def test_health_and_template() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/leads/template").json()["schema_version"] == "dc5-lead-v1"


def test_local_frontend_preflight_is_allowed() -> None:
    response = client.options(
        "/api/leads/validate",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_local_frontend_preflight_allows_another_dev_port() -> None:
    response = client.options(
        "/api/leads/validate",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


def test_agent_demo_exposes_synthetic_scenarios() -> None:
    response = client.get("/api/agent-demo/scenarios")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "steady_analyst"

    run = client.post(
        "/api/agent-demo/run",
        json={"scenario_id": "steady_analyst", "use_llm": False},
    )
    assert run.status_code == 200
    assert run.json()["trace"][0].startswith("1. Extract: dữ liệu synthetic")


def test_insight_status_does_not_require_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = client.get("/api/insights/status")
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_validate_and_simulate_lead() -> None:
    validated = client.post("/api/leads/validate", json=VALID_LEAD)
    assert validated.status_code == 200
    result = client.post("/api/leads/simulate", json=VALID_LEAD)
    assert result.status_code == 200
    assert 0 <= result.json()["demo_index"] <= 100
    assert result.json()["cic_used_in_model"] is False


def test_credit_reasoning_flow_runs_three_synthetic_cases() -> None:
    profile = {
        key: value
        for key, value in VALID_LEAD.items()
        if key not in {"cic_score", "schema_version"}
    }
    response = client.post(
        "/api/credit-flow/run",
        json={"profile": profile, "use_llm": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["flow_version"] == "credit-reasoning-flow-v1"
    assert body["extraction"]["source"] == "customer_intake"
    assert len(body["synthetic_tests"]) == 3
    assert body["agent_harness"]["status"] == "completed"
    assert body["final_reasoning"]["status"] == "deterministic_fallback"
    assert body["final_reasoning"]["evidence"]
    assert body["llm_rule_generation"]["status"] in {
        "ready_to_run",
        "blocked_no_ml_evidence",
    }


def test_reasoning_workspace_and_assessment_endpoints() -> None:
    workspace = client.get("/api/reasoning/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["counts"]["scenarios"] == 3

    assessment = client.post(
        "/api/reasoning/assess",
        json={"scenario_id": "conflicting_signals", "use_llm": False},
    )
    assert assessment.status_code == 200
    assert assessment.json()["detected_domains"]
    assert assessment.json()["llm_called"] is False


def test_invalid_lead_returns_safe_validation_error() -> None:
    response = client.post("/api/leads/validate", json={"age": 12})
    assert response.status_code == 422
    assert "Thiếu trường bắt buộc" in response.json()["detail"]


def test_model_lead_template_uses_active_manifest(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "artifacts"
    run_dir = output_dir / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (output_dir / "latest.json").write_text(
        json.dumps({"run_dir": str(run_dir)}), encoding="utf-8"
    )
    (run_dir / "research_inference_manifest.json").write_text(
        json.dumps(
            {
                "feature_schema": {
                    "numeric_feature": {"type": "number"},
                    "category_feature": {"type": "string"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DC5_ARTIFACT_DIR", str(output_dir))

    response = client.get("/api/leads/model-template")

    assert response.status_code == 200
    assert response.json()["model_features"] == {
        "numeric_feature": 0,
        "category_feature": "MISSING",
    }
