"""Validation that preserves the distinction between missing and invalid data."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

AVAILABLE = "available"
MISSING = "missing"
INVALID = "invalid"


def is_missing(value: Any) -> bool:
    """Return whether a scalar is absent without treating zero as absent."""

    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {
        "",
        "nan",
        "none",
        "null",
        "không có dữ liệu",
    }:
        return True
    try:
        missing = pd.isna(value)
        return bool(missing) if not hasattr(missing, "__len__") else False
    except (TypeError, ValueError):
        return False


def to_python(value: Any) -> Any:
    """Make pandas/numpy scalars JSON-compatible while preserving nulls."""

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
        except (TypeError, ValueError):
            pass
    return value


def _as_number(value: Any) -> float | None:
    if is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _column_rule(column: str) -> tuple[float, float] | None:
    """Return conservative checks for numeric behavioral columns only."""

    lower = column.lower()
    if "is_late_mean" in lower or "is_prepaid_mean" in lower:
        return 0.0, 1.0
    if "payment_month_count" in lower or "is_late_sum" in lower:
        return 0.0, 12.0
    if "late_day" in lower:
        return 0.0, 366.0
    if "_rate" in lower and "monthly" not in lower:
        return 0.0, 100.0
    if any(token in lower for token in ("_count", "_nunique", "_recency")):
        return 0.0, float("inf")
    return None


def _cell_status(value: Any, column: str, spec: Mapping[str, Any]) -> tuple[str, str | None]:
    if is_missing(value):
        return MISSING, "value_missing"
    if column in {"avg_monthly_income", "avg_monthly_spend"}:
        return INVALID, "unit_not_confirmed"
    rule = _column_rule(column)
    if rule is None:
        return AVAILABLE, None
    number = _as_number(value)
    if number is None:
        return INVALID, "expected_numeric_value"
    minimum, maximum = rule
    if number < minimum or number > maximum:
        return INVALID, f"outside_expected_range_{minimum:g}_{maximum:g}"
    return AVAILABLE, None


def validate_row_fields(
    row: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate one row at group/raw-column granularity."""

    result: dict[str, dict[str, Any]] = {}
    for group, spec in mapping["fields"].items():
        raw_statuses: dict[str, dict[str, Any]] = {}
        for column in spec["raw_columns"]:
            if column not in row:
                raw_statuses[column] = {"status": MISSING, "reason": "column_missing"}
                continue
            status, reason = _cell_status(row[column], column, spec)
            raw_statuses[column] = {
                "status": status,
                "reason": reason,
                "value": to_python(row[column]),
            }
        statuses = {item["status"] for item in raw_statuses.values()}
        if INVALID in statuses:
            field_status = INVALID
        elif AVAILABLE in statuses:
            field_status = AVAILABLE
        else:
            field_status = MISSING
        result[group] = {
            "status": field_status,
            "raw": raw_statuses,
            "warning": spec.get("validation_warning") if INVALID in statuses else None,
        }
    return result


def validate_frame(frame: pd.DataFrame, mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Validate structure and values before any profile or rule is built."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    fields = mapping["fields"]
    id_column = mapping.get("source", {}).get("id_column", "user_id")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing_columns: list[str] = []
    for group, spec in fields.items():
        for column in spec["raw_columns"]:
            if column not in frame.columns:
                missing_columns.append(column)
        if spec.get("required") and not any(
            column in frame.columns for column in spec["raw_columns"]
        ):
            errors.append({"type": "required_column_missing", "field": group})
    if id_column not in frame.columns:
        errors.append({"type": "missing_id_column", "column": id_column})
    else:
        if frame[id_column].isna().any():
            errors.append({"type": "missing_user_id", "column": id_column})
        if frame[id_column].duplicated().any():
            errors.append({"type": "duplicate_user_id", "column": id_column})

    row_fields: dict[str, dict[str, dict[str, Any]]] = {}
    missing_observations = 0
    invalid_observations = 0
    for index, row in frame.iterrows():
        validated = validate_row_fields(row.to_dict(), mapping)
        row_key = str(index)
        row_fields[row_key] = validated
        for group, details in validated.items():
            if details["status"] == MISSING:
                missing_observations += 1
            if details["status"] == INVALID:
                invalid_observations += sum(
                    item["status"] == INVALID for item in details["raw"].values()
                )
            for column, item in details["raw"].items():
                if item["reason"] == "unit_not_confirmed":
                    warnings.append(
                        {
                            "type": "unit_uncertain",
                            "row": int(index) if isinstance(index, int) else str(index),
                            "column": column,
                            "reason": "TODO(FPT): cần xác nhận với mentor hoặc data owner.",
                        }
                    )
                elif item["status"] == INVALID:
                    warnings.append(
                        {
                            "type": "invalid_value",
                            "row": int(index) if isinstance(index, int) else str(index),
                            "column": column,
                            "reason": item["reason"],
                        }
                    )

    if missing_columns:
        warnings.append(
            {
                "type": "declared_columns_missing",
                "columns": sorted(set(missing_columns)),
                "note": "Missing source columns are preserved as missing; they are not filled with zero.",
            }
        )
    return {
        "source": {
            "file": frame.attrs.get("source_file"),
            "sheet": frame.attrs.get("source_sheet"),
        },
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "errors": errors,
        "warnings": warnings,
        "missing_columns": sorted(set(missing_columns)),
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "missing": missing_observations,
            "invalid": invalid_observations,
        },
        "row_fields": row_fields,
        "valid_for_profile_build": not errors,
    }
