"""Run the alternative-data harness from an external feature JSON object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from credit_scoring.reasoning.feature_registry import (
    feature_registry_index,
    load_feature_definitions_yaml,
)
from credit_scoring.reasoning.harness import run_reasoning_harness
from credit_scoring.reasoning.llm_client import create_reasoner_from_environment
from credit_scoring.reasoning.rules import load_rules_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="External JSON object containing customer features")
    parser.add_argument("--use-llm", action="store_true", help="Call the configured structured LLM provider")
    parser.add_argument("--print-prompt", action="store_true", help="Include the generated prompt in output")
    args = parser.parse_args()

    root = Path(__file__).parents[1]
    features = feature_registry_index(
        load_feature_definitions_yaml(root / "configs/reasoning/feature_definitions.yaml")
    )
    rules = load_rules_yaml(root / "configs/reasoning/rules.yaml", known_features=features)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Input JSON must be an object of customer features.")
    reasoner = create_reasoner_from_environment() if args.use_llm else None
    if args.use_llm and reasoner is None:
        parser.error("No reasoning LLM API key is configured.")
    result = run_reasoning_harness(payload, feature_index=features, rules=rules, reasoner=reasoner)
    response = {
        "detected_domains": result.detected.domains,
        "observed_features": result.detected.observed_features,
        "missing_features": result.detected.missing_features,
        "unknown_features": result.detected.unknown_features,
        "retrieved_rule_ids": [rule.id for rule in result.retrieved_rules],
        "llm_called": result.llm_called,
        "output": result.output,
    }
    if args.print_prompt:
        response["prompt"] = result.prompt
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
