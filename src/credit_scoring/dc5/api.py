"""FastAPI endpoints for the DC5 customer website."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from credit_scoring.dc5.agent_demo import (
    AgentDemoRequest,
    AgentDemoResponse,
    load_knowledge_base,
    run_agent_demo,
    synthetic_demo_scenarios,
)
from credit_scoring.dc5.config import ModelConfig, PipelineConfig, ValidationConfig
from credit_scoring.dc5.credit_flow import discover_candidate_rules, run_credit_reasoning_flow
from credit_scoring.dc5.data import model_catalog
from credit_scoring.dc5.inference import (
    BUNDLE_MANIFEST_NAME,
    build_latest_catboost_bundle,
    predict_catboost_bundle,
)
from credit_scoring.dc5.lead import LEAD_SCHEMA_VERSION, validate_lead
from credit_scoring.dc5.llm_insights import (
    InsightConclusion,
    InsightRequest,
    SafeProfile,
    generate_insight,
    llm_status,
)
from credit_scoring.dc5.model_evidence import load_latest_model_evidence
from credit_scoring.dc5.pipeline import run_pipeline, smoke_check
from credit_scoring.dc5.simulation import simulate_profile
from credit_scoring.reasoning.workspace import (
    assess_customer,
    challenge_assessment,
    load_reference_evaluations,
    load_workspace_catalog,
)

app = FastAPI(title="DC5 Customer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    # Local Vite may move to another port when 5173 is occupied. Keep this
    # regex limited to loopback hosts; production origins need an explicit
    # allowlist instead.
    allow_origin_regex=r"^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class AdminRunRequest(BaseModel):
    data_path: str = "data_extracted/model_df_extracted.parquet"
    output_dir: str = "artifacts/dc5_customer_analysis"
    mode: str = "quick"
    backend: str = "catboost"
    include_city: bool = True
    clustering_enabled: bool = True
    force: bool = False
    n_splits: int = Field(default=5, ge=2, le=10)


class CreditFlowRequest(BaseModel):
    model_config = {"extra": "forbid"}
    profile: SafeProfile
    use_llm: bool = False


class ReasoningAssessmentRequest(BaseModel):
    model_config = {"extra": "forbid"}
    scenario_id: str | None = None
    features: dict[str, Any] | None = None
    use_llm: bool = True
    prompt_type: Literal["minimal", "guided"] = "guided"
    model: Literal["configured", "gpt", "gemini"] = "configured"


class ReasoningChallengeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    scenario_id: str
    original_output: dict[str, Any]
    challenge: str = Field(min_length=1, max_length=2000)
    prompt_type: Literal["minimal", "guided"] = "guided"
    model: Literal["configured", "gpt", "gemini"] = "configured"


class ReasoningEvaluationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    scenario_id: str
    models: list[Literal["gpt", "gemini"]] = Field(
        default_factory=lambda: ["gpt", "gemini"]
    )
    prompt_types: list[Literal["minimal", "guided"]] = Field(
        default_factory=lambda: ["guided"]
    )


def _latest_run_dir(output_dir: str | Path) -> Path:
    root = Path(output_dir).resolve()
    pointer = root / "latest.json"
    if not pointer.is_file():
        raise FileNotFoundError("No previous DC5 run found.")
    import json

    run_dir = Path(json.loads(pointer.read_text(encoding="utf-8"))["run_dir"]).resolve()
    if root not in run_dir.parents:
        raise ValueError("Latest run must stay inside the configured artifact directory.")
    return run_dir


def _records(frame: Any, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        frame = frame.head(limit)
    return frame.astype(object).where(frame.notna(), None).to_dict(orient="records")


def _admin_payload(run: Any) -> dict[str, Any]:
    import json

    import pandas as pd

    def read_csv(name: str) -> list[dict[str, Any]]:
        path = run.run_dir / name
        return _records(pd.read_csv(path)) if path.is_file() else []

    metadata_path = run.run_dir / "run_metadata.json"
    return {
        "cached": run.cached,
        "run_dir": str(run.run_dir),
        "report_name": run.report_path.name,
        "metrics": _records(run.metrics),
        "importance": read_csv("feature_importance.csv"),
        "fold_metrics": read_csv("fold_metrics.csv"),
        "domain_coverage": read_csv("domain_coverage.csv"),
        "missingness": read_csv("feature_missingness.csv"),
        "target_distribution": read_csv("target_distribution.csv"),
        "cluster_sizes": read_csv("cluster_sizes.csv"),
        "cluster_profile": read_csv("cluster_profile.csv"),
        "metadata": (
            json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata_path.is_file()
            else {}
        ),
        "model_catalog": model_catalog(include_city=True),
    }


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/agent-demo/knowledge")
def agent_demo_knowledge() -> dict[str, Any]:
    """Return the current on-disk KB so edits can be observed without restart."""

    try:
        return load_knowledge_base(os.getenv("EPI_KB_PATH", "configs/agent_demo_knowledge.json"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/agent-demo/scenarios")
def agent_demo_scenarios() -> list[dict[str, Any]]:
    """Return the non-PII synthetic profiles used by the Agent Demo UI."""

    return synthetic_demo_scenarios()


@app.post("/api/agent-demo/run", response_model=AgentDemoResponse)
def agent_demo_run(request: AgentDemoRequest) -> AgentDemoResponse:
    """Run the employee model/rules/harness demo."""

    try:
        knowledge_base = load_knowledge_base(
            os.getenv("EPI_KB_PATH", "configs/agent_demo_knowledge.json")
        )
        return run_agent_demo(request, knowledge_base=knowledge_base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/credit-flow/run")
def credit_flow_run(request: CreditFlowRequest) -> dict[str, Any]:
    """Run intake -> evidence -> KB -> synthetic harness orchestration."""

    try:
        return run_credit_reasoning_flow(
            request.profile,
            use_llm=request.use_llm,
            artifact_dir=os.getenv("DC5_ARTIFACT_DIR", "artifacts/dc5_customer_analysis"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/reasoning/workspace")
def reasoning_workspace() -> dict[str, Any]:
    """Return the feature registry, rule KB and synthetic scenario catalog."""

    try:
        payload = load_workspace_catalog()
        payload["llm"] = llm_status()
        return payload
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/reasoning/assess")
def reasoning_assess(request: ReasoningAssessmentRequest) -> dict[str, Any]:
    """Run the online customer reasoning harness for one scenario or feature object."""

    try:
        return assess_customer(
            scenario_id=request.scenario_id,
            features=request.features,
            use_llm=request.use_llm,
            prompt_type=request.prompt_type,
            model=request.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/reasoning/rule-discovery")
def reasoning_rule_discovery(use_llm: bool = False) -> dict[str, Any]:
    """Expose aggregate model evidence and optional candidate-rule drafting."""

    try:
        return discover_candidate_rules(
            use_llm=use_llm,
            artifact_dir=os.getenv("DC5_ARTIFACT_DIR", "artifacts/dc5_customer_analysis"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/reasoning/evaluation/reference")
def reasoning_reference_evaluation() -> dict[str, Any]:
    """Read and audit the model responses preserved in simulate.zip."""

    archive = Path(os.getenv("SIMULATE_ZIP_PATH", r"D:\Downloads\simulate.zip"))
    if not archive.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy simulate.zip.")
    try:
        return load_reference_evaluations(archive)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/reasoning/evaluate")
def reasoning_evaluate(request: ReasoningEvaluationRequest) -> dict[str, Any]:
    """Run explicit GPT/Gemini and prompt-variant evaluation calls."""

    runs: list[dict[str, Any]] = []
    for model in request.models:
        for prompt_type in request.prompt_types:
            try:
                result = assess_customer(
                    scenario_id=request.scenario_id,
                    use_llm=True,
                    prompt_type=prompt_type,
                    model=model,
                )
                output = result["output"] or {}
                runs.append(
                    {
                        "model_choice": model,
                        "prompt_type": prompt_type,
                        "status": "completed",
                        "provider": result["provider"],
                        "model": result["model"],
                        "classification": output.get("classification"),
                        "confidence": output.get("confidence"),
                        "rule_adherence": True,
                        "unsupported_information_count": len(
                            output.get("unsupported_information", [])
                        ),
                        "conflict_count": len(output.get("conflicts", [])),
                        "output": output,
                    }
                )
            except (ImportError, OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
                runs.append(
                    {
                        "model_choice": model,
                        "prompt_type": prompt_type,
                        "status": "error",
                        "error": str(exc),
                    }
                )
    return {"scenario_id": request.scenario_id, "runs": runs}


@app.post("/api/reasoning/challenge")
def reasoning_challenge(request: ReasoningChallengeRequest) -> dict[str, Any]:
    """Counter-argue one structured output and report classification stability."""

    try:
        return challenge_assessment(
            scenario_id=request.scenario_id,
            original_output=request.original_output,
            challenge=request.challenge,
            model=request.model,
            prompt_type=request.prompt_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/insights/status")
def insight_status() -> dict[str, Any]:
    return llm_status()


@app.post("/api/insights/generate", response_model=InsightConclusion)
def insight_generate(request: InsightRequest) -> InsightConclusion:
    try:
        artifact_dir = os.getenv("DC5_ARTIFACT_DIR", "artifacts/dc5_customer_analysis")
        evidence = load_latest_model_evidence(artifact_dir)
        individual_result = None
        if request.model_features is not None:
            individual_result = predict_catboost_bundle(
                _latest_run_dir(artifact_dir), request.model_features
            )
        return generate_insight(
            request,
            model_evidence=evidence,
            individual_result=individual_result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ImportError, OSError, RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/models/inference-schema")
def inference_schema() -> dict[str, Any]:
    try:
        run_dir = _latest_run_dir(os.getenv("DC5_ARTIFACT_DIR", "artifacts/dc5_customer_analysis"))
        import json

        return json.loads((run_dir / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="Chưa có CatBoost inference bundle.") from exc


@app.get("/api/leads/template")
def lead_template() -> dict[str, Any]:
    return {
        "schema_version": LEAD_SCHEMA_VERSION,
        "age": 35,
        "income_million_vnd": 15,
        "occupation": "Nhân viên văn phòng",
        "employment_years": 3,
        "household_type": "Chung cư",
        "dependents": 1,
        "service_count": 2,
        "cic_score": None,
    }


@app.get("/api/leads/model-template")
def model_lead_template() -> dict[str, Any]:
    """Return a synthetic, editable lead with the active bundle's exact schema."""

    manifest = inference_schema()
    feature_schema = manifest.get("feature_schema", {})
    payload = lead_template()
    payload["model_features"] = {
        feature: "MISSING" if spec.get("type") == "string" else 0
        for feature, spec in feature_schema.items()
    }
    return payload


@app.post("/api/leads/validate")
def validate_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_lead(payload)
    except (TypeError, ValueError) as exc:
        raise _error(exc) from exc


@app.post("/api/leads/simulate")
def simulate_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = validate_lead(payload)
        return simulate_profile(**profile)
    except (TypeError, ValueError) as exc:
        raise _error(exc) from exc


@app.post("/api/admin/runs")
def admin_run(request: AdminRunRequest) -> dict[str, Any]:
    """Run or load the research pipeline for the protected admin UI."""

    try:
        if request.mode != "report-only":
            smoke_check()
        config = PipelineConfig(
            data_path=Path(request.data_path),
            output_dir=Path(request.output_dir),
            mode=request.mode,  # type: ignore[arg-type]
            include_city_comparison=request.include_city,
            clustering_enabled=request.clustering_enabled,
            validation=ValidationConfig(n_splits=request.n_splits, random_state=42),
            model=ModelConfig(backend=request.backend),  # type: ignore[arg-type]
        )
        run = run_pipeline(config=config, force=request.force)
        if request.backend == "catboost" and not (run.run_dir / BUNDLE_MANIFEST_NAME).is_file():
            build_latest_catboost_bundle(request.data_path, run.run_dir)
        return _admin_payload(run)
    except (FileNotFoundError, ImportError, OSError, TypeError, ValueError) as exc:
        raise _error(exc) from exc


@app.get("/api/admin/report")
def admin_report(output_dir: str = "artifacts/dc5_customer_analysis") -> FileResponse:
    """Download the latest report artifact without exposing arbitrary paths."""

    try:
        output_path = Path(output_dir).resolve()
        pointer = output_path / "latest.json"
        if not pointer.is_file():
            raise FileNotFoundError("No previous DC5 run found.")
        import json

        report_path = Path(json.loads(pointer.read_text(encoding="utf-8"))["report_path"]).resolve()
        if output_path not in report_path.parents or not report_path.is_file():
            raise FileNotFoundError("Latest report artifact is unavailable.")
        return FileResponse(report_path, media_type="text/html", filename="dc5_report.html")
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise _error(exc) from exc
