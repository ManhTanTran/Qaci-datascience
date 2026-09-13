"""Deterministic raw-to-business profile building with evidence lineage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.reasoning.mapping import BUSINESS_GROUPS, load_feature_mapping
from credit_scoring.reasoning.validation import (
    AVAILABLE,
    MISSING,
    INVALID,
    is_missing,
    to_python,
    validate_frame,
    validate_row_fields,
)


def parse_age_group(value: Any) -> dict[str, Any]:
    """Parse exact ages and age ranges without inventing a midpoint."""

    if is_missing(value):
        return {"exact": None, "group": None, "min": None, "max": None, "status": MISSING}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number.is_integer() and 0 <= number <= 120:
            exact = int(number)
            return {
                "exact": exact,
                "group": str(exact),
                "min": exact,
                "max": exact,
                "status": AVAILABLE,
            }
    text = str(value).strip()
    exact_match = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if exact_match:
        exact = float(exact_match.group(1))
        if exact.is_integer() and 0 <= exact <= 120:
            integer = int(exact)
            return {
                "exact": integer,
                "group": text,
                "min": integer,
                "max": integer,
                "status": AVAILABLE,
            }
    range_match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", text)
    if range_match:
        minimum, maximum = map(int, range_match.groups())
        if 0 <= minimum <= maximum <= 120:
            return {
                "exact": None,
                "group": text,
                "min": minimum,
                "max": maximum,
                "status": AVAILABLE,
            }
    plus_match = re.fullmatch(r">?\s*(\d+)\s*\+?", text)
    if plus_match:
        minimum = int(plus_match.group(1))
        if 0 <= minimum <= 120:
            return {
                "exact": None,
                "group": text,
                "min": minimum,
                "max": None,
                "status": AVAILABLE,
            }
    return {"exact": None, "group": text, "min": None, "max": None, "status": INVALID}


def _first_value(row: dict[str, Any], columns: list[str]) -> tuple[str | None, Any]:
    for column in columns:
        if column in row and not is_missing(row[column]):
            return column, row[column]
    return None, None


def _clean_values(raw_values: dict[str, Any]) -> dict[str, Any]:
    return {key: to_python(value) for key, value in raw_values.items()}


def build_local_context(raw_values: dict[str, Any]) -> dict[str, Any]:
    """Build regional context and explicitly keep personal values unknown."""

    values = _clean_values(raw_values)
    values["personal_income"] = None
    values["personal_spend"] = None
    return values


def build_payment_history_12m(raw_values: dict[str, Any]) -> dict[str, Any]:
    """Build payment aggregates without filling an unobserved total with zero."""

    values = _clean_values(raw_values)
    values.update(
        {
            "observed_months": values.get("payment_month_count_12M"),
            "late_months": values.get("is_late_sum_12M"),
            "late_rate": values.get("is_late_mean_12M"),
            "max_late_days": values.get("total_late_day_max_12M"),
            "total_paid_vnd": values.get("telco_monetary_sum_12M"),
            "average_paid_vnd": values.get("telco_monetary_mean_12M"),
        }
    )
    return values


def build_location(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


def build_device_usage(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


def build_shopping_installment(raw_values: dict[str, Any]) -> dict[str, Any]:
    values = _clean_values(raw_values)
    values.setdefault("installment_count_24m", None)
    values.setdefault("installment_late_count_24m", None)
    return values


def build_orders(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


def build_healthcare_spending(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


def build_fpt_education(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


def build_age_demographics(raw_values: dict[str, Any]) -> dict[str, Any]:
    return _clean_values(raw_values)


_TRANSFORMS = {
    "build_age_demographics": build_age_demographics,
    "build_local_context": build_local_context,
    "build_payment_history_12m": build_payment_history_12m,
    "build_location": build_location,
    "build_device_usage": build_device_usage,
    "build_shopping_installment": build_shopping_installment,
    "build_orders": build_orders,
    "build_healthcare_spending": build_healthcare_spending,
    "build_fpt_education": build_fpt_education,
}


def _derived_values(group: str, raw_values: dict[str, Any], transform: str) -> dict[str, Any]:
    del group
    builder = _TRANSFORMS.get(transform)
    return builder(raw_values) if builder is not None else _clean_values(raw_values)


def _build_evidence(
    group: str,
    spec: dict[str, Any],
    row: dict[str, Any],
    row_validation: dict[str, Any],
    *,
    source_file: str | None,
    source_sheet: str | None,
    source_row: int | str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for column in spec["raw_columns"]:
        item = row_validation["raw"][column]
        evidence.append(
            {
                "feature": group,
                "raw_column": column,
                "value": to_python(row.get(column)),
                "status": item["status"],
                "validation_warning": item.get("reason")
                if item.get("reason") not in {"value_missing", "column_missing"}
                else None,
                "transform": spec["transform"],
                "semantic_type": spec["semantic_type"],
                "trace": {
                    "file": source_file,
                    "sheet": source_sheet,
                    "source_row": source_row,
                    "user_id": to_python(row.get("user_id")),
                },
            }
        )
    return evidence


def build_profile(
    row: pd.Series | dict[str, Any],
    mapping: dict[str, Any] | None = None,
    *,
    source_file: str | None = None,
    source_sheet: str | None = None,
    source_row: int | str = 1,
    row_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one profile whose schema is fixed by the mapping configuration."""

    resolved_mapping = mapping or load_feature_mapping()
    raw_row = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    validation = row_validation or validate_row_fields(raw_row, resolved_mapping)
    profile: dict[str, Any] = {}
    all_evidence: list[dict[str, Any]] = []
    for group in BUSINESS_GROUPS:
        spec = resolved_mapping["fields"][group]
        group_validation = validation[group]
        raw_values = {column: raw_row.get(column) for column in spec["raw_columns"] if column in raw_row}
        values = _derived_values(group, raw_values, spec["transform"])
        evidence = _build_evidence(
            group,
            spec,
            raw_row,
            group_validation,
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=source_row,
        )
        all_evidence.extend(evidence)
        if group == "user_id":
            value: Any = to_python(raw_row.get("user_id"))
        elif group == "age":
            age_columns = [
                column
                for column in spec["raw_columns"]
                if not column.endswith("_ord")
            ]
            _, age_value = _first_value(raw_row, age_columns)
            value = parse_age_group(age_value)
        else:
            value = values
        present = [column for column in spec["raw_columns"] if column in raw_row]
        missing = [column for column in spec["raw_columns"] if column not in raw_row]
        payload: dict[str, Any] = {
            "value": value,
            "status": group_validation["status"],
            "raw_columns": present,
            "missing_raw_columns": missing,
            "transform": spec["transform"],
            "semantic_type": spec["semantic_type"],
            "description": spec["description"],
            "evidence": evidence,
            "field_status": {
                column: group_validation["raw"][column]["status"]
                for column in spec["raw_columns"]
            },
        }
        if group == "user_id":
            # Keep the identifier compatible with profile consumers and put
            # its lineage in the shared evidence_trace below.
            profile[group] = value
            continue
        elif group == "age":
            payload.update(value)
        else:
            # Keep the concise business fields accessible to table/UI clients;
            # ``value`` remains the canonical nested payload.
            payload.update(value)
        profile[group] = payload
    profile["_metadata"] = {
        "schema_version": resolved_mapping.get("version", "1.0"),
        "source": {
            "file": source_file,
            "sheet": source_sheet,
            "row": source_row,
            "user_id": to_python(raw_row.get("user_id")),
        },
    }
    profile["evidence_trace"] = all_evidence
    return profile


def build_profiles(
    frame: pd.DataFrame,
    mapping: dict[str, Any] | str | Path | None = None,
    *,
    validation_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build all profiles from a frame without selecting fields from observed data."""

    resolved_mapping = (
        load_feature_mapping(mapping) if isinstance(mapping, (str, Path)) else mapping
    ) or load_feature_mapping()
    report = validation_report or validate_frame(frame, resolved_mapping)
    source_file = frame.attrs.get("source_file")
    source_sheet = frame.attrs.get("source_sheet")
    profiles: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        row_validation = report.get("row_fields", {}).get(str(row.name))
        profiles.append(
            build_profile(
                row,
                resolved_mapping,
                source_file=source_file,
                source_sheet=source_sheet,
                source_row=position,
                row_validation=row_validation,
            )
        )
    identifiers = [profile.get("user_id") for profile in profiles]
    if len(profiles) != len(frame):
        raise RuntimeError("Profile build changed input cardinality.")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Profile grain requires unique user_id values.")
    return profiles


def flatten_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Create a human-readable, one-row representation for ``profiles.csv``."""

    flattened: dict[str, Any] = {"user_id": profile["user_id"]}
    for group in BUSINESS_GROUPS[1:]:
        payload = profile[group]
        flattened[f"{group}_status"] = payload["status"]
        flattened[f"{group}_semantic_type"] = payload["semantic_type"]
        value = payload.get("value")
        flattened[group] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return flattened


def profiles_to_dataframe(profiles: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([flatten_profile(profile) for profile in profiles])
