from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from .common import CONFIG_DIR, OUTPUT_DIR, PROCESSED_DIR, nested_get, read_jsonl, write_jsonl

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"


def compare(value: Any, operator: str, expected: Any) -> str:
    if value is None:
        return UNKNOWN
    try:
        if operator == "gt":
            return PASS if value > expected else FAIL
        if operator == "gte":
            return PASS if value >= expected else FAIL
        if operator == "lt":
            return PASS if value < expected else FAIL
        if operator == "lte":
            return PASS if value <= expected else FAIL
        if operator == "eq":
            return PASS if value == expected else FAIL
    except TypeError:
        return UNKNOWN
    raise ValueError(f"Operator chưa hỗ trợ: {operator}")


def compare_age(age: dict[str, Any] | None, threshold: int) -> str:
    if not age:
        return UNKNOWN
    exact = age.get("exact")
    if exact is not None:
        return PASS if exact > threshold else FAIL
    minimum = age.get("min")
    maximum = age.get("max")
    if minimum is not None and minimum > threshold:
        return PASS
    if maximum is not None and maximum <= threshold:
        return FAIL
    return UNKNOWN


def evaluate_condition(profile: dict[str, Any], condition: dict[str, Any]) -> str:
    value = nested_get(profile, condition["field"])
    operator = condition["operator"]
    if operator == "age_gt":
        return compare_age(value, int(condition["value"]))
    return compare(value, operator, condition["value"])


def evaluate_rule(profile: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    conditions = rule.get("all") or [rule]
    results = [evaluate_condition(profile, condition) for condition in conditions]
    if FAIL in results:
        outcome = FAIL
    elif UNKNOWN in results:
        outcome = UNKNOWN
    else:
        outcome = PASS
    return {
        "rule_id": rule["id"],
        "type": rule["type"],
        "description": rule["description"],
        "outcome": outcome,
        "condition_results": results,
    }


def evaluate_profile(profile: dict[str, Any], rules_config: dict[str, Any]) -> dict[str, Any]:
    details = [evaluate_rule(profile, rule) for rule in rules_config["rules"]]
    hard = [item for item in details if item["type"] == "hard"]
    if any(item["outcome"] == FAIL for item in hard):
        decision = "NOT_ELIGIBLE"
        recommendation = "REJECT_BY_RULE"
    elif any(item["outcome"] == UNKNOWN for item in hard):
        decision = "MANUAL_REVIEW"
        recommendation = "MANUAL_REVIEW"
    else:
        decision = "ELIGIBLE"
        recommendation = "CONSIDER"
    return {
        "user_id": profile["user_id"],
        "decision": decision,
        "recommendation": recommendation,
        "rules": details,
    }


def load_rules(path: Path = CONFIG_DIR / "rules.yaml") -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run(input_path: Path, output_path: Path) -> list[dict[str, Any]]:
    profiles = read_jsonl(input_path)
    rules = load_rules()
    results = [evaluate_profile(profile.get("profile", profile), rules) for profile in profiles]
    write_jsonl(output_path, results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy rule engine trên profile JSONL")
    parser.add_argument("--input", type=Path, default=PROCESSED_DIR / "profiles.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "rule_results.jsonl")
    args = parser.parse_args()
    results = run(args.input, args.output)
    print(f"Đã chạy rule cho {len(results)} profile: {args.output}")


if __name__ == "__main__":
    main()

