"""Read newly arrived answers from the hand-off file into the store (as `pending`).

Rules (code_plan.md §1, §7):
- only newline-terminated lines are trusted; a half-written last line waits for the next scan;
- a checkpoint (byte offset) is saved in the same transaction as the rows it covers;
- bad lines are logged to `input_errors`, never fatal;
- if the file shrank or its head changed (someone rewrote it), rescan from 0 — answer_id
  de-duplication makes a rescan harmless.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .models import AnswerRecord
from .store import ClaimStore

_HEAD_BYTES = 4096


@dataclass
class IngestResult:
    registered: int = 0
    duplicates: int = 0
    invalid: int = 0
    waiting_bytes: int = 0  # bytes of an unfinished last line (kept for the next scan)
    file_missing: bool = False
    unchanged: bool = False


def _head_hash(path: Path, upto: int) -> str:
    with path.open("rb") as handle:
        return hashlib.sha256(handle.read(min(upto, _HEAD_BYTES))).hexdigest()


def _validate(obj: object, position: int, errors: list, records: list) -> None:
    try:
        records.append(AnswerRecord.model_validate(obj))
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"]) or "record"
        snippet = json.dumps(obj, ensure_ascii=False)[:200] if isinstance(obj, (dict, list)) else str(obj)
        errors.append((position, f"{loc}: {first['msg']}", snippet))


def ingest_file(store: ClaimStore, path: str | Path, *, rescan: bool = False) -> IngestResult:
    path = Path(path)
    key = str(path)
    result = IngestResult()
    if not path.is_file():
        result.file_missing = True
        return result
    stat = path.stat()
    state = store.get_ingest_state(key)
    if path.suffix.lower() == ".json":
        return _ingest_json(store, path, key, stat, state, rescan, result)

    offset = 0 if (rescan or not state) else state["byte_offset"]
    if state and not rescan:
        if stat.st_size < offset or (offset and _head_hash(path, offset) != state["head_hash"]):
            offset = 0  # file was replaced or truncated
    if offset and stat.st_size == offset and not rescan:
        result.unchanged = True
        return result

    with path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read()
    end = chunk.rfind(b"\n") + 1  # 0 when there is no complete line yet
    complete, tail = chunk[:end], chunk[end:]
    result.waiting_bytes = len(tail)

    records: list[AnswerRecord] = []
    errors: list[tuple[int, str, str]] = []
    position = offset
    for raw in complete.split(b"\n")[:-1]:
        line_start, position = position, position + len(raw) + 1
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            reason = exc.msg if isinstance(exc, json.JSONDecodeError) else "not valid UTF-8"
            errors.append((line_start, f"invalid JSON ({reason})", raw[:200].decode("utf-8", "replace")))
            continue
        _validate(obj, line_start, errors, records)

    new_offset = offset + len(complete)
    result.registered, result.duplicates = store.register_batch(
        records, key, errors=errors,
        checkpoint={
            "byte_offset": new_offset, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "head_hash": _head_hash(path, new_offset) if new_offset else None,
        },
    )
    result.invalid = len(errors)
    return result


def _ingest_json(store, path, key, stat, state, rescan, result) -> IngestResult:
    if (state and not rescan and state["size"] == stat.st_size
            and state["mtime_ns"] == stat.st_mtime_ns):
        result.unchanged = True
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        result.waiting_bytes = stat.st_size  # probably still being written: retry next scan
        return result
    if isinstance(data, dict):
        data = [data]
    records: list[AnswerRecord] = []
    errors: list[tuple[int, str, str]] = []
    if not isinstance(data, list):
        errors.append((0, "expected a JSON object or array", ""))
    else:
        for index, obj in enumerate(data):
            _validate(obj, index, errors, records)
    result.registered, result.duplicates = store.register_batch(
        records, key, errors=errors,
        checkpoint={"byte_offset": 0, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
    )
    result.invalid = len(errors)
    return result
