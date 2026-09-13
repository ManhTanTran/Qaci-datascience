"""Scenario definitions derived from the workbook's Scenario_Design sheet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _list_value(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in text.split(",")]
    return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]


def scenario_definitions_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert scenario metadata to structured definitions without passing labels to AI."""

    if "customer_id" not in frame.columns:
        raise ValueError("Scenario_Design must contain customer_id.")
    definitions = []
    for _, row in frame.iterrows():
        scenario_id = str(row["customer_id"])
        name = row.get("scenario_name", row.get("scenario_design", scenario_id))
        observable = row.get("observable_pattern", row.get("note", ""))
        reasoning_test = row.get("reasoning_test", "")
        scenario_text = f"{name} {observable} {reasoning_test}".lower()
        expected_missing = _list_value(row.get("expected_missing"))
        if not expected_missing and (
            "all behavioral" in scenario_text
            or "behavioral/transactional fields are missing" in scenario_text
            or "behavioral fields are missing" in scenario_text
        ):
            expected_missing = [
                "device_usage",
                "payment_history_12m",
                "shopping_installment",
                "orders",
                "healthcare_spending",
                "fpt_education",
            ]
        if not expected_missing and "no observed monetary/payment" in scenario_text:
            expected_missing = ["payment_history_12m"]
        must_not_infer = _list_value(row.get("must_not_infer"))
        if not must_not_infer and (
            "context" in scenario_text or "socioeconomic" in scenario_text
        ):
            must_not_infer = ["personal_income", "personal_spend", "repayment_capacity"]
        conflict_expected = row.get("should_detect_conflict")
        if pd.isna(conflict_expected) and any(
            token in scenario_text for token in ("tension", "lateness", "late-payment", "mixed profile")
        ):
            conflict_expected = True
        expected_negative = _list_value(row.get("strong_negative_evidence"))
        if not expected_negative and ("late" in scenario_text or "lateness" in scenario_text):
            expected_negative = ["payment_history_12m"]
        expected_positive = _list_value(row.get("weak_positive_evidence"))
        if not expected_positive and ("usage" in scenario_text or "engagement" in scenario_text):
            expected_positive = ["device_usage", "orders"]
        expected = {
            "rule_decision": row.get("expected_rule_decision"),
            "should_detect_conflict": conflict_expected,
        }
        expected = {key: value for key, value in expected.items() if pd.notna(value)}
        definitions.append(
            {
                "id": scenario_id,
                "description": str(name),
                "observable_pattern": str(observable),
                "reasoning_test": str(reasoning_test),
                "expected": expected,
                "must_not_infer": must_not_infer,
                "expected_missing": expected_missing,
                "strong_negative_evidence": expected_negative,
                "weak_positive_evidence": expected_positive,
                "source": {"sheet": "Scenario_Design", "row": int(row.name) + 2},
                "label_is_for_experiment_only": True,
            }
        )
    return definitions


def load_scenario_definitions(
    workbook_path: str | Path,
    *,
    sheet_name: str = "Scenario_Design",
) -> list[dict[str, Any]]:
    workbook = Path(workbook_path)
    frame = pd.read_excel(workbook, sheet_name=sheet_name)
    return scenario_definitions_from_frame(frame)


def load_scenarios_json(path: str | Path) -> list[dict[str, Any]]:
    import yaml

    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("scenarios", [])
    if not isinstance(payload, list):
        raise ValueError("Scenario configuration must be a list or contain scenarios.")
    return payload
