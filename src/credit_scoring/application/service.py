"""Boundary for the user-facing profile application flow.

This module intentionally uses the approved application profile contract and
simulation only. It does not read synthetic research cases, experiment output,
or research model artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from credit_scoring.dc5.lead import validate_lead
from credit_scoring.dc5.simulation import simulate_profile


def assess_user_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one user-facing profile and return the application result."""

    validated = validate_lead(dict(profile))
    result = simulate_profile(**validated)
    return {
        "flow": "application",
        "profile": validated,
        "result": result,
        "research_used": False,
        "human_review_required": True,
        "disclaimer": (
            "Đây là kết quả mô phỏng hồ sơ ứng dụng, không phải credit score "
            "hoặc quyết định phê duyệt/từ chối."
        ),
    }
