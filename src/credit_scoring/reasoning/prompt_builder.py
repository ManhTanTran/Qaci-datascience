"""Build a traceable reasoning payload from customer data and retrieved rules."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from credit_scoring.reasoning.rules import RuleRecord
from credit_scoring.reasoning.schemas import REASONING_OUTPUT_FIELDS


def build_reasoning_payload(
    customer_features: Mapping[str, Any],
    *,
    feature_index: Mapping[str, Mapping[str, Any]],
    relevant_rules: Sequence[RuleRecord],
    missing_features: Sequence[str] = (),
) -> dict[str, Any]:
    """Create the structured input that an interchangeable LLM client receives."""

    selected_features = {
        feature: customer_features[feature]
        for feature in sorted(customer_features)
        if feature in feature_index and feature_index[feature].get("allowed_for_reasoning", True)
    }
    definitions = [
        {
            "name": feature,
            "domain": str(feature_index[feature]["domain"]),
            "evidence_type": str(feature_index[feature]["evidence_type"]),
            "credit_relevance": str(feature_index[feature]["credit_relevance"]),
            "limitation": str(feature_index[feature]["limitation"]),
        }
        for feature in sorted(selected_features)
        if feature in feature_index
    ]
    return {
        "customer_features": selected_features,
        "feature_definitions": definitions,
        "relevant_rules": [rule.to_dict() for rule in relevant_rules],
        "missing_information": sorted(set(missing_features)),
        "output_schema": list(REASONING_OUTPUT_FIELDS),
        "instructions": [
            "Use only supplied customer features and retrieved rule IDs.",
            "Distinguish direct behavioral evidence from proxy/context evidence.",
            "Do not convert missing values into negative evidence.",
            "Do not make unsupported causal claims or invent thresholds.",
        ],
    }


def build_reasoning_prompt(payload: Mapping[str, Any]) -> str:
    """Serialize the payload deterministically for an LLM adapter."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
