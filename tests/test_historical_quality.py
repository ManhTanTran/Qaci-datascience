from wardprice.historical_quality import (
    MIN_TUKEY_GROUP_SIZE,
    robust_mad,
    tukey_iqr,
)


def test_tukey_group_outlier_flag_is_diagnostic_and_requires_ten_values():
    assert MIN_TUKEY_GROUP_SIZE == 10
    assert tukey_iqr([1.0] * 9) == {
        "sample_count": 9,
        "applied": False,
        "reason": "INSUFFICIENT_SAMPLE",
    }

    result = tukey_iqr([*map(float, range(9)), 100.0])

    assert result["applied"] is True
    assert result["flagged_count"] == 1
    assert result["method"] == "TUKEY_1_5_IQR_DIAGNOSTIC_ONLY"


def test_robust_mad_requires_sufficient_group_and_flags_without_deleting():
    assert robust_mad(list(range(29)))["applied"] is False

    result = robust_mad([*map(float, range(40)), 1000.0])

    assert result["applied"] is True
    assert result["flagged_count"] == 1
    assert result["method"] == "MODIFIED_Z_SCORE_MAD_DIAGNOSTIC_ONLY_N_GE_30"


def test_robust_mad_does_not_apply_when_mad_is_zero():
    result = robust_mad([100.0] * 30)

    assert result == {
        "sample_count": 30,
        "applied": False,
        "reason": "ZERO_MAD",
    }


def test_small_sample_quality_codes_are_not_statistical_outlier_flags():
    result = tukey_iqr([1.0, 1.1, 0.9])

    assert result["sample_count"] == 3
    assert result["applied"] is False
    assert result["reason"] == "INSUFFICIENT_SAMPLE"
