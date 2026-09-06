"""Transparent what-if profile simulation for the phase-one UI prototype."""

from __future__ import annotations

from typing import Any

OCCUPATION_STABILITY = {
    "Nhân viên văn phòng": 0.75,
    "Kinh doanh tự do": 0.50,
    "Công chức/viên chức": 0.85,
    "Lao động kỹ thuật": 0.65,
    "Sinh viên": 0.30,
    "Khác": 0.50,
}


def simulate_profile(
    *,
    age: int,
    income_million_vnd: float,
    occupation: str,
    employment_years: float,
    household_type: str,
    dependents: int,
    service_count: int,
    cic_score: int | None = None,
) -> dict[str, Any]:
    """Return a non-credit, explainable demo index and feature summary.

    CIC is displayed as an optional input only; it is deliberately not used in
    this phase-one index because no approved CIC target/model exists yet.
    """

    if not 18 <= age <= 100:
        raise ValueError("age must be between 18 and 100")
    if income_million_vnd < 0 or employment_years < 0 or dependents < 0 or service_count < 0:
        raise ValueError("income, employment years, dependents and services cannot be negative")
    if cic_score is not None and not 300 <= cic_score <= 900:
        raise ValueError("cic_score must be between 300 and 900 when supplied")

    age_component = max(0.0, 1.0 - abs(age - 40) / 60)
    income_component = min(income_million_vnd / 50.0, 1.0)
    tenure_component = min(employment_years / 10.0, 1.0)
    family_component = max(0.0, 1.0 - dependents / 6.0)
    service_component = min(service_count / 5.0, 1.0)
    occupation_component = OCCUPATION_STABILITY.get(occupation, OCCUPATION_STABILITY["Khác"])
    index = round(
        100
        * (
            0.15 * age_component
            + 0.25 * income_component
            + 0.20 * tenure_component
            + 0.15 * family_component
            + 0.10 * service_component
            + 0.15 * occupation_component
        ),
        1,
    )
    return {
        "demo_index": index,
        "cic_score": cic_score,
        "cic_used_in_model": False,
        "occupation_used_in_trained_model": False,
        "components": {
            "age": round(age_component * 100, 1),
            "income": round(income_component * 100, 1),
            "employment_tenure": round(tenure_component * 100, 1),
            "household_and_dependents": round(family_component * 100, 1),
            "service_engagement": round(service_component * 100, 1),
            "occupation_stability_assumption": round(occupation_component * 100, 1),
        },
        "note": "Chỉ là chỉ số minh họa; không phải CIC score, credit score hoặc quyết định cho vay.",
    }
