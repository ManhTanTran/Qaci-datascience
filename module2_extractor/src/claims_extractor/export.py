"""Flat exports of the claim store for people who prefer Excel/CSV or line-oriented JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .domain import Domain
from .store import ClaimStore


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return value


def export_csv(store: ClaimStore, domain: Domain, path: str | Path) -> int:
    """Write claims as UTF-8 CSV (with BOM so Excel shows Vietnamese correctly)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=domain.csv_columns, extrasaction="ignore")
        writer.writeheader()
        for claim in store.iter_claims(domain.name):
            writer.writerow({column: _cell(claim.get(column)) for column in domain.csv_columns})
            count += 1
    return count


def export_jsonl(store: ClaimStore, domain: Domain, path: str | Path) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for claim in store.iter_claims(domain.name):
            handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
            count += 1
    return count
