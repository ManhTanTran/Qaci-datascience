from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from credit_scoring.features.home_credit_aggregation import (
    Aggregation,
    AggregationResult,
    aggregate,
    assert_unique_key,
    count_true_episodes,
    fill_counts,
    linear_trend_slope,
    longest_true_streak,
    merge_features,
    one_hot_counts,
    sanitize_feature_names,
    sum_observed,
)


def test_sum_observed_keeps_missing_distinct_from_zero() -> None:
    assert np.isnan(sum_observed(pd.Series([np.nan, np.nan])))
    assert sum_observed(pd.Series([0.0, np.nan])) == 0.0
    assert sum_observed(pd.Series([1.5, np.nan, 2.5])) == 4.0


def test_aggregate_distinguishes_sum_from_sum_observed() -> None:
    frame = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2, 2],
            "AMOUNT": [np.nan, np.nan, 10.0, np.nan],
            "FLAG": [0, 0, 1, 0],
        }
    )
    result = aggregate(
        frame,
        "SK_ID_CURR",
        (
            Aggregation("AMOUNT", ("sum_observed", "mean"), "amounts"),
            Aggregation("FLAG", ("sum",), "counts"),
        ),
    )
    values = result.frame.set_index("SK_ID_CURR")

    # A client with nothing observed must not be reported as owing zero.
    assert np.isnan(values.loc[1, "AMOUNT_SUM"])
    assert np.isnan(values.loc[1, "AMOUNT_MEAN"])
    assert values.loc[2, "AMOUNT_SUM"] == 10.0
    # Indicator flags are genuinely zero when no row is set.
    assert values.loc[1, "FLAG_SUM"] == 0


def test_aggregate_names_columns_from_the_specification() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": [1, 1], "DPD": [3.0, 5.0]})
    result = aggregate(
        frame,
        "SK_ID_CURR",
        (Aggregation("DPD", ("mean", "max"), "delinquency", name="LATE"),),
        prefix="INST_",
    )

    assert list(result.frame.columns) == ["SK_ID_CURR", "INST_LATE_MEAN", "INST_LATE_MAX"]
    assert result.families == {
        "INST_LATE_MEAN": "delinquency",
        "INST_LATE_MAX": "delinquency",
    }


def test_aggregate_rejects_missing_source_column() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": [1]})
    with pytest.raises(ValueError, match="Missing source columns"):
        aggregate(frame, "SK_ID_CURR", (Aggregation("ABSENT", ("mean",), "amounts"),))


def test_aggregate_rejects_duplicate_output_names() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": [1], "DPD": [1.0]})
    specs = (
        Aggregation("DPD", ("mean",), "delinquency"),
        Aggregation("DPD", ("mean",), "amounts"),
    )
    with pytest.raises(ValueError, match="Duplicate aggregation output name"):
        aggregate(frame, "SK_ID_CURR", specs)


def test_one_hot_counts_schema_does_not_depend_on_the_data() -> None:
    categories = ("Credit card", "Car loan")
    full = pd.DataFrame(
        {"SK_ID_CURR": [1, 1, 2], "CREDIT_TYPE": ["Credit card", "Car loan", "Mortgage"]}
    )
    partial = pd.DataFrame({"SK_ID_CURR": [3], "CREDIT_TYPE": ["Credit card"]})

    full_result = one_hot_counts(
        full, "CREDIT_TYPE", categories=categories,
        group_column="SK_ID_CURR", prefix="BUREAU_CTYPE_", family="counts",
    )
    partial_result = one_hot_counts(
        partial, "CREDIT_TYPE", categories=categories,
        group_column="SK_ID_CURR", prefix="BUREAU_CTYPE_", family="counts",
    )

    assert list(full_result.frame.columns) == list(partial_result.frame.columns)
    values = full_result.frame.set_index("SK_ID_CURR")
    assert values.loc[1, "BUREAU_CTYPE_Credit card_COUNT"] == 1
    # Undeclared categories are pooled rather than silently dropped.
    assert values.loc[2, "BUREAU_CTYPE_OTHER_COUNT"] == 1


def test_one_hot_counts_produces_lightgbm_safe_names() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": [1], "SUITE": ["Spouse, partner"]})
    result = one_hot_counts(
        frame, "SUITE", categories=("Spouse, partner",),
        group_column="SK_ID_CURR", prefix="PREV_SUITE_", family="counts",
    )

    assert "PREV_SUITE_Spouse_ partner_COUNT" in result.frame.columns
    assert all("," not in column for column in result.frame.columns)


def test_sanitize_feature_names_replaces_every_unsafe_character() -> None:
    assert sanitize_feature_names(["a,b", 'c"d', "e[f]"]) == ["a_b", "c_d", "e_f_"]


def test_merge_features_rejects_overlapping_names() -> None:
    left = AggregationResult(
        frame=pd.DataFrame({"SK_ID_CURR": [1], "A": [1]}), families={"A": "counts"}
    )
    right = AggregationResult(
        frame=pd.DataFrame({"SK_ID_CURR": [1], "A": [2]}), families={"A": "amounts"}
    )
    with pytest.raises(ValueError, match="Overlapping feature names"):
        merge_features(left, right, on="SK_ID_CURR")


def test_fill_counts_only_touches_named_columns() -> None:
    result = AggregationResult(
        frame=pd.DataFrame(
            {"SK_ID_CURR": [1, 2], "N_COUNT": [1.0, np.nan], "AMOUNT": [1.0, np.nan]}
        ),
        families={"N_COUNT": "counts", "AMOUNT": "amounts"},
    )
    filled = fill_counts(result, ["N_COUNT"])

    assert filled.frame["N_COUNT"].tolist() == [1, 0]
    assert filled.frame["AMOUNT"].isna().tolist() == [False, True]


def test_fill_counts_rejects_unknown_column() -> None:
    result = AggregationResult(frame=pd.DataFrame({"SK_ID_CURR": [1]}), families={})
    with pytest.raises(ValueError, match="unknown count column"):
        fill_counts(result, ["ABSENT"])


def test_longest_true_streak_and_episode_count() -> None:
    flags = pd.Series([0, 1, 1, 0, 1, 0, 1, 1, 1])
    assert longest_true_streak(flags) == 3
    assert count_true_episodes(flags) == 3

    empty = pd.Series([], dtype="int8")
    assert longest_true_streak(empty) == 0
    assert count_true_episodes(empty) == 0
    assert longest_true_streak(pd.Series([0, 0])) == 0


def test_linear_trend_slope_sign_follows_caller_ordering() -> None:
    increasing = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert linear_trend_slope(increasing) == pytest.approx(1.0)
    assert linear_trend_slope(increasing[::-1]) == pytest.approx(-1.0)
    assert linear_trend_slope(pd.Series([5.0, 5.0])) == 0.0
    assert np.isnan(linear_trend_slope(pd.Series([1.0])))
    assert np.isnan(linear_trend_slope(pd.Series([np.nan, 1.0])))


def test_assert_unique_key_reports_duplicates() -> None:
    assert_unique_key(pd.DataFrame({"SK_ID_CURR": [1, 2]}), "SK_ID_CURR", "ctx")
    with pytest.raises(ValueError, match="1 duplicate values"):
        assert_unique_key(pd.DataFrame({"SK_ID_CURR": [1, 1]}), "SK_ID_CURR", "ctx")
    with pytest.raises(ValueError, match="missing key column"):
        assert_unique_key(pd.DataFrame({"OTHER": [1]}), "SK_ID_CURR", "ctx")
