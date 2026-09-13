"""Compatibility entry point for the reusable shared profile builder."""

from credit_scoring.reasoning.profiles import (
    build_profile,
    build_profiles,
    flatten_profile,
    parse_age_group,
    profiles_to_dataframe,
)
from credit_scoring.reasoning.mapping import load_feature_mapping
from credit_scoring.reasoning.validation import validate_frame
from credit_scoring.research.fpt_reasoning_poc.common import PROCESSED_DIR, write_jsonl

__all__ = [
    "build_profile",
    "build_profiles",
    "flatten_profile",
    "parse_age_group",
    "profiles_to_dataframe",
]


def build(frame):
    """Legacy convenience wrapper; core logic remains in ``credit_scoring.reasoning``."""

    mapping = load_feature_mapping()
    report = validate_frame(frame, mapping)
    profiles = build_profiles(frame, mapping, validation_report=report)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    profiles_to_dataframe(profiles).to_csv(
        PROCESSED_DIR / "profiles.csv", index=False, encoding="utf-8-sig"
    )
    write_jsonl(PROCESSED_DIR / "profiles.jsonl", profiles)
    return profiles


__all__.append("build")
