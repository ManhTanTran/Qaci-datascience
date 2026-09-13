"""CLI-compatible wrapper around evidence-grounded research evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from credit_scoring.research.fpt_reasoning_poc.common import read_jsonl
from credit_scoring.research.fpt_reasoning_poc.evaluation import evaluate_research_results


def evaluate(
    records: list[dict],
    scenarios: list[dict] | None = None,
) -> dict:
    return evaluate_research_results(records, scenarios)


def main() -> None:
    parser = argparse.ArgumentParser(description="Đánh giá kết quả reasoning research.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(read_jsonl(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
