"""Orchestration for the customer -> reasoning-harness demo flow.

The flow intentionally keeps three concerns separate:

* the customer intake is only an allow-listed profile;
* the current DC5 model evidence is aggregate research evidence, not a credit
  default probability;
* LLM rules are drafts and are never silently promoted into the Knowledge Base.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from credit_scoring.dc5.llm_insights import SafeProfile
from credit_scoring.dc5.model_evidence import ModelEvidence, load_latest_model_evidence
from credit_scoring.reasoning.feature_registry import (
    feature_registry_index,
    load_feature_definitions_yaml,
)
from credit_scoring.reasoning.harness import run_reasoning_harness
from credit_scoring.reasoning.rules import RuleRecord, load_rules_yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEATURE_PATH = REPO_ROOT / "configs/reasoning/feature_definitions.yaml"
DEFAULT_RULE_PATH = REPO_ROOT / "configs/reasoning/rules.yaml"
DEFAULT_CASE_PATH = REPO_ROOT / "configs/reasoning/synthetic_cases.yaml"
MODEL_TO_REASONING_FEATURE = {
    "active_domain_count_ord": "active_domain_count",
    "tenure_group_ord": "tenure_group",
    "recency_group_ord": "recency_group",
    "app_count_group_ord": "app_count_group",
    "app_tenure_group_ord": "app_tenure_group",
    "app_recency_days_ord": "app_recency_days",
    "loyalty_points_ord": "loyalty_points",
    "loyalty_tier_ord": "loyalty_tier",
    "telco_internet_usage_group_ord": "telco_internet_usage_group",
    "telco_internet_trend_group_ord": "telco_internet_trend_group",
}


class RuleCandidate(BaseModel):
    """A proposed rule that still requires validation and human review."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    feature_refs: list[str] = Field(min_length=1)
    domains: list[str] = Field(min_length=1)
    evidence_basis: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    confidence: str = Field(pattern="^(low|medium|high)$")


class FinalReasoning(BaseModel):
    """Customer-facing reasoning that cannot be mistaken for a credit decision."""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1)
    evidence: list[str]
    uncertainties: list[str]
    recommended_actions: list[str]


def load_synthetic_cases(path: str | Path = DEFAULT_CASE_PATH) -> tuple[dict[str, Any], ...]:
    """Load the three project-authored cases used for harness smoke tests."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("Loading synthetic cases requires PyYAML.") from exc
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("cases"), list):
        raise TypeError("Synthetic cases must be an object with a cases list.")
    cases = tuple(dict(case) for case in document["cases"])
    ids = [str(case.get("case_id", "")) for case in cases]
    if len(cases) != 3 or not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("The reasoning flow requires exactly three unique synthetic cases.")
    if not all(isinstance(case.get("features"), Mapping) for case in cases):
        raise TypeError("Every synthetic case must contain a features object.")
    return cases


def _safe_profile_payload(profile: SafeProfile) -> dict[str, Any]:
    return profile.model_dump(exclude_none=False)


def _extract_customer_features(profile: SafeProfile) -> dict[str, Any]:
    """Create an explicit intake extraction record without inventing alt-data."""

    payload = _safe_profile_payload(profile)
    return {
        "status": "complete",
        "source": "customer_intake",
        "fields": sorted(payload),
        "values": payload,
        "note": (
            "Đây là dữ liệu hồ sơ người dùng đã chuẩn hóa. Chưa có connector giao dịch "
            "hoặc lịch sử thanh toán để tạo alternative-data features."
        ),
    }


def _pattern_payload(evidence: ModelEvidence | None) -> dict[str, Any]:
    if evidence is None:
        return {
            "status": "unavailable",
            "research_only": True,
            "message": "Chưa có aggregate model evidence từ một research run.",
        }
    top_features = [
        {"feature": item.feature, "importance": item.importance}
        for item in evidence.top_features
    ]
    reasoning_feature_refs = sorted(
        {
            MODEL_TO_REASONING_FEATURE[item["feature"]]
            for item in top_features
            if item["feature"] in MODEL_TO_REASONING_FEATURE
        }
    )
    return {
        "status": "available",
        "research_only": True,
        "run_id": evidence.run_id,
        "model_name": evidence.model_name,
        "setting": evidence.setting,
        "target_definition": evidence.target_definition,
        "roc_auc": evidence.roc_auc,
        "pr_auc": evidence.pr_auc,
        "positive_rate": evidence.positive_rate,
        "top_features": top_features,
        "reasoning_feature_refs": reasoning_feature_refs,
        "inference_available": evidence.inference_available,
        "limitation": evidence.limitation,
        "message": (
            "Đây là pattern aggregate của target nghiên cứu hiện tại, không phải "
            "xác suất vỡ nợ hay quyết định tín dụng cá nhân."
        ),
    }


RULE_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rule": {"type": "string"},
                    "feature_refs": {"type": "array", "items": {"type": "string"}},
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "evidence_basis": {"type": "string"},
                    "limitation": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": [
                    "title",
                    "rule",
                    "feature_refs",
                    "domains",
                    "evidence_basis",
                    "limitation",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rules"],
    "additionalProperties": False,
}

FINAL_REASONING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "evidence", "uncertainties", "recommended_actions"],
    "additionalProperties": False,
}


def _rule_llm_settings() -> tuple[str, str, str] | None:
    provider = os.getenv("REASONING_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "")).lower()
    if not provider:
        provider = "openrouter" if os.getenv("OPENROUTER_API_KEY") else "openai"
    if provider == "openrouter":
        key_env = "OPENROUTER_API_KEY"
        model = os.getenv("REASONING_LLM_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    elif provider == "openai":
        key_env = "OPENAI_API_KEY"
        model = os.getenv("REASONING_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini"))
    else:
        raise ValueError("REASONING_LLM_PROVIDER must be openai or openrouter.")
    if not os.getenv(key_env):
        return None
    return provider, model, key_env


def _call_rule_llm(prompt: str) -> tuple[Mapping[str, Any], str, str]:
    settings = _rule_llm_settings()
    if settings is None:
        raise RuntimeError("LLM chưa được cấu hình; bỏ qua bước sinh rule.")
    provider, model, key_env = settings
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError('Cần cài dependency: pip install -e ".[web]"') from exc
    client = (
        OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ[key_env],
            default_headers={"X-OpenRouter-Title": "Alternative Data Rule Drafting"},
        )
        if provider == "openrouter"
        else OpenAI(api_key=os.environ[key_env])
    )
    if provider == "openrouter":
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Draft cautious, non-causal candidate rules from aggregate model "
                        "evidence. Never call a candidate validated and never invent a threshold."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "rule_candidates", "strict": True, "schema": RULE_CANDIDATE_SCHEMA},
            },
            extra_body={"provider": {"require_parameters": True}},
        )
        content = response.choices[0].message.content
    else:
        response = client.responses.create(
            model=model,
            store=False,
            instructions=(
                "Draft cautious, non-causal candidate rules from aggregate model evidence. "
                "Never call a candidate validated and never invent a threshold."
            ),
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "rule_candidates",
                    "strict": True,
                    "schema": RULE_CANDIDATE_SCHEMA,
                }
            },
        )
        content = response.output_text
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM trả về rule candidate rỗng.")
    payload = json.loads(content)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("rules"), list):
        raise TypeError("LLM rule response phải có trường rules dạng list.")
    return payload, provider, model


def _call_final_reasoning_llm(
    prompt: str,
) -> tuple[Mapping[str, Any], str, str]:
    settings = _rule_llm_settings()
    if settings is None:
        raise RuntimeError("LLM chưa được cấu hình; dùng fallback reasoning.")
    provider, model, key_env = settings
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError('Cần cài dependency: pip install -e ".[web]"') from exc
    client = (
        OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ[key_env],
            default_headers={"X-OpenRouter-Title": "Customer Reasoning"},
        )
        if provider == "openrouter"
        else OpenAI(api_key=os.environ[key_env])
    )
    system = (
        "Bạn là trợ lý reasoning thận trọng. Hãy viết summary, evidence, uncertainties "
        "và recommended_actions bằng tiếng Việt. Không kết luận duyệt/từ chối, không gọi "
        "đây là credit score, không suy diễn nhân quả và luôn giữ research limitation."
    )
    if provider == "openrouter":
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "customer_reasoning", "strict": True, "schema": FINAL_REASONING_SCHEMA},
            },
            extra_body={"provider": {"require_parameters": True}},
        )
        content = response.choices[0].message.content
    else:
        response = client.responses.create(
            model=model,
            store=False,
            instructions=system,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "customer_reasoning",
                    "strict": True,
                    "schema": FINAL_REASONING_SCHEMA,
                }
            },
        )
        content = response.output_text
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM trả về customer reasoning rỗng.")
    payload = json.loads(content)
    if not isinstance(payload, Mapping):
        raise TypeError("Customer reasoning phải là một object.")
    return payload, provider, model


def _final_reasoning(
    profile: SafeProfile,
    pattern: Mapping[str, Any],
    *,
    use_llm: bool,
) -> dict[str, Any]:
    fallback = FinalReasoning(
        summary=(
            "Hồ sơ đã được chuẩn hóa và chuyển qua Agent Harness. Chưa đủ dữ liệu "
            "giao dịch hoặc nhãn tín dụng để kết luận rủi ro cá nhân."
        ),
        evidence=[
            "Các trường customer intake đã được validate theo allow-list.",
            "ML evidence hiện là pattern aggregate của research run, không phải dự đoán cá nhân.",
        ],
        uncertainties=[
            "Chưa có transaction connector, lịch sử thanh toán có ngữ nghĩa xác nhận hoặc default label.",
            "Target hiện tại là high Telco monetary, không phải default/CIC.",
        ],
        recommended_actions=[
            "Bổ sung data lineage, observation cutoff và target tín dụng đã được phê duyệt.",
            "Giữ human review trước mọi quyết định; không dùng output này để duyệt hoặc từ chối.",
        ],
    )
    if not use_llm:
        return {
            "status": "deterministic_fallback",
            "provider": None,
            "model": None,
            **fallback.model_dump(),
        }
    prompt = json.dumps(
        {
            "customer_profile": _safe_profile_payload(profile),
            "aggregate_ml_pattern": {
                key: pattern[key]
                for key in (
                    "status",
                    "model_name",
                    "setting",
                    "target_definition",
                    "roc_auc",
                    "pr_auc",
                    "positive_rate",
                    "reasoning_feature_refs",
                    "limitation",
                )
                if key in pattern
            },
            "constraints": [
                "Do not produce a credit decision or probability of default.",
                "Separate profile observations from aggregate model evidence.",
                "State missing data and human-review requirement explicitly.",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    try:
        payload, provider, model = _call_final_reasoning_llm(prompt)
        reasoning = FinalReasoning.model_validate(payload)
        return {
            "status": "llm_generated",
            "provider": provider,
            "model": model,
            **reasoning.model_dump(),
        }
    except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "fallback_after_error",
            "provider": None,
            "model": None,
            **fallback.model_dump(),
            "error": str(exc),
        }


def _draft_rules(
    pattern: Mapping[str, Any],
    *,
    known_features: Mapping[str, Mapping[str, Any]],
    use_llm: bool,
) -> dict[str, Any]:
    if pattern.get("status") != "available":
        return {
            "status": "blocked_no_ml_evidence",
            "provider": None,
            "model": None,
            "rules": [],
            "note": "LLM không được phép bịa pattern khi chưa có ML evidence.",
        }
    if not use_llm:
        return {
            "status": "ready_to_run",
            "provider": None,
            "model": None,
            "rules": [],
            "note": "Bật tùy chọn LLM để tạo draft rule; draft vẫn cần validation và human review.",
        }
    if not pattern.get("reasoning_feature_refs"):
        return {
            "status": "blocked_no_registry_overlap",
            "provider": None,
            "model": None,
            "rules": [],
            "note": "ML pattern chưa có feature tương ứng trong reasoning registry.",
        }
    llm_evidence = {
        key: pattern[key]
        for key in (
            "run_id",
            "model_name",
            "setting",
            "target_definition",
            "roc_auc",
            "pr_auc",
            "positive_rate",
            "reasoning_feature_refs",
            "limitation",
        )
        if key in pattern
    }
    prompt = json.dumps(
        {
            "aggregate_model_evidence": llm_evidence,
            "known_features": sorted(known_features),
            "constraints": [
                "Chỉ tham chiếu known_features.",
                "Không dùng causal wording, không tự tạo threshold.",
                "Mọi output là candidate, không phải production rule.",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    try:
        payload, provider, model = _call_rule_llm(prompt)
        candidates = [RuleCandidate.model_validate(item) for item in payload["rules"][:5]]
        rejected_features: set[str] = set()
        valid_candidates: list[RuleCandidate] = []
        for candidate in candidates:
            rejected_features.update(set(candidate.feature_refs) - set(known_features))
            if not (set(candidate.feature_refs) - set(known_features)):
                valid_candidates.append(candidate)
        if rejected_features:
            return {
                "status": "rejected_unknown_features",
                "provider": provider,
                "model": model,
                "rules": [candidate.model_dump() for candidate in valid_candidates],
                "note": (
                    "Một số candidate bị reject vì tham chiếu feature ngoài registry: "
                    + ", ".join(sorted(rejected_features))
                    + ". Không candidate nào được tự động promote vào KB."
                ),
            }
        return {
            "status": "candidate_generated",
            "provider": provider,
            "model": model,
            "rules": [candidate.model_dump() for candidate in valid_candidates],
            "note": "Candidate chưa được thêm vào KB và chưa được dùng như production rule.",
        }
    except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "error",
            "provider": None,
            "model": None,
            "rules": [],
            "note": str(exc),
        }


def _load_kb(
    feature_index: Mapping[str, Mapping[str, Any]],
    path: str | Path = DEFAULT_RULE_PATH,
) -> tuple[str, tuple[RuleRecord, ...]]:
    import yaml

    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = load_rules_yaml(path, known_features=feature_index)
    return str(document.get("knowledge_base_version", "unknown")), rules


def _run_synthetic_harness(
    cases: tuple[dict[str, Any], ...],
    *,
    feature_index: Mapping[str, Mapping[str, Any]],
    rules: tuple[RuleRecord, ...],
    use_llm: bool,
) -> list[dict[str, Any]]:
    reasoner = None
    if use_llm:
        from credit_scoring.reasoning.llm_client import create_reasoner_from_environment

        reasoner = create_reasoner_from_environment()
    outputs: list[dict[str, Any]] = []
    for case in cases:
        result = run_reasoning_harness(
            case["features"], feature_index=feature_index, rules=rules, reasoner=reasoner
        )
        outputs.append(
            {
                "case_id": case["case_id"],
                "label": case["label"],
                "description": case["description"],
                "detected_domains": list(result.detected.domains),
                "observed_features": list(result.detected.observed_features),
                "missing_information": list(result.detected.missing_features),
                "unknown_features": list(result.detected.unknown_features),
                "retrieved_rule_ids": [rule.id for rule in result.retrieved_rules],
                "reasoning_output": result.output,
                "llm_called": result.llm_called,
            }
        )
    return outputs


def discover_candidate_rules(
    *,
    use_llm: bool = False,
    artifact_dir: str | Path = "artifacts/dc5_customer_analysis",
) -> dict[str, Any]:
    """Return real aggregate ML evidence and optional LLM-drafted candidate rules."""

    definitions = load_feature_definitions_yaml(DEFAULT_FEATURE_PATH)
    feature_index = feature_registry_index(definitions)
    pattern = _pattern_payload(load_latest_model_evidence(artifact_dir))
    return {
        "ml_pattern": pattern,
        "candidate_rules": _draft_rules(
            pattern,
            known_features=feature_index,
            use_llm=use_llm,
        ),
    }


def run_credit_reasoning_flow(
    profile: SafeProfile,
    *,
    use_llm: bool = False,
    artifact_dir: str | Path = "artifacts/dc5_customer_analysis",
) -> dict[str, Any]:
    """Run the complete demo flow and return a UI/API-safe trace payload."""

    definitions = load_feature_definitions_yaml(DEFAULT_FEATURE_PATH)
    feature_index = feature_registry_index(definitions)
    knowledge_version, rules = _load_kb(feature_index)
    cases = load_synthetic_cases()
    discovery = discover_candidate_rules(use_llm=use_llm, artifact_dir=artifact_dir)
    pattern = discovery["ml_pattern"]
    rule_drafts = discovery["candidate_rules"]
    final_reasoning = _final_reasoning(profile, pattern, use_llm=use_llm)
    synthetic_results = _run_synthetic_harness(
        cases, feature_index=feature_index, rules=rules, use_llm=use_llm
    )
    return {
        "flow_version": "credit-reasoning-flow-v1",
        "customer_profile": _safe_profile_payload(profile),
        "extraction": _extract_customer_features(profile),
        "ml_pattern": pattern,
        "llm_rule_generation": rule_drafts,
        "final_reasoning": final_reasoning,
        "knowledge_base": {
            "version": knowledge_version,
            "status": "loaded",
            "rule_count": len(rules),
            "rules": [rule.to_dict() for rule in rules],
        },
        "synthetic_tests": synthetic_results,
        "agent_harness": {
            "status": "completed",
            "case_count": len(synthetic_results),
            "llm_calls": sum(1 for item in synthetic_results if item["llm_called"]),
            "note": "Synthetic tests kiểm tra routing, rule retrieval và schema; không có gold credit label.",
        },
        "trace": [
            "1. Intake: nhận profile allow-list từ trang người dùng.",
            "2. Extract: chuẩn hóa trường intake; chưa giả định có transaction connector.",
            f"3. ML pattern: {pattern['status']} aggregate research evidence.",
            f"4. LLM -> rule candidate: {rule_drafts['status']}.",
            f"4b. Final reasoning: {final_reasoning['status']}.",
            f"5. Knowledge Base: loaded {len(rules)} candidate rules ({knowledge_version}).",
            f"6. Synthetic test: chạy {len(synthetic_results)} case không có gold credit label.",
            "7. Agent Harness: normalize -> detect -> retrieve -> prompt -> validate.",
        ],
        "disclaimer": (
            "Demo nghiên cứu; không phải credit score, xác suất vỡ nợ hoặc quyết định "
            "phê duyệt/từ chối. Rule candidate cần data support, holdout và human review."
        ),
    }
