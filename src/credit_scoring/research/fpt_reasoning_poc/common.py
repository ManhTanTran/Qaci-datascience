"""Paths and JSONL helpers for the research layer."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "research" / "fpt_reasoning_poc"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "research" / "fpt_reasoning_poc"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "research" / "fpt_reasoning_poc"
CONFIG_DIR = PROJECT_ROOT / "configs" / "research" / "fpt_reasoning_poc"
DEFAULT_WORKBOOK = RAW_DIR / "FPT_credit_scoring_synthetic_10_cases.xlsx"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
