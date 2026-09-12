from __future__ import annotations

from pathlib import Path

import pytest

from credit_scoring.reasoning.rules import (
    load_rules_yaml,
    normalize_rule_payload,
    validate_rule_payload,
)

ROOT = Path(__file__).parents[1]
FEATURES = {
    "payment_on_time_rate_12m",
    "overdue_days_max_12m",
    "payment_failure_count_12m",
    "active_domain_count",
    "telco_internet_usage_group",
}


def _rule(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "RULE_PAY_001",
        "type": "evidence_priority",
        "domains": ["payment", "engagement"],
        "features": ["payment_on_time_rate_12m"],
        "rule": "Payment behavior receives priority when signals conflict.",
        "source": "human",
        "evidence": "Design principle; no statistical support claimed.",
        "limitation": "Payment semantics remain unconfirmed.",
        "confidence": "medium",
        "status": "candidate",
        "version": "1.0",
        "owner": "reviewer",
        "validation": {
            "data_support": "not_run",
            "holdout": "not_run",
            "logical_consistency": "pending",
            "causal_claim_check": "passed",
            "human_review": "pending",
        },
    }
    payload.update(overrides)
    return payload


def test_load_rules_yaml_validates_all_candidate_rules() -> None:
    rules = load_rules_yaml(ROOT / "configs/reasoning/rules.yaml")
    assert len(rules) == 5
    assert {rule.status for rule in rules} == {"candidate"}
    assert "RULE_PAY_001" in {rule.id for rule in rules}


def test_normalize_rule_returns_immutable_metadata() -> None:
    rule = normalize_rule_payload(_rule(), known_features=FEATURES)
    assert rule.id == "RULE_PAY_001"
    assert rule.features == ("payment_on_time_rate_12m",)
    assert rule.to_dict()["validation"]["human_review"] == "pending"


def test_rule_rejects_unknown_feature_and_causal_wording() -> None:
    with pytest.raises(ValueError, match="unknown features"):
        validate_rule_payload(_rule(features=["unknown_feature"]), known_features=FEATURES)
    with pytest.raises(ValueError, match="causal"):
        validate_rule_payload(_rule(rule="Payment behavior causes low credit risk."))


def test_validated_rule_requires_support_and_human_review() -> None:
    with pytest.raises(ValueError, match="validated rule"):
        validate_rule_payload(_rule(status="validated"))


def test_rule_ids_must_be_unique_in_yaml(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        """schema_version: test
rules:
  - id: RULE_PAY_001
    type: guardrail
    domains: [payment]
    features: [payment_on_time_rate_12m]
    rule: x
    source: human
    evidence: x
    limitation: x
    confidence: low
    status: candidate
    version: '1.0'
    owner: x
    validation: {data_support: not_run, holdout: not_run, logical_consistency: pending, causal_claim_check: passed, human_review: pending}
  - id: RULE_PAY_001
    type: guardrail
    domains: [payment]
    features: [payment_on_time_rate_12m]
    rule: y
    source: human
    evidence: y
    limitation: y
    confidence: low
    status: candidate
    version: '1.0'
    owner: y
    validation: {data_support: not_run, holdout: not_run, logical_consistency: pending, causal_claim_check: passed, human_review: pending}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unique"):
        load_rules_yaml(path, known_features=FEATURES)
