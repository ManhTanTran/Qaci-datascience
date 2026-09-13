"""Research import path for the shared deterministic rule engine."""

from credit_scoring.reasoning.rules import (
    FAIL,
    PASS,
    UNKNOWN,
    compare_age,
    evaluate_profile,
    evaluate_profile_rules,
    load_rules,
)

__all__ = [
    "FAIL",
    "PASS",
    "UNKNOWN",
    "compare_age",
    "evaluate_profile",
    "evaluate_profile_rules",
    "load_rules",
]
