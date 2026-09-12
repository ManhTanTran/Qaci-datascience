"""Application service for the local Credit Reasoning Agent workspace."""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from credit_scoring.reasoning.evaluation import evaluate_text_response
from credit_scoring.reasoning.feature_registry import (
    feature_registry_index,
    load_feature_definitions_yaml,
)
from credit_scoring.reasoning.harness import run_reasoning_harness
from credit_scoring.reasoning.llm_client import create_reasoner_from_environment
from credit_scoring.reasoning.prompt_builder import build_reasoning_prompt
from credit_scoring.reasoning.rules import load_rules_yaml
from credit_scoring.reasoning.schemas import validate_reasoning_output

ROOT = Path(__file__).parents[3]
DEFAULT_FEATURE_PATH = ROOT / "configs/reasoning/feature_definitions.yaml"
DEFAULT_RULE_PATH = ROOT / "configs/reasoning/rules.yaml"
DEFAULT_CASE_PATH = ROOT / "configs/reasoning/synthetic_cases.yaml"
DEFAULT_EVALUATION_MANIFEST = ROOT / "configs/reasoning/evaluation_manifest.json"

PromptType = Literal["minimal", "guided"]
ModelChoice = Literal["configured", "gpt", "gemini"]


def load_synthetic_cases(path: str | Path = DEFAULT_CASE_PATH) -> tuple[dict[str, Any], ...]:
    """Load the three project-authored, non-PII evaluation fixtures."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Loading synthetic cases requires PyYAML.") from exc
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("cases"), list):
        raise TypeError("Synthetic case config must contain a cases list.")
    cases = tuple(dict(item) for item in document["cases"])
    ids = [str(item.get("case_id", "")) for item in cases]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Synthetic case IDs must be non-empty and unique.")
    if any(not isinstance(item.get("features"), Mapping) for item in cases):
        raise TypeError("Every synthetic case must contain a feature object.")
    return cases


def load_workspace_catalog(
    *,
    feature_path: str | Path = DEFAULT_FEATURE_PATH,
    rule_path: str | Path = DEFAULT_RULE_PATH,
    case_path: str | Path = DEFAULT_CASE_PATH,
) -> dict[str, Any]:
    """Return registry, KB and scenario metadata for the web workspace."""

    features = load_feature_definitions_yaml(feature_path)
    feature_index = feature_registry_index(features)
    rules = load_rules_yaml(rule_path, known_features=feature_index)
    cases = load_synthetic_cases(case_path)
    statuses: dict[str, int] = {}
    for rule in rules:
        statuses[rule.status] = statuses.get(rule.status, 0) + 1
    domains = sorted({str(item["domain"]) for item in features})
    return {
        "counts": {
            "features": len(features),
            "rules": len(rules),
            "scenarios": len(cases),
            "rule_statuses": statuses,
        },
        "domains": domains,
        "features": list(features),
        "rules": [rule.to_dict() for rule in rules],
        "scenarios": [
            {
                "case_id": item["case_id"],
                "label": item["label"],
                "description": item["description"],
                "features": dict(item["features"]),
            }
            for item in cases
        ],
    }


def _reasoner_for(model: ModelChoice):
    if model == "configured":
        return create_reasoner_from_environment()
    model_name = (
        os.getenv("EVALUATION_GPT_MODEL", "openai/gpt-4o-mini")
        if model == "gpt"
        else os.getenv("EVALUATION_GEMINI_MODEL", "google/gemini-2.5-flash")
    )
    return create_reasoner_from_environment(provider="openrouter", model=model_name)


def _prompt_variant(prompt: str, prompt_type: PromptType) -> str:
    if prompt_type == "guided":
        return prompt
    payload = json.loads(prompt)
    payload["instructions"] = ["Return the requested JSON using only supplied evidence."]
    return build_reasoning_prompt(payload)


def assess_customer(
    *,
    scenario_id: str | None = None,
    features: Mapping[str, Any] | None = None,
    use_llm: bool = True,
    prompt_type: PromptType = "guided",
    model: ModelChoice = "configured",
    feature_path: str | Path = DEFAULT_FEATURE_PATH,
    rule_path: str | Path = DEFAULT_RULE_PATH,
    case_path: str | Path = DEFAULT_CASE_PATH,
) -> dict[str, Any]:
    """Run normalize → detect → retrieve → reason → validate for one customer."""

    if (scenario_id is None) == (features is None):
        raise ValueError("Provide exactly one of scenario_id or features.")
    definitions = load_feature_definitions_yaml(feature_path)
    feature_index = feature_registry_index(definitions)
    rules = load_rules_yaml(rule_path, known_features=feature_index)
    if scenario_id is not None:
        case = next((item for item in load_synthetic_cases(case_path) if item["case_id"] == scenario_id), None)
        if case is None:
            raise ValueError(f"Unknown synthetic scenario: {scenario_id}.")
        customer_features = dict(case["features"])
        label = str(case["label"])
    else:
        customer_features = dict(features or {})
        label = "Custom customer"

    prepared = run_reasoning_harness(
        customer_features,
        feature_index=feature_index,
        rules=rules,
    )
    prompt = _prompt_variant(prepared.prompt, prompt_type)
    output: Mapping[str, Any] | None = None
    provider: str | None = None
    model_name: str | None = None
    if use_llm:
        reasoner = _reasoner_for(model)
        if reasoner is None:
            raise RuntimeError("LLM is not configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY.")
        output = reasoner.complete(prompt)
        validate_reasoning_output(
            output,
            known_features=feature_index,
            known_rule_ids={rule.id for rule in prepared.retrieved_rules},
        )
        provider = reasoner.config.provider
        model_name = reasoner.config.model

    return {
        "scenario_id": scenario_id,
        "label": label,
        "normalized_features": prepared.normalized_features,
        "detected_domains": list(prepared.detected.domains),
        "observed_features": list(prepared.detected.observed_features),
        "missing_features": list(prepared.detected.missing_features),
        "unknown_features": list(prepared.detected.unknown_features),
        "retrieved_rules": [rule.to_dict() for rule in prepared.retrieved_rules],
        "prompt_type": prompt_type,
        "llm_called": output is not None,
        "provider": provider,
        "model": model_name,
        "output": dict(output) if output is not None else None,
        "trace": [
            "1. Chuẩn hóa feature khách hàng và giữ nguyên giá trị thiếu.",
            f"2. Phát hiện miền: {', '.join(prepared.detected.domains) or 'không có'}.",
            f"3. Truy xuất {len(prepared.retrieved_rules)} rule từ Kho tri thức.",
            f"4. Tạo prompt loại {prompt_type} từ feature và rule trong danh sách cho phép.",
            "5. Gọi LLM và kiểm tra đầu ra có cấu trúc."
            if output is not None
            else "5. Bỏ qua lời gọi LLM.",
        ],
    }


def challenge_assessment(
    *,
    scenario_id: str,
    original_output: Mapping[str, Any],
    challenge: str,
    model: ModelChoice = "configured",
    prompt_type: PromptType = "guided",
) -> dict[str, Any]:
    """Re-run a structured assessment with a counter-argument and compare labels."""

    baseline = assess_customer(
        scenario_id=scenario_id,
        use_llm=False,
        prompt_type=prompt_type,
        model=model,
    )
    reasoner = _reasoner_for(model)
    if reasoner is None:
        raise RuntimeError("LLM is not configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY.")
    prompt = json.dumps(
        {
            "customer_features": baseline["normalized_features"],
            "relevant_rules": baseline["retrieved_rules"],
            "original_output": dict(original_output),
            "counter_argument": challenge,
            "instruction": (
                "Reassess using no new facts. Do not change classification merely because the "
                "counter-argument is persuasive; return the standard structured schema."
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    challenged = reasoner.complete(prompt)
    validate_reasoning_output(
        challenged,
        known_features=set(baseline["normalized_features"]),
        known_rule_ids={rule["id"] for rule in baseline["retrieved_rules"]},
    )
    before = str(original_output.get("classification", ""))
    after = str(challenged.get("classification", ""))
    return {
        "original_classification": before,
        "challenged_classification": after,
        "classification_changed": before != after,
        "conclusion": "stable" if before == after else "changed_requires_review",
        "provider": reasoner.config.provider,
        "model": reasoner.config.model,
        "output": dict(challenged),
    }


def load_reference_evaluations(
    archive_path: str | Path,
    *,
    manifest_path: str | Path = DEFAULT_EVALUATION_MANIFEST,
) -> dict[str, Any]:
    """Evaluate the real response attachments in simulate.zip without inventing scores."""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    runs: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for run in manifest["runs"]:
            response_file = str(run["response_file"])
            if response_file not in names:
                runs.append({**run, "available": False, "checks": None})
                continue
            text = archive.read(response_file).decode("utf-8-sig")
            checks = evaluate_text_response(text, turn=run["turn"])
            runs.append({**run, "available": True, "checks": checks})
    return {
        "manifest_version": manifest["manifest_version"],
        "metrics_policy": manifest["metrics_policy"],
        "scenarios": manifest["scenarios"],
        "runs": runs,
    }
