"""Validation and normalization for customer lead JSON uploads.

The lead contract is deliberately small and contains only fields used by the
phase-one profile simulation. It is not a credit application or a production
credit-scoring input contract.
"""

from __future__ import annotations

import json
from typing import Any

from credit_scoring.dc5.simulation import OCCUPATION_STABILITY, simulate_profile

LEAD_SCHEMA_VERSION = "dc5-lead-v1"
LEAD_FIELDS = (
    "age",
    "income_million_vnd",
    "occupation",
    "employment_years",
    "household_type",
    "dependents",
    "service_count",
    "cic_score",
)
REQUIRED_LEAD_FIELDS = LEAD_FIELDS[:-1]


def parse_lead_json(payload: str | bytes) -> dict[str, Any]:
    """Parse and validate one lead JSON object.

    Unknown fields and JSON arrays are rejected so an uploaded file cannot
    silently look valid while being ignored by the simulation.
    """

    try:
        value = json.loads(payload)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Lead phải là JSON hợp lệ (một object, không phải array).") from exc
    if not isinstance(value, dict):
        raise TypeError("Lead JSON phải là một object duy nhất.")
    return validate_lead(value)


def validate_lead(value: dict[str, Any]) -> dict[str, Any]:
    """Validate a decoded lead and return a stable, JSON-safe profile dict."""

    missing = [field for field in REQUIRED_LEAD_FIELDS if field not in value]
    if missing:
        raise ValueError(f"Thiếu trường bắt buộc: {', '.join(missing)}")
    unknown = sorted(set(value) - set(LEAD_FIELDS) - {"schema_version"})
    if unknown:
        raise ValueError(f"Trường không được hỗ trợ: {', '.join(unknown)}")
    if value.get("schema_version", LEAD_SCHEMA_VERSION) != LEAD_SCHEMA_VERSION:
        raise ValueError(f"schema_version phải là {LEAD_SCHEMA_VERSION}.")

    try:
        profile: dict[str, Any] = {
            "age": int(value["age"]),
            "income_million_vnd": float(value["income_million_vnd"]),
            "occupation": str(value["occupation"]),
            "employment_years": float(value["employment_years"]),
            "household_type": str(value["household_type"]),
            "dependents": int(value["dependents"]),
            "service_count": int(value["service_count"]),
            "cic_score": None if value.get("cic_score") in (None, "") else int(value["cic_score"]),
        }
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Các trường số của lead phải có kiểu số hợp lệ.") from exc

    if profile["occupation"] not in OCCUPATION_STABILITY:
        raise ValueError("occupation không nằm trong danh sách nghề nghiệp hỗ trợ.")
    # Reuse the simulation's range checks as the single source of truth.
    simulate_profile(**profile)
    return profile
