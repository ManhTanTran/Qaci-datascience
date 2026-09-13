"""End-to-end shared FPT reasoning data pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from credit_scoring.reasoning.ai import build_explanation_prompt, normalize_ai_response
from credit_scoring.reasoning.ingestion import InputInspection, load_input
from credit_scoring.reasoning.mapping import BUSINESS_GROUPS, load_feature_mapping
from credit_scoring.reasoning.profiles import build_profiles, profiles_to_dataframe
from credit_scoring.reasoning.rules import evaluate_profile_rules
from credit_scoring.reasoning.validation import validate_frame

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "research" / "fpt_reasoning_poc"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "research" / "fpt_reasoning_poc"


@dataclass(frozen=True)
class FPTPipelineResult:
    """In-memory result and artifact paths for one application/research run."""

    inspection: InputInspection
    validation_report: dict[str, Any]
    profiles: list[dict[str, Any]]
    rule_results: list[dict[str, Any]]
    explanations: list[dict[str, Any]]
    artifact_paths: dict[str, Path]


ExplanationResponder = Callable[..., Any]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _mapping_report(
    frame: pd.DataFrame,
    profiles: list[dict[str, Any]],
    validation_report: dict[str, Any],
    mapping: dict[str, Any],
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for group in BUSINESS_GROUPS:
        spec = mapping["fields"][group]
        details = [
            validation_report["row_fields"][str(index)][group]
            for index in frame.index
        ]
        statuses = {detail["status"] for detail in details}
        status = "invalid" if "invalid" in statuses else "available" if "available" in statuses else "missing"
        traces = [
            {
                "user_id": profile.get("user_id"),
                "source_row": profile.get("_metadata", {}).get("source", {}).get("row"),
                "source_sheet": profile.get("_metadata", {}).get("source", {}).get("sheet"),
            }
            for profile in profiles
        ]
        report.append(
            {
                "business_field": group,
                "raw_columns": list(spec["raw_columns"]),
                "raw_columns_present": [column for column in spec["raw_columns"] if column in frame],
                "raw_columns_missing": [column for column in spec["raw_columns"] if column not in frame],
                "transform": spec["transform"],
                "status": status,
                "semantic_type": spec["semantic_type"],
                "description": spec["description"],
                "source_trace": traces,
            }
        )
    return report


def _call_responder(
    responder: ExplanationResponder,
    profile: dict[str, Any],
    rule_result: dict[str, Any],
    model: str | None,
) -> Any:
    context = build_explanation_prompt(profile, rule_result)
    try:
        return responder(context, profile=profile, rule_result=rule_result, model=model)
    except TypeError:
        return responder(context)


def run_fpt_pipeline(
    input_path: str | Path,
    *,
    sheet: str | None = None,
    mapping_path: str | Path | None = None,
    processed_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    explanation_responder: ExplanationResponder | None = None,
    model: str | None = None,
) -> FPTPipelineResult:
    """Run ingestion → validation → mapping/profile → deterministic rules."""

    mapping = load_feature_mapping(mapping_path)
    frame, inspection = load_input(input_path, sheet=sheet, mapping=mapping)
    validation_report = validate_frame(frame, mapping)
    if not validation_report["valid_for_profile_build"]:
        raise ValueError(
            "Input failed structural validation; inspect validation_report.json before profile build."
        )
    profiles = build_profiles(frame, mapping, validation_report=validation_report)
    rule_results = [evaluate_profile_rules(profile) for profile in profiles]
    explanations: list[dict[str, Any]] = []
    if explanation_responder is not None:
        for profile, rule_result in zip(profiles, rule_results, strict=True):
            response = _call_responder(explanation_responder, profile, rule_result, model)
            explanation = normalize_ai_response(response, rule_result)
            explanations.append(
                {
                    "user_id": profile.get("user_id"),
                    "rule_result": rule_result,
                    "explanation": explanation,
                    "raw_response": response,
                }
            )

    processed = Path(processed_dir) if processed_dir is not None else DEFAULT_PROCESSED_DIR
    output = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    profile_csv = processed / "profiles.csv"
    profile_jsonl = processed / "profiles.jsonl"
    validation_json = processed / "validation_report.json"
    mapping_json = processed / "mapping_report.json"
    rules_jsonl = output / "rule_results.jsonl"
    _write_json(validation_json, validation_report)
    _write_json(mapping_json, _mapping_report(frame, profiles, validation_report, mapping))
    profiles_to_dataframe(profiles).to_csv(profile_csv, index=False, encoding="utf-8-sig")
    _write_jsonl(profile_jsonl, profiles)
    _write_jsonl(rules_jsonl, rule_results)
    artifact_paths = {
        "profiles_csv": profile_csv,
        "profiles_jsonl": profile_jsonl,
        "validation_report": validation_json,
        "mapping_report": mapping_json,
        "rule_results": rules_jsonl,
    }
    if explanations:
        explanation_path = output / "explanations.jsonl"
        _write_jsonl(explanation_path, explanations)
        artifact_paths["explanations"] = explanation_path
    return FPTPipelineResult(
        inspection=inspection,
        validation_report=validation_report,
        profiles=profiles,
        rule_results=rule_results,
        explanations=explanations,
        artifact_paths=artifact_paths,
    )
