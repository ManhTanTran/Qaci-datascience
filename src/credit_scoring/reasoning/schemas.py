"""Strict contracts for the reasoning output proposed in Phase 1."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

CLASSIFICATIONS = ("Relatively stable", "Mixed", "Potentially risky")
CONFIDENCES = ("Low", "Medium", "High")
REASONING_OUTPUT_FIELDS = (
    "classification",
    "confidence",
    "positive_evidence",
    "negative_evidence",
    "conflicts",
    "rules_used",
    "unsupported_information",
    "missing_information",
    "reasoning_summary",
)
EVIDENCE_FIELDS = ("positive_evidence", "negative_evidence", "conflicts")


def validate_reasoning_output(
    payload: Mapping[str, Any],
    *,
    known_features: Collection[str] = (),
    known_rule_ids: Collection[str] = (),
) -> None:
    """Validate the minimal JSON contract without calling an LLM.

    The function intentionally validates references and shape only. It does not
    decide whether a claim is statistically supported; that belongs to rule
    validation and human review.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("Reasoning output must be an object.")

    expected = set(REASONING_OUTPUT_FIELDS)
    actual = set(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        raise ValueError("Invalid reasoning output schema (" + "; ".join(details) + ").")

    if payload["classification"] not in CLASSIFICATIONS:
        raise ValueError("classification must be one of the supported assessments.")
    if payload["confidence"] not in CONFIDENCES:
        raise ValueError("confidence must be Low, Medium or High.")

    for field in (*EVIDENCE_FIELDS, "rules_used", "unsupported_information", "missing_information"):
        if not isinstance(payload[field], list):
            raise TypeError(f"{field} must be a list.")
    if not isinstance(payload["reasoning_summary"], str):
        raise TypeError("reasoning_summary must be a string.")

    feature_set = set(known_features)
    for field in EVIDENCE_FIELDS:
        for index, item in enumerate(payload[field]):
            if not isinstance(item, Mapping):
                raise TypeError(f"{field}[{index}] must be an object.")
            feature = item.get("feature")
            if feature is not None and feature_set and feature not in feature_set:
                raise ValueError(f"{field}[{index}] references unknown feature: {feature}.")

    rule_set = set(known_rule_ids)
    if rule_set:
        unknown_rules = sorted(set(payload["rules_used"]) - rule_set)
        if unknown_rules:
            raise ValueError("rules_used references unknown rule IDs: " + ", ".join(unknown_rules))
