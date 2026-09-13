"""Evidence-grounded research metrics with explicit not-evaluable states."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from credit_scoring.research.fpt_reasoning_poc.experiments import duplicate_run_identities


def _ratio(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def evaluate_research_results(
    results: list[dict[str, Any]],
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scenarios_by_id = {str(item["id"]): item for item in (scenarios or [])}
    completed = [
        item for item in results if (item.get("response") or {}).get("status") == "available"
    ]
    details: list[dict[str, Any]] = []
    missing_scores: list[bool] = []
    unsupported_scores: list[bool] = []
    conflict_scores: list[bool] = []
    agreement_scores: list[bool] = []
    signatures: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for result in results:
        response = result.get("response") or {}
        scenario = scenarios_by_id.get(str(result.get("case_id")), {})
        expected = scenario.get("expected", {})
        missing_gold = scenario.get("expected_missing", [])
        forbidden_gold = scenario.get("must_not_infer", [])
        expected_conflict = expected.get("should_detect_conflict")
        observed_missing = set(response.get("missing_data", []))
        observed_unsupported = set(response.get("unsupported_inferences", []))
        response_available = response.get("status") == "available"
        if response_available:
            if expected.get("rule_decision") is not None and response.get("assessment") is not None:
                agreement_scores.append(
                    str(response["assessment"]).upper() == str(expected["rule_decision"]).upper()
                )
            if missing_gold:
                missing_scores.append(set(missing_gold).issubset(observed_missing))
            if forbidden_gold:
                unsupported_scores.append(not observed_unsupported.intersection(forbidden_gold))
            if expected_conflict is not None:
                conflict_scores.append(bool(response.get("rule_conflict")) == bool(expected_conflict))
            signature = json.dumps(response, ensure_ascii=False, sort_keys=True, default=str)
            signatures[(str(result.get("case_id")), str(result.get("configuration")))].append(signature)
        details.append(
            {
                "run_id": result.get("run_id"),
                "case_id": result.get("case_id"),
                "configuration": result.get("configuration"),
                "response_available": response_available,
            }
        )
    stability = [len(set(values)) == 1 for values in signatures.values() if len(values) > 1]
    duplicate_identities = duplicate_run_identities(results)
    metrics = {
        "rule_agreement": {
            "status": "evaluable" if agreement_scores else "not_evaluable",
            "value": _ratio(agreement_scores),
        },
        "conflict_detection": {
            "status": "evaluable" if conflict_scores else "not_evaluable",
            "value": _ratio(conflict_scores),
        },
        "missing_data_awareness": {
            "status": "evaluable" if missing_scores else "not_evaluable",
            "value": _ratio(missing_scores),
        },
        "unsupported_inference": {
            "status": "evaluable" if unsupported_scores else "not_evaluable",
            "value": _ratio(unsupported_scores),
        },
        "evidence_grounding": {
            "status": "not_evaluable",
            "value": None,
            "note": "Requires a reviewed evidence gold set; no proxy score is invented.",
        },
        "response_stability": {
            "status": "evaluable" if stability else "not_evaluable",
            "value": _ratio(stability),
        },
    }
    return {
        "total_runs": len(results),
        "completed_runs": len(completed),
        "duplicate_run_identities": {
            "status": "warning" if duplicate_identities else "none",
            "duplicates": {
                "|".join(str(item) for item in identity): count
                for identity, count in duplicate_identities.items()
            },
        },
        "metrics": metrics,
        "details": details,
    }
