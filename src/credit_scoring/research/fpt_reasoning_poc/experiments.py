"""Research-only ablation and repeated-run orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from credit_scoring.reasoning.ai import build_explanation_context, normalize_ai_response
from credit_scoring.reasoning.rules import evaluate_profile_rules

CURRENT_GROUPS = (
    "user_id",
    "age",
    "local_context",
    "location",
    "device_usage",
    "payment_history_12m",
    "shopping_installment",
    "orders",
)
RESEARCH_CONFIGURATIONS: dict[str, tuple[str, ...]] = {
    "current": CURRENT_GROUPS,
    "current_healthcare": CURRENT_GROUPS + ("healthcare_spending",),
    "current_fpt_education": CURRENT_GROUPS + ("fpt_education",),
    "current_both": CURRENT_GROUPS + ("healthcare_spending", "fpt_education"),
}
RUN_ID_FIELDS = ("experiment_id", "case_id", "configuration", "repeat_id", "model")
CONFIGURATION_ALIASES = {
    "A": "current",
    "B": "current_healthcare",
    "C": "current_fpt_education",
    "D": "current_both",
    "healthcare": "current_healthcare",
    "education": "current_fpt_education",
    "both": "current_both",
    "current + healthcare": "current_healthcare",
    "current + fpt education": "current_fpt_education",
    "current + healthcare + fpt education": "current_both",
    "with_healthcare": "current_healthcare",
    "with_fpt_education": "current_fpt_education",
    "with_both": "current_both",
}


def feature_groups_for_configuration(configuration: str) -> tuple[str, ...]:
    name = CONFIGURATION_ALIASES.get(configuration, configuration)
    if name not in RESEARCH_CONFIGURATIONS:
        raise ValueError(
            f"Unknown research configuration {configuration!r}; "
            f"choose from {sorted(RESEARCH_CONFIGURATIONS)}."
        )
    return RESEARCH_CONFIGURATIONS[name]


@dataclass(frozen=True)
class ResearchExperimentConfig:
    """Configurable experiment dimensions; no repeat count is hard-coded."""

    experiment_id: str = "fpt_reasoning_poc"
    repeat_count: int = 1
    model: str = "not_configured"
    case_ids: tuple[str, ...] | None = None
    configurations: tuple[str, ...] = tuple(RESEARCH_CONFIGURATIONS)

    def __post_init__(self) -> None:
        if self.repeat_count < 1:
            raise ValueError("repeat_count must be >= 1")
        for configuration in self.configurations:
            feature_groups_for_configuration(configuration)


Responder = Callable[..., Any]


def _profile_id(profile: dict[str, Any]) -> str:
    identifier = profile.get("user_id")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    if identifier is None:
        raise ValueError("Every research profile needs user_id.")
    return str(identifier)


def _profile_input(profile: dict[str, Any], groups: tuple[str, ...]) -> dict[str, Any]:
    return {
        group: profile[group]
        for group in groups
        if group in profile
    }


def _call_responder(responder: Responder, context: dict[str, Any], model: str) -> Any:
    try:
        return responder(context, model=model)
    except TypeError:
        return responder(context)


def run_research_experiment(
    profiles: list[dict[str, Any]],
    *,
    config: ResearchExperimentConfig | None = None,
    rule_results: list[dict[str, Any]] | None = None,
    responder: Responder | None = None,
) -> list[dict[str, Any]]:
    """Run every case/configuration/repeat and retain raw + structured output."""

    resolved = config or ResearchExperimentConfig()
    by_id = {_profile_id(profile): profile for profile in profiles}
    if len(by_id) != len(profiles):
        raise ValueError("Research profiles must have unique user_id values.")
    selected_ids = tuple(str(item) for item in (resolved.case_ids or tuple(by_id)))
    unknown = sorted(set(selected_ids).difference(by_id))
    if unknown:
        raise ValueError(f"Unknown research case IDs: {unknown}")
    provided_rules = {
        str(result.get("user_id")): result for result in (rule_results or [])
    }
    results: list[dict[str, Any]] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for case_id in selected_ids:
        profile = by_id[case_id]
        rule_result = provided_rules.get(case_id) or evaluate_profile_rules(profile)
        for configuration in resolved.configurations:
            name = CONFIGURATION_ALIASES.get(configuration, configuration)
            groups = feature_groups_for_configuration(configuration)
            selected_profile = _profile_input(profile, groups)
            context = build_explanation_context(selected_profile, rule_result)
            context["experiment"] = {
                "configuration": name,
                "feature_groups": list(groups),
                "case_id": case_id,
            }
            for repeat_id in range(resolved.repeat_count):
                raw_response: Any = None
                error: str | None = None
                if responder is not None:
                    try:
                        raw_response = _call_responder(responder, context, resolved.model)
                        response = normalize_ai_response(raw_response, rule_result)
                    except Exception as exc:  # keep other repeats inspectable
                        response = normalize_ai_response(None, rule_result)
                        error = f"{type(exc).__name__}: {exc}"
                else:
                    response = normalize_ai_response(None, rule_result)
                results.append(
                    {
                        "experiment_id": resolved.experiment_id,
                        "case_id": case_id,
                        "run_id": (
                            f"{resolved.experiment_id}:{resolved.model}:{case_id}:{name}:{repeat_id}"
                        ),
                        "repeat_id": repeat_id,
                        "model": resolved.model,
                        "configuration": name,
                        "feature_groups": list(groups),
                        "timestamp": timestamp,
                        "rule_result": rule_result,
                        "input": context,
                        "response": response,
                        "raw_response": raw_response,
                        "error": error,
                    }
                )
    return results


def write_experiment_results(
    results: list[dict[str, Any]],
    *,
    jsonl_path: str | Path,
    csv_path: str | Path | None = None,
) -> None:
    """Persist lossless JSONL and a readable one-row-per-run CSV."""

    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    if csv_path is None:
        return
    import pandas as pd

    rows = []
    for result in results:
        rows.append(
            {
                "experiment_id": result["experiment_id"],
                "case_id": result["case_id"],
                "run_id": result["run_id"],
                "repeat_id": result["repeat_id"],
                "model": result["model"],
                "configuration": result["configuration"],
                "feature_groups": ",".join(result["feature_groups"]),
                "rule_decision": result["rule_result"].get("decision"),
                "response_status": result["response"].get("status"),
                "explanation": result["response"].get("explanation"),
                "rule_conflict": result["response"].get("rule_conflict"),
                "raw_response": json.dumps(result["raw_response"], ensure_ascii=False, default=str),
                "error": result["error"] or "",
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")


def run_identity(record: dict[str, Any]) -> tuple[Any, ...]:
    """Return the explicit identity used to audit legacy experiment rows."""

    return tuple(record.get(field) for field in RUN_ID_FIELDS)


def duplicate_run_identities(results: list[dict[str, Any]]) -> dict[tuple[Any, ...], int]:
    """Report duplicates without silently dropping any legacy response."""

    counts: dict[tuple[Any, ...], int] = {}
    for result in results:
        identity = run_identity(result)
        counts[identity] = counts.get(identity, 0) + 1
    return {identity: count for identity, count in counts.items() if count > 1}
