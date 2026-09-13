"""Convenience pipeline for the shared data path plus research metadata."""

from __future__ import annotations

from pathlib import Path

from credit_scoring.reasoning.pipeline import FPTPipelineResult, run_fpt_pipeline
from credit_scoring.research.fpt_reasoning_poc.common import (
    DEFAULT_WORKBOOK,
    PROCESSED_DIR,
    write_jsonl,
)
from credit_scoring.research.fpt_reasoning_poc.create_test_cases import create
from credit_scoring.research.fpt_reasoning_poc.scenarios import load_scenario_definitions


def run(
    input_path: str | Path = DEFAULT_WORKBOOK,
    *,
    processed_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> tuple[FPTPipelineResult, list[dict]]:
    result = run_fpt_pipeline(
        input_path,
        processed_dir=processed_dir,
        output_dir=output_dir,
    )
    scenarios = load_scenario_definitions(input_path)
    processed = Path(processed_dir) if processed_dir is not None else PROCESSED_DIR
    write_jsonl(processed / "scenario_definitions.jsonl", scenarios)
    create(
        result.artifact_paths["profiles_jsonl"],
        workbook_path=input_path,
        output_path=processed / "cases.jsonl",
    )
    return result, scenarios


def main() -> None:
    result, scenarios = run()
    print(
        f"Hoàn tất pipeline: {len(result.profiles)} profiles, "
        f"{len(result.rule_results)} rule results, {len(scenarios)} scenarios."
    )


if __name__ == "__main__":
    main()
