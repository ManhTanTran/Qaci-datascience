"""Load and normalize the alternative-data feature registry."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

MISSING_MARKERS = frozenset(
    {
        "",
        "null",
        "none",
        "nan",
        "n/a",
        "na",
        "không có",
        "không có dữ liệu",
    }
)


def load_feature_definitions_yaml(path: str | Path) -> tuple[dict[str, Any], ...]:
    """Load the machine-readable feature definitions and reject bad shape."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Loading YAML feature definitions requires PyYAML.") from exc
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("features"), list):
        raise TypeError("Feature registry must be an object with a features list.")
    records = tuple(document["features"])
    if not all(isinstance(record, Mapping) for record in records):
        raise TypeError("Every feature registry entry must be an object.")
    names = [str(record.get("name", "")) for record in records]
    if not all(names) or len(names) != len(set(names)):
        raise ValueError("Feature names must be non-empty and unique.")
    return tuple(dict(record) for record in records)


def normalize_customer_features(features: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize attachment-style keys and missing markers without touching zero."""

    normalized: dict[str, Any] = {}
    for raw_name, value in features.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise TypeError("Customer feature names must be non-empty strings.")
        name = raw_name.lstrip("\ufeff").strip()
        if name in normalized:
            raise ValueError(f"Duplicate customer feature after normalization: {name}.")
        if isinstance(value, str) and value.strip().lower() in MISSING_MARKERS:
            normalized[name] = None
        else:
            normalized[name] = value
    return normalized


def feature_registry_index(
    definitions: tuple[Mapping[str, Any], ...],
) -> dict[str, Mapping[str, Any]]:
    """Index registry records by feature name for detector and prompt builder."""

    index = {str(record["name"]): record for record in definitions}
    if len(index) != len(definitions):
        raise ValueError("Feature registry contains duplicate names.")
    return index
