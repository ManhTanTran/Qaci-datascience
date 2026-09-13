"""Create research case records from profile output and workbook scenarios."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from credit_scoring.research.fpt_reasoning_poc.common import read_jsonl, write_jsonl
from credit_scoring.research.fpt_reasoning_poc.rule_engine import evaluate_profile
from credit_scoring.research.fpt_reasoning_poc.scenarios import load_scenario_definitions


def create(
    profiles_path: str | Path,
    *,
    workbook_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    profiles = read_jsonl(profiles_path)
    scenarios = (
        load_scenario_definitions(workbook_path) if workbook_path is not None else []
    )
    scenario_by_id = {str(item["id"]): item for item in scenarios}
    cases = []
    for profile in profiles:
        case_id = str(profile.get("user_id"))
        rule_result = evaluate_profile(profile)
        scenario = deepcopy(scenario_by_id.get(case_id, {}))
        cases.append(
            {
                "case_id": case_id,
                "profile": profile,
                "rule_result": rule_result,
                "scenario": scenario,
                "expected_missing": scenario.get("expected_missing", []),
                "must_not_infer": scenario.get("must_not_infer", []),
                "gold_status": "not_provided",
            }
        )
    if output_path is not None:
        write_jsonl(output_path, cases)
    return cases
