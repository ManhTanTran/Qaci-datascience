from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
RAW_DIR = ROOT / "data" / "raw" / "research" / "fpt_reasoning_poc"
PROCESSED_DIR = ROOT / "data" / "processed" / "research" / "fpt_reasoning_poc"
OUTPUT_DIR = ROOT / "outputs" / "research" / "fpt_reasoning_poc"
CONFIG_DIR = ROOT / "configs" / "research" / "fpt_reasoning_poc"
PROMPT_DIR = ROOT / "prompts" / "research" / "fpt_reasoning_poc"
TEST_DIR = ROOT / "tests" / "fixtures" / "research" / "fpt_reasoning_poc"


# Windows PowerShell may expose a legacy code page to Python. Keep CLI output
# readable without changing any machine-wide setting.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def ensure_directories() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "không có dữ liệu"}
    return False


def clean_scalar(value: Any) -> Any:
    if is_missing(value):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return value


def number_or_none(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float | int | None:
    if is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return int(number) if number.is_integer() else number


def status(value: Any) -> str:
    return "missing" if is_missing(value) else "available"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def nested_get(data: dict[str, Any], dotted_field: str) -> Any:
    current: Any = data
    for part in dotted_field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
