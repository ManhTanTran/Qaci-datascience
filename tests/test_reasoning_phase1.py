from __future__ import annotations

import pytest

from credit_scoring.reasoning.evaluation import evaluate_text_response, parse_one_shot_assessments
from credit_scoring.reasoning.schemas import validate_reasoning_output


def test_parse_one_shot_assessments_extracts_three_labels() -> None:
    text = """
    Customer 1 — **Relatively stable**
    Customer 2 — **Potentially risky**
    Customer 3 — **Mixed**
    """
    assert parse_one_shot_assessments(text) == {
        1: "Relatively stable",
        2: "Potentially risky",
        3: "Mixed",
    }


def test_parse_one_shot_assessments_supports_customer_sections() -> None:
    text = """
    ### 1. Khách hàng 1
    *Overall assessment:* Relatively stable
    ### 2. Khách hàng 2
    *Overall assessment:* Potentially risky
    ### 3. Khách hàng 3
    *Overall assessment:* Mixed
    """
    assert parse_one_shot_assessments(text) == {
        1: "Relatively stable",
        2: "Potentially risky",
        3: "Mixed",
    }


def test_evaluation_checks_are_descriptive_and_do_not_make_gold_claims() -> None:
    result = evaluate_text_response(
        "Customer 1 — **Mixed**. Có proxy gián tiếp, mâu thuẫn và thiếu dữ liệu."
    )
    assert result["coverage_complete"] is False
    assert result["proxy_distinction_present"] is True
    assert result["conflict_handling_present"] is True
    assert result["missingness_awareness_present"] is True
    assert "gold" not in result


def test_counter_argument_is_not_scored_without_prompt_linkage() -> None:
    result = evaluate_text_response("Tôi tự phản biện lại kết luận.", turn="counter_argument")
    assert result["parsed_assessments"] == {}
    assert result["counter_prompt_linkage_available"] is False


def _valid_output() -> dict[str, object]:
    return {
        "classification": "Mixed",
        "confidence": "Medium",
        "positive_evidence": [{"feature": "payment_on_time_rate_12m", "value": 0.91}],
        "negative_evidence": [],
        "conflicts": [],
        "rules_used": ["RULE_PAY_001"],
        "unsupported_information": [],
        "missing_information": ["payment_semantics"],
        "reasoning_summary": "Payment behavior is positive but not fully defined as credit repayment.",
    }


def test_reasoning_schema_validates_features_and_rules() -> None:
    validate_reasoning_output(
        _valid_output(),
        known_features={"payment_on_time_rate_12m"},
        known_rule_ids={"RULE_PAY_001"},
    )

    bad = _valid_output()
    bad["rules_used"] = ["RULE_UNKNOWN"]
    with pytest.raises(ValueError, match="unknown rule"):
        validate_reasoning_output(bad, known_features={"payment_on_time_rate_12m"}, known_rule_ids={"RULE_PAY_001"})


def test_reasoning_schema_rejects_unknown_top_level_fields() -> None:
    bad = _valid_output()
    bad["hallucinated_field"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        validate_reasoning_output(bad)
