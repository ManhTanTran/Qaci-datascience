"""Guardrailed AI explanation contracts.

No provider call is made here.  A provider adapter may consume the generated
context and return a structured object; this module keeps the rule result
authoritative and rejects loan-decision fields from model output.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

FORBIDDEN_DECISION_KEYS = {
    "loan_approved",
    "loan_rejected",
    "ai_decision",
    "loan_decision",
}
RESPONSE_FIELDS = (
    "explanation",
    "strong_evidence",
    "weak_evidence",
    "contextual_evidence",
    "missing_data",
    "contradictions",
    "unsupported_inferences",
    "rule_conflict",
)


def build_explanation_context(
    profile: Mapping[str, Any],
    rule_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the small business-profile context supplied to an AI reasoner."""

    groups = {}
    for group, value in profile.items():
        if group.startswith("_") or group == "evidence_trace":
            continue
        groups[group] = value
    return {
        "profile": groups,
        "rule_result": copy.deepcopy(dict(rule_result)),
        "instructions": {
            "role": "explanation_only",
            "rule_is_authoritative": True,
            "contextual_proxy_is_not_personal_fact": True,
            "allowed_decision_labels": ["PASS", "FAIL", "UNKNOWN"],
            "assessment_is_non_authoritative": True,
            "do_not_output": sorted(FORBIDDEN_DECISION_KEYS),
        },
    }


def build_explanation_prompt(
    profile: Mapping[str, Any],
    rule_result: Mapping[str, Any],
) -> str:
    """Serialize the guarded context for an external structured-output model."""

    return json.dumps(build_explanation_context(profile, rule_result), ensure_ascii=False, default=str)


def _parse_response(response: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, str):
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError:
            return {"explanation": response}
        if not isinstance(decoded, Mapping):
            raise TypeError("AI response JSON must be an object.")
        return dict(decoded)
    raise TypeError("AI response must be an object or JSON/text string.")


def normalize_ai_response(
    response: Mapping[str, Any] | str | None,
    rule_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize an AI response while keeping ``rule_result.decision`` immutable."""

    if response is None:
        return {
            "status": "not_run",
            "explanation": None,
            "strong_evidence": [],
            "weak_evidence": [],
            "contextual_evidence": [],
            "missing_data": [],
            "contradictions": [],
            "unsupported_inferences": [],
            "rule_conflict": False,
        }
    payload = _parse_response(response)
    forbidden = sorted(FORBIDDEN_DECISION_KEYS.intersection(payload))
    if forbidden:
        raise ValueError(f"AI response contains authoritative decision fields: {forbidden}")
    list_fields = (
        "strong_evidence",
        "weak_evidence",
        "contextual_evidence",
        "missing_data",
        "contradictions",
        "unsupported_inferences",
    )
    for field in list_fields:
        if field in payload and not isinstance(payload[field], list):
            raise TypeError(f"AI response field {field} must be a list.")
    normalized = {
        "status": "available",
        "explanation": str(payload.get("explanation", "")),
        "strong_evidence": list(payload.get("strong_evidence", [])),
        "weak_evidence": list(payload.get("weak_evidence", [])),
        "contextual_evidence": list(payload.get("contextual_evidence", [])),
        "missing_data": list(payload.get("missing_data", [])),
        "contradictions": list(payload.get("contradictions", [])),
        "unsupported_inferences": list(payload.get("unsupported_inferences", [])),
        "rule_conflict": bool(payload.get("rule_conflict", False)),
    }
    assessment = payload.get("assessment", payload.get("rule_result", payload.get("decision")))
    if assessment is not None:
        normalized["assessment"] = assessment
        if str(assessment).upper() in {"PASS", "FAIL", "UNKNOWN"}:
            normalized["rule_conflict"] = normalized["rule_conflict"] or (
                str(assessment).upper() != str(rule_result.get("decision", UNKNOWN)).upper()
            )
    if "confidence" in payload:
        normalized["confidence"] = payload["confidence"]
    return normalized


# Avoid a second public source of truth for the label.
UNKNOWN = "UNKNOWN"
