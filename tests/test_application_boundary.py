from __future__ import annotations

from credit_scoring.application.service import assess_user_profile


def test_user_application_does_not_use_research_pipeline() -> None:
    result = assess_user_profile(
        {
            "age": 35,
            "income_million_vnd": 15,
            "occupation": "Nhân viên văn phòng",
            "employment_years": 3,
            "household_type": "Chung cư",
            "dependents": 1,
            "service_count": 2,
            "cic_score": None,
        }
    )

    assert result["flow"] == "application"
    assert result["research_used"] is False
    assert result["human_review_required"] is True
