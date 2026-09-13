"""Load and validate the raw-to-business mapping contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

BUSINESS_GROUPS = (
    "user_id",
    "age",
    "local_context",
    "location",
    "device_usage",
    "payment_history_12m",
    "shopping_installment",
    "orders",
    "healthcare_spending",
    "fpt_education",
)
REQUIRED_FIELD_KEYS = ("raw_columns", "transform", "required", "semantic_type", "description")


def default_mapping_path() -> Path:
    """Return the repository mapping path without depending on the cwd."""

    return Path(__file__).resolve().parents[3] / "configs" / "research" / "fpt_reasoning_poc" / "feature_mapping.yaml"


def load_feature_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Read the mapping and fail early on schema drift.

    The mapping is the source of truth for business groups; observed data never
    changes the declared output schema.
    """

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("Feature mapping requires PyYAML.") from exc
    mapping_path = Path(path) if path is not None else default_mapping_path()
    document = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("fields"), Mapping):
        raise ValueError("Feature mapping must contain a fields object.")
    fields = document["fields"]
    missing_groups = [group for group in BUSINESS_GROUPS if group not in fields]
    extra_groups = sorted(set(fields).difference(BUSINESS_GROUPS))
    if missing_groups or extra_groups:
        raise ValueError(
            f"Feature mapping groups differ from the contract; missing={missing_groups}, "
            f"extra={extra_groups}."
        )
    for group in BUSINESS_GROUPS:
        spec = fields[group]
        if not isinstance(spec, Mapping):
            raise TypeError(f"Mapping for {group} must be an object.")
        missing_keys = [key for key in REQUIRED_FIELD_KEYS if key not in spec]
        if missing_keys:
            raise ValueError(f"Mapping for {group} misses keys: {missing_keys}.")
        if not isinstance(spec["raw_columns"], list) or not all(
            isinstance(column, str) and column for column in spec["raw_columns"]
        ):
            raise ValueError(f"Mapping raw_columns for {group} must be a non-empty string list.")
        if not isinstance(spec["required"], bool):
            raise TypeError(f"Mapping required flag for {group} must be boolean.")
    return {**document, "fields": {group: dict(fields[group]) for group in BUSINESS_GROUPS}}


def mapped_columns(mapping: Mapping[str, Any]) -> tuple[str, ...]:
    """Return unique declared raw columns in declaration order."""

    seen: set[str] = set()
    columns: list[str] = []
    for group in BUSINESS_GROUPS:
        for column in mapping["fields"][group]["raw_columns"]:
            if column not in seen:
                seen.add(column)
                columns.append(column)
    return tuple(columns)
