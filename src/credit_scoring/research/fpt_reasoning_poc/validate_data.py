"""CLI compatibility wrapper for shared pre-profile validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from credit_scoring.reasoning.ingestion import load_input
from credit_scoring.reasoning.mapping import load_feature_mapping
from credit_scoring.reasoning.validation import validate_frame
from credit_scoring.research.fpt_reasoning_poc.common import DEFAULT_WORKBOOK, PROCESSED_DIR


def validate_dataframe(frame):
    mapping = load_feature_mapping()
    return validate_frame(frame, mapping)


def run(
    source: str | Path = DEFAULT_WORKBOOK,
    *,
    sheet: str | None = None,
) -> tuple[object, dict]:
    frame, inspection = load_input(source, sheet=sheet)
    report = validate_dataframe(frame)
    report["inspection"] = inspection.to_dict()
    path = PROCESSED_DIR / "validation_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return frame, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate FPT reasoning raw input.")
    parser.add_argument("--input", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", default=None)
    args = parser.parse_args()
    _, report = run(args.input, sheet=args.sheet)
    print(json.dumps(report["summary"], ensure_ascii=False))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
