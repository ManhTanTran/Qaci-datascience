"""Research features from ``previous_application`` at ``SK_ID_CURR`` grain.

Ported from the team's standalone pipeline. Amount totals use ``SUM_OBSERVED``,
contract and yield categories come from declared lists, and the requested-amount
trend is computed oldest-first so a positive slope means the client has been
asking for progressively larger loans over time. The original sorted
most-recent-first, which silently inverted that sign.

These are research candidates, not production features.
"""

from __future__ import annotations

import pandas as pd

from credit_scoring.features.home_credit_aggregation import (
    Aggregation,
    AggregationResult,
    aggregate,
    assert_unique_key,
    fill_counts,
    linear_trend_slope,
    merge_features,
    one_hot_counts,
)
from credit_scoring.numeric import safe_divide

KEY_COLUMN = "SK_ID_CURR"
CONTRACT_KEY = "SK_ID_PREV"
BUILDER_VERSION = "previous-application-v1"

CONTRACT_TYPES: tuple[str, ...] = ("Cash loans", "Consumer loans", "Revolving loans", "XNA")
YIELD_GROUPS: tuple[str, ...] = ("low_action", "low_normal", "middle", "high", "XNA")

#: Window used for the "recently refused" indicator, in days before application.
RECENT_REFUSAL_DAYS = 365
#: Number of most recent applications entering the requested-amount trend.
TREND_APPLICATIONS = 5

_AGGREGATIONS = (
    Aggregation(CONTRACT_KEY, ("count",), "counts", name="APPLICATION"),
    Aggregation("IS_APPROVED", ("sum", "mean"), "counts", name="APPROVED"),
    Aggregation("IS_REFUSED", ("sum", "mean"), "counts", name="REFUSED"),
    Aggregation("IS_CANCELLED", ("sum", "mean"), "counts", name="CANCELLED"),
    Aggregation("AMT_CREDIT", ("sum_observed", "mean", "max"), "amounts"),
    Aggregation("AMT_APPLICATION", ("mean", "max"), "amounts"),
    Aggregation("AMT_ANNUITY", ("mean", "max"), "amounts"),
    Aggregation("AMT_DIFF_APPLICATION_CREDIT", ("mean", "max", "min"), "amounts"),
    Aggregation("DOWN_PAYMENT_RATIO", ("mean", "max"), "amounts"),
    Aggregation("RATE_DOWN_PAYMENT", ("mean", "max"), "amounts"),
    Aggregation("LOAN_TO_PRICE", ("mean", "max"), "amounts"),
    Aggregation("DAYS_DECISION", ("max", "min", "mean"), "recency"),
    Aggregation("CNT_PAYMENT", ("mean", "max"), "counts"),
)

_APPROVED_AGGREGATIONS = (
    Aggregation("AMT_CREDIT", ("max", "mean"), "amounts", name="HIST_CREDIT"),
    Aggregation("AMT_ANNUITY", ("max",), "amounts", name="HIST_ANNUITY"),
)

_ZERO_FILLED_COUNTS = ("PREV_RECENT_REFUSAL_COUNT",)


def _add_row_features(prev: pd.DataFrame) -> pd.DataFrame:
    frame = prev.copy()
    status = frame["NAME_CONTRACT_STATUS"]
    frame["IS_APPROVED"] = (status == "Approved").astype("int8")
    frame["IS_REFUSED"] = (status == "Refused").astype("int8")
    frame["IS_CANCELLED"] = (status == "Canceled").astype("int8")
    frame["AMT_DIFF_APPLICATION_CREDIT"] = (
        frame["AMT_APPLICATION"] - frame["AMT_CREDIT"]
    ).astype("float32")
    frame["DOWN_PAYMENT_RATIO"] = safe_divide(
        frame["AMT_DOWN_PAYMENT"], frame["AMT_GOODS_PRICE"]
    )
    frame["LOAN_TO_PRICE"] = safe_divide(frame["AMT_CREDIT"], frame["AMT_GOODS_PRICE"])
    return frame


def _requested_amount_trend(frame: pd.DataFrame) -> pd.DataFrame:
    """Slope of requested amount across the most recent applications."""

    recent = (
        frame.sort_values([KEY_COLUMN, "DAYS_DECISION"], ascending=[True, False])
        .groupby(KEY_COLUMN)
        .head(TREND_APPLICATIONS)
        .sort_values([KEY_COLUMN, "DAYS_DECISION"])
    )
    slopes = recent.groupby(KEY_COLUMN)["AMT_APPLICATION"].agg(linear_trend_slope)
    return slopes.reset_index(name="PREV_AMT_APPLICATION_TREND")


def build_previous_application_features(
    previous_application: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build client-level previous-application features and their families."""

    frame = _add_row_features(previous_application)
    result = aggregate(frame, KEY_COLUMN, _AGGREGATIONS, prefix="PREV_")

    approved = frame[frame["IS_APPROVED"] == 1]
    result = merge_features(
        result,
        aggregate(approved, KEY_COLUMN, _APPROVED_AGGREGATIONS, prefix="PREV_"),
        on=KEY_COLUMN,
    )

    recent_refused = (
        frame[(frame["IS_REFUSED"] == 1) & (frame["DAYS_DECISION"] >= -RECENT_REFUSAL_DAYS)]
        .groupby(KEY_COLUMN)
        .size()
        .reset_index(name="PREV_RECENT_REFUSAL_COUNT")
    )
    result = merge_features(
        result,
        AggregationResult(
            frame=recent_refused, families={"PREV_RECENT_REFUSAL_COUNT": "counts"}
        ),
        on=KEY_COLUMN,
    )
    result = fill_counts(result, _ZERO_FILLED_COUNTS)

    trend = _requested_amount_trend(frame)
    result = merge_features(
        result,
        AggregationResult(frame=trend, families={"PREV_AMT_APPLICATION_TREND": "amounts"}),
        on=KEY_COLUMN,
    )

    for column, categories, prefix in [
        ("NAME_CONTRACT_TYPE", CONTRACT_TYPES, "PREV_CONTRACT_"),
        ("NAME_YIELD_GROUP", YIELD_GROUPS, "PREV_YIELD_"),
    ]:
        result = merge_features(
            result,
            one_hot_counts(
                frame,
                column,
                categories=categories,
                group_column=KEY_COLUMN,
                prefix=prefix,
                family="counts",
            ),
            on=KEY_COLUMN,
        )

    output = result.frame
    output["PREV_HAS_RECENT_REFUSAL"] = (
        output["PREV_RECENT_REFUSAL_COUNT"] > 0
    ).astype("int8")
    families = {**result.families, "PREV_HAS_RECENT_REFUSAL": "counts"}

    assert_unique_key(output, KEY_COLUMN, "previous_application client aggregate")
    return output, families
