from __future__ import annotations

import pandas as pd

from credit_scoring.reasoning.ai import normalize_ai_response
from credit_scoring.reasoning.mapping import BUSINESS_GROUPS, load_feature_mapping, mapped_columns
from credit_scoring.reasoning.profiles import build_profile, build_profiles, parse_age_group
from credit_scoring.reasoning.rules import FAIL, PASS, UNKNOWN, evaluate_profile_rules
from credit_scoring.reasoning.validation import validate_frame
from credit_scoring.research.fpt_reasoning_poc.evaluation import evaluate_research_results
from credit_scoring.research.fpt_reasoning_poc.experiments import (
    RESEARCH_CONFIGURATIONS,
    ResearchExperimentConfig,
    run_research_experiment,
)
from credit_scoring.research.fpt_reasoning_poc.scenarios import scenario_definitions_from_frame


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "user_id": "customer_test",
        "age_group": "31-40",
        "avg_monthly_income": 12_000,
        "avg_monthly_spend": 5_000,
        "is_late_mean_12M": 0.0,
        "is_late_sum_12M": 0.0,
        "total_late_day_max_12M": 0.0,
        "payment_month_count_12M": 12.0,
        "telco_monetary_sum_12M": 1_000_000.0,
        "telco_monetary_mean_12M": 100_000.0,
        "healthcare_spend_6m": 400_000.0,
        "has_fpt_edu": 1,
        "fpt_edu_year": 2024,
    }
    row.update(overrides)
    return row


def test_mapping_declares_ten_stable_groups_and_workbook_columns() -> None:
    mapping = load_feature_mapping()
    assert tuple(mapping["fields"]) == BUSINESS_GROUPS
    assert len(mapped_columns(mapping)) == 199
    assert mapping["fields"]["payment_history_12m"]["transform"] == "build_payment_history_12m"


def test_validation_keeps_missing_and_invalid_distinct_from_zero() -> None:
    mapping = load_feature_mapping()
    frame = pd.DataFrame(
        [
            _row(payment_month_count_12M=None, is_late_sum_12M=-1),
            _row(payment_month_count_12M=0, is_late_sum_12M=0),
        ]
    )
    report = validate_frame(frame, mapping)
    first = report["row_fields"]["0"]["payment_history_12m"]["raw"]
    second = report["row_fields"]["1"]["payment_history_12m"]["raw"]
    assert first["payment_month_count_12M"]["status"] == "missing"
    assert first["is_late_sum_12M"]["status"] == "invalid"
    assert second["payment_month_count_12M"]["status"] == "available"
    assert report["summary"]["invalid"] > 0


def test_contextual_proxy_never_becomes_personal_income() -> None:
    profile = build_profile(pd.Series(_row()), load_feature_mapping())
    local = profile["local_context"]
    assert local["semantic_type"] == "contextual_proxy"
    assert local["personal_income"] is None
    assert local["value"]["personal_income"] is None
    income_evidence = next(
        item for item in local["evidence"] if item["raw_column"] == "avg_monthly_income"
    )
    assert income_evidence["validation_warning"] == "unit_not_confirmed"


def test_age_rule_preserves_exact_and_range_boundaries() -> None:
    assert parse_age_group("23")["exact"] == 23
    assert evaluate_profile_rules(build_profile(pd.Series(_row(age_group="23")), load_feature_mapping()))[
        "decision"
    ] == FAIL
    assert evaluate_profile_rules(build_profile(pd.Series(_row(age_group="23-30")), load_feature_mapping()))[
        "decision"
    ] == UNKNOWN
    assert evaluate_profile_rules(build_profile(pd.Series(_row(age_group="31-40")), load_feature_mapping()))[
        "decision"
    ] == PASS


def test_source_trace_and_profile_schema_are_fixed() -> None:
    mapping = load_feature_mapping()
    frame = pd.DataFrame([_row(user_id="a"), _row(user_id="b")])
    frame.attrs["source_file"] = "synthetic.xlsx"
    frame.attrs["source_sheet"] = "Synthetic_Customers"
    profiles = build_profiles(frame, mapping)
    assert len(profiles) == 2
    assert set(BUSINESS_GROUPS).issubset(profiles[0])
    trace = next(item for item in profiles[0]["evidence_trace"] if item["raw_column"] == "age_group")
    assert trace["trace"] == {
        "file": "synthetic.xlsx",
        "sheet": "Synthetic_Customers",
        "source_row": 2,
        "user_id": "a",
    }


def test_ai_explanation_cannot_mutate_authoritative_rule_result() -> None:
    rule_result = {"decision": PASS, "rule_id": "AGE_OVER_23_RESEARCH"}
    response = normalize_ai_response(
        {"explanation": "không đồng ý", "assessment": FAIL, "rule_conflict": False},
        rule_result,
    )
    assert response["rule_conflict"] is True
    assert rule_result["decision"] == PASS


def test_research_has_four_ablation_configs_and_configurable_repeats() -> None:
    mapping = load_feature_mapping()
    profiles = build_profiles(pd.DataFrame([_row(user_id="a"), _row(user_id="b")]), mapping)
    config = ResearchExperimentConfig(repeat_count=3, model="fake", configurations=tuple(RESEARCH_CONFIGURATIONS))
    results = run_research_experiment(profiles, config=config)
    assert set(RESEARCH_CONFIGURATIONS) == {
        "current",
        "current_healthcare",
        "current_fpt_education",
        "current_both",
    }
    assert len(results) == 2 * 4 * 3
    assert len({result["run_id"] for result in results}) == len(results)
    assert all(result["response"]["status"] == "not_run" for result in results)


def test_scenario_metadata_is_structured_and_metrics_without_gold_are_not_evaluable() -> None:
    scenarios = scenario_definitions_from_frame(
        pd.DataFrame(
            {
                "customer_id": ["a"],
                "scenario_name": ["Sparse local context"],
                "observable_pattern": ["Only area context is observed; behavioral fields are missing."],
                "reasoning_test": ["Do not infer payment capacity."],
            }
        )
    )
    assert scenarios[0]["must_not_infer"]
    assert "payment_history_12m" in scenarios[0]["expected_missing"]
    report = evaluate_research_results([], scenarios)
    assert all(metric["status"] == "not_evaluable" for metric in report["metrics"].values())
