from __future__ import annotations

from pathlib import Path

import pytest

from credit_scoring.reasoning.feature_registry import (
    feature_registry_index,
    load_feature_definitions_yaml,
    normalize_customer_features,
)
from credit_scoring.reasoning.harness import run_reasoning_harness
from credit_scoring.reasoning.prompt_builder import build_reasoning_payload
from credit_scoring.reasoning.retriever import detect_domains, retrieve_rules
from credit_scoring.reasoning.rules import load_rules_yaml

ROOT = Path(__file__).parents[1]
FEATURE_DEFINITIONS = load_feature_definitions_yaml(ROOT / "configs/reasoning/feature_definitions.yaml")
FEATURE_INDEX = feature_registry_index(FEATURE_DEFINITIONS)
RULES = load_rules_yaml(
    ROOT / "configs/reasoning/rules.yaml",
    known_features=FEATURE_INDEX,
)


def test_normalization_preserves_zero_and_normalizes_attachment_markers() -> None:
    normalized = normalize_customer_features(
        {"\ufeffpayment_on_time_rate_12m": 0, "healthcare_spend_6m": "Không có dữ liệu"}
    )
    assert normalized == {"payment_on_time_rate_12m": 0, "healthcare_spend_6m": None}

    with pytest.raises(ValueError, match="Duplicate"):
        normalize_customer_features({"\ufefffeature": 1, "feature": 2})


def test_domain_detection_separates_observed_missing_and_unknown() -> None:
    detected = detect_domains(
        {
            "payment_on_time_rate_12m": 0.72,
            "active_domain_count": "4+ services",
            "healthcare_spend_6m": None,
            "unknown_feature": 1,
        },
        FEATURE_INDEX,
    )
    assert detected.domains == ("engagement", "payment")
    assert detected.observed_features == ("active_domain_count", "payment_on_time_rate_12m")
    assert detected.missing_features == ("healthcare_spend_6m",)
    assert detected.unknown_features == ("unknown_feature",)


def test_retriever_prioritizes_payment_conflict_rules() -> None:
    retrieved = retrieve_rules(
        RULES,
        detected_domains={"payment", "engagement", "shopping"},
        observed_features={
            "payment_on_time_rate_12m",
            "overdue_days_max_12m",
            "payment_failure_count_12m",
            "active_domain_count",
            "telco_internet_usage_group",
            "online_purchase_frequency",
        },
    )
    ids = [rule.id for rule in retrieved]
    assert ids[:2] == ["RULE_PAY_001", "RULE_PAY_002"]
    assert "RULE_PAY_003" in ids


def test_harness_builds_prompt_without_calling_llm() -> None:
    result = run_reasoning_harness(
        {
            "payment_on_time_rate_12m": 0.72,
            "overdue_days_max_12m": 25,
            "payment_failure_count_12m": 4,
            "active_domain_count": "4+ services",
            "healthcare_spend_6m": "Không có dữ liệu",
        },
        feature_index=FEATURE_INDEX,
        rules=RULES,
    )
    assert result.llm_called is False
    assert result.output is None
    assert "RULE_PAY_001" in result.prompt
    assert result.detected.missing_features == ("healthcare_spend_6m",)


def test_prompt_excludes_features_blocked_for_individual_reasoning() -> None:
    payload = build_reasoning_payload(
        {"gender": "female", "payment_on_time_rate_12m": 0.91},
        feature_index=FEATURE_INDEX,
        relevant_rules=(),
    )

    assert "gender" not in payload["customer_features"]
    assert payload["customer_features"]["payment_on_time_rate_12m"] == 0.91


class FakeReasoner:
    def complete(self, _prompt: str) -> dict[str, object]:
        return {
            "classification": "Potentially risky",
            "confidence": "Medium",
            "positive_evidence": [],
            "negative_evidence": [{"feature": "payment_on_time_rate_12m", "value": 0.72}],
            "conflicts": [],
            "rules_used": ["RULE_PAY_001"],
            "unsupported_information": [],
            "missing_information": [],
            "reasoning_summary": "Payment behavior is concerning; engagement is not sufficient to override it.",
        }


def test_harness_validates_provider_output_and_rule_references() -> None:
    result = run_reasoning_harness(
        {"payment_on_time_rate_12m": 0.72},
        feature_index=FEATURE_INDEX,
        rules=RULES,
        reasoner=FakeReasoner(),
    )
    assert result.llm_called is True
    assert result.output is not None

    class BadReasoner:
        def complete(self, _prompt: str) -> dict[str, object]:
            output = FakeReasoner().complete(_prompt)
            output["rules_used"] = ["RULE_UNKNOWN"]
            return output

    with pytest.raises(ValueError, match="unknown rule"):
        run_reasoning_harness(
            {"payment_on_time_rate_12m": 0.72},
            feature_index=FEATURE_INDEX,
            rules=RULES,
            reasoner=BadReasoner(),
        )
