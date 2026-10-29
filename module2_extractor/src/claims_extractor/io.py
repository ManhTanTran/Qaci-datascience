"""Read the phase-1 hand-off file (`llm_answers`) from a single JSONL or JSON file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import AnswerRecord


def _load_items(path: Path) -> tuple[list[tuple[str, Any]], list[str]]:
    """Return [(label, raw_object)] plus problems found while splitting the file."""
    text = path.read_text(encoding="utf-8-sig")
    items: list[tuple[str, Any]] = []
    problems: list[str] = []

    if path.suffix.lower() == ".jsonl":
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue  # blank lines do occur in real hand-off files
            try:
                items.append((f"line {number}", json.loads(line)))
            except json.JSONDecodeError as exc:
                problems.append(f"line {number}: invalid JSON ({exc.msg})")
        return items, problems

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"{path.name}: invalid JSON ({exc.msg} at line {exc.lineno})"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [], [f"{path.name}: expected a JSON object or array"]
    return [(f"item {index}", obj) for index, obj in enumerate(data, start=1)], problems


def read_answers(path: str | Path) -> tuple[list[AnswerRecord], list[str]]:
    """Parse every answer in `path`. Bad entries are reported, never fatal."""
    items, problems = _load_items(Path(path))
    records: list[AnswerRecord] = []
    for label, obj in items:
        try:
            records.append(AnswerRecord.model_validate(obj))
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first["loc"])
            problems.append(f"{label}: {location}: {first['msg']}")
    return records, problems
