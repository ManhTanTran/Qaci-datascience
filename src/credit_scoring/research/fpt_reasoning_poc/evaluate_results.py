from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from .common import CONFIG_DIR, OUTPUT_DIR, read_jsonl


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    schema = json.loads((CONFIG_DIR / "response_schema.json").read_text(encoding="utf-8"))
    scored: list[dict[str, Any]] = []
    by_case: dict[str, set[str]] = defaultdict(set)
    for record in records:
        response = record.get("response")
        schema_valid = False
        if response is not None:
            try:
                validate(instance=response, schema=schema)
                schema_valid = True
            except ValidationError:
                pass
        rule_correct = bool(response) and response.get("rule_result") == record.get("expected_rule_result")
        recommendation_correct = bool(response) and response.get("recommendation") == record.get("expected_recommendation")
        conflict_correct = bool(response) and response.get("conflict_detected") == record.get("expected_conflict")
        signature = json.dumps(response, ensure_ascii=False, sort_keys=True) if response else "ERROR"
        by_case[record["case_id"]].add(signature)
        scored.append({
            "case_id": record["case_id"],
            "repeat_index": record["repeat_index"],
            "schema_valid": schema_valid,
            "rule_correct": rule_correct,
            "recommendation_correct": recommendation_correct,
            "conflict_correct": conflict_correct,
            "has_error": record.get("error") is not None,
        })

    total = len(scored)
    ratio = lambda field: (sum(1 for row in scored if row[field]) / total) if total else 0.0
    return {
        "total_runs": total,
        "schema_valid_rate": ratio("schema_valid"),
        "rule_correct_rate": ratio("rule_correct"),
        "recommendation_correct_rate": ratio("recommendation_correct"),
        "conflict_correct_rate": ratio("conflict_correct"),
        "error_rate": ratio("has_error"),
        "exact_repeat_consistency_by_case": {case: len(signatures) == 1 for case, signatures in by_case.items()},
        "details": scored,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Chấm kết quả AI")
    parser.add_argument("--input", type=Path, default=OUTPUT_DIR / "experiment_results.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "evaluation_report.json")
    args = parser.parse_args()
    report = evaluate(read_jsonl(args.input))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

