"""Research features from ``installments_payments`` at ``SK_ID_CURR`` grain.

Three groups of features are produced:

* nested aggregation of installment rows to loan (``SK_ID_PREV``) and then to
  client, so a loan with many installments does not dominate the client average;
* windowed aggregates over the last 60/90/180/365 days, together with their
  difference against the lifetime average, which is what distinguishes a client
  who is deteriorating now from one who was late years ago;
* short sequence aggregates over the most recent installments.

Ported from the team's standalone pipeline. Client-level statistics are declared
explicitly, amount totals use ``SUM_OBSERVED``, and trend slopes are computed
oldest-first so a positive slope means delinquency is getting worse.

These are research candidates, not production features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

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
)
from credit_scoring.numeric import safe_divide

KEY_COLUMN = "SK_ID_CURR"
LOAN_KEY = "SK_ID_PREV"
BUILDER_VERSION = "installments-v1"

#: Days-past-due thresholds turned into indicator counts.
DPD_THRESHOLDS: tuple[int, ...] = (7, 30, 60, 90)
#: Trailing windows in days before the application date.
TIME_WINDOWS_DAYS: tuple[int, ...] = (60, 90, 180, 365)
#: Sequence lengths for "most recent N installments" aggregates.
SEQUENCE_WINDOWS: tuple[int, ...] = (1, 3, 5)
#: Installments entering the trend slopes.
TREND_INSTALLMENTS = 20

_LOAN_AGGREGATIONS = (
    Aggregation("NUM_INSTALMENT_NUMBER", ("count",), "counts", name="INST"),
    Aggregation("DPD", ("mean", "max", "sum"), "delinquency"),
    Aggregation("IS_LATE", ("sum",), "delinquency", name="LATE"),
    Aggregation("PAYMENT_RATIO", ("mean", "min"), "amounts"),
    Aggregation("UNDERPAYMENT", ("sum_observed", "max"), "amounts"),
    Aggregation("IS_UNDERPAID", ("sum",), "amounts", name="UNDERPAID"),
    *(
        Aggregation(f"DPD_GE_{threshold}", ("sum",), "delinquency")
        for threshold in DPD_THRESHOLDS
    ),
)

_CLIENT_AGGREGATIONS = (
    Aggregation(LOAN_KEY, ("count",), "counts", name="INST_LOAN"),
    Aggregation("INST_COUNT", ("sum", "mean", "max"), "counts"),
    Aggregation("DPD_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("DPD_MAX", ("max", "mean"), "delinquency", name="DPD_WORST"),
    Aggregation("DPD_SUM", ("sum",), "delinquency", name="DPD_TOTAL"),
    Aggregation("LATE_SUM", ("sum", "max"), "delinquency", name="LATE"),
    Aggregation("LATE_RATE", ("mean", "max"), "delinquency"),
    Aggregation("PAYMENT_RATIO_MEAN", ("mean", "min"), "amounts"),
    Aggregation("PAYMENT_RATIO_MIN", ("min",), "amounts", name="PAYMENT_RATIO_WORST"),
    Aggregation("UNDERPAYMENT_SUM", ("sum_observed", "max"), "amounts", name="UNDERPAYMENT"),
    Aggregation("UNDERPAID_SUM", ("sum",), "amounts", name="UNDERPAID"),
    Aggregation("UNDERPAID_RATE", ("mean", "max"), "amounts"),
    Aggregation("LONGEST_LATE_STREAK", ("max", "mean"), "delinquency"),
    Aggregation("LATE_EPISODES", ("max", "sum"), "delinquency"),
    *(
        Aggregation(f"DPD_GE_{threshold}_SUM", ("sum",), "delinquency", name=f"DPD_GE_{threshold}")
        for threshold in DPD_THRESHOLDS
    ),
)

_LIFETIME_AGGREGATIONS = (
    Aggregation("DPD", ("mean",), "delinquency", name="INST_DPD_LIFETIME"),
    Aggregation("PAYMENT_RATIO", ("mean",), "amounts", name="INST_PAYMENT_RATIO_LIFETIME"),
    Aggregation("IS_LATE", ("sum",), "delinquency", name="INST_LATE_LIFETIME"),
    Aggregation("NUM_INSTALMENT_NUMBER", ("count",), "counts", name="INST_COUNT_LIFETIME"),
)

_ZERO_FILLED_COUNTS = ("INST_LOANS_WITH_LATE_COUNT",)


def _add_row_features(installments: pd.DataFrame) -> pd.DataFrame:
    frame = installments.copy()
    # Both dates are negative day offsets; paying later than due gives a positive
    # difference. Early payment is clamped to zero rather than made negative.
    frame["DPD"] = np.maximum(
        frame["DAYS_ENTRY_PAYMENT"] - frame["DAYS_INSTALMENT"], 0
    ).astype("float32")
    frame["IS_LATE"] = (frame["DPD"] > 0).fillna(False).astype("int8")
    for threshold in DPD_THRESHOLDS:
        frame[f"DPD_GE_{threshold}"] = (frame["DPD"] >= threshold).fillna(False).astype("int8")
    frame["PAYMENT_RATIO"] = safe_divide(frame["AMT_PAYMENT"], frame["AMT_INSTALMENT"])
    frame["UNDERPAYMENT"] = np.maximum(
        frame["AMT_INSTALMENT"] - frame["AMT_PAYMENT"], 0
    ).astype("float32")
    frame["IS_UNDERPAID"] = (frame["UNDERPAYMENT"] > 0).fillna(False).astype("int8")
    return frame


def _build_loan_features(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values([LOAN_KEY, "NUM_INSTALMENT_NUMBER"])
    result = aggregate(ordered, [KEY_COLUMN, LOAN_KEY], _LOAN_AGGREGATIONS)

    streaks = ordered.groupby(LOAN_KEY)["IS_LATE"].agg(
        LONGEST_LATE_STREAK=longest_true_streak,
        LATE_EPISODES=count_true_episodes,
    )
    loan = result.frame.merge(streaks.reset_index(), on=LOAN_KEY, how="left")
    loan["LATE_RATE"] = safe_divide(loan["LATE_SUM"], loan["INST_COUNT"])
    loan["UNDERPAID_RATE"] = safe_divide(loan["UNDERPAID_SUM"], loan["INST_COUNT"])
    return loan


def _windowed_features(frame: pd.DataFrame) -> AggregationResult:
    """Trailing-window aggregates plus their gap against the lifetime average."""

    lifetime = aggregate(frame, KEY_COLUMN, _LIFETIME_AGGREGATIONS)
    output = lifetime.frame
    output["INST_LATE_RATE_LIFETIME"] = safe_divide(
        output["INST_LATE_LIFETIME_SUM"], output["INST_COUNT_LIFETIME_COUNT"]
    )
    families = {**lifetime.families, "INST_LATE_RATE_LIFETIME": "delinquency"}

    for window in TIME_WINDOWS_DAYS:
        windowed = aggregate(
            frame[frame["DAYS_INSTALMENT"] >= -window],
            KEY_COLUMN,
            (
                Aggregation("DPD", ("mean", "max"), "delinquency", name=f"INST_DPD_{window}D"),
                Aggregation(
                    "IS_LATE", ("sum",), "delinquency", name=f"INST_LATE_{window}D"
                ),
                Aggregation(
                    "PAYMENT_RATIO", ("mean",), "amounts", name=f"INST_PAYMENT_RATIO_{window}D"
                ),
                Aggregation(
                    "UNDERPAYMENT",
                    ("sum_observed",),
                    "amounts",
                    name=f"INST_UNDERPAYMENT_{window}D",
                ),
                Aggregation(
                    "NUM_INSTALMENT_NUMBER", ("count",), "counts", name=f"INST_{window}D"
                ),
            ),
        )
        output = output.merge(windowed.frame, on=KEY_COLUMN, how="outer")
        families.update(windowed.families)

        rate = f"INST_LATE_RATE_{window}D"
        output[rate] = safe_divide(
            output[f"INST_LATE_{window}D_SUM"], output[f"INST_{window}D_COUNT"]
        )
        output[f"INST_DPD_RECENT_MINUS_LIFE_{window}D"] = (
            output[f"INST_DPD_{window}D_MEAN"] - output["INST_DPD_LIFETIME_MEAN"]
        ).astype("float32")
        output[f"INST_LATE_RATE_RECENT_MINUS_LIFE_{window}D"] = (
            output[rate] - output["INST_LATE_RATE_LIFETIME"]
        ).astype("float32")
        families[rate] = "delinquency"
        families[f"INST_DPD_RECENT_MINUS_LIFE_{window}D"] = "delinquency"
        families[f"INST_LATE_RATE_RECENT_MINUS_LIFE_{window}D"] = "delinquency"

    return AggregationResult(frame=output, families=families)


def _sequence_features(frame: pd.DataFrame) -> AggregationResult:
    """Aggregates over the most recent N installments, and trend slopes."""

    by_recency = frame.sort_values([KEY_COLUMN, "DAYS_INSTALMENT"], ascending=[True, False])
    output: pd.DataFrame | None = None
    families: dict[str, str] = {}

    for size in SEQUENCE_WINDOWS:
        recent = by_recency.groupby(KEY_COLUMN).head(size)
        result = aggregate(
            recent,
            KEY_COLUMN,
            (
                Aggregation("DPD", ("mean", "max"), "delinquency", name=f"INST_LAST{size}_DPD"),
                Aggregation(
                    "PAYMENT_RATIO",
                    ("mean",),
                    "amounts",
                    name=f"INST_LAST{size}_PAYMENT_RATIO",
                ),
                Aggregation("IS_LATE", ("sum",), "delinquency", name=f"INST_LAST{size}_LATE"),
            ),
        )
        output = result.frame if output is None else output.merge(
            result.frame, on=KEY_COLUMN, how="outer"
        )
        families.update(result.families)

    trend_source = (
        by_recency.groupby(KEY_COLUMN)
        .head(TREND_INSTALLMENTS)
        .sort_values([KEY_COLUMN, "DAYS_INSTALMENT"])
    )
    slopes = trend_source.groupby(KEY_COLUMN).agg(
        INST_DPD_TREND_SLOPE=pd.NamedAgg("DPD", linear_trend_slope),
        INST_PAYMENT_RATIO_TREND_SLOPE=pd.NamedAgg("PAYMENT_RATIO", linear_trend_slope),
    )
    assert output is not None
    output = output.merge(slopes.reset_index(), on=KEY_COLUMN, how="outer")
    families["INST_DPD_TREND_SLOPE"] = "delinquency"
    families["INST_PAYMENT_RATIO_TREND_SLOPE"] = "amounts"

    last_late = (
        frame[frame["IS_LATE"] == 1]
        .groupby(KEY_COLUMN)["DAYS_INSTALMENT"]
        .max()
        .reset_index(name="INST_DAYS_SINCE_LAST_LATE")
    )
    last_late["INST_DAYS_SINCE_LAST_LATE"] = -last_late["INST_DAYS_SINCE_LAST_LATE"]
    output = output.merge(last_late, on=KEY_COLUMN, how="left")
    families["INST_DAYS_SINCE_LAST_LATE"] = "recency"

    return AggregationResult(frame=output, families=families)


def build_installments_features(
    installments: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build client-level installment features and their families."""

    frame = _add_row_features(installments)
    loan = _build_loan_features(frame)

    result = aggregate(loan, KEY_COLUMN, _CLIENT_AGGREGATIONS, prefix="INST_")

    loans_with_late = (
        loan[loan["LATE_SUM"] > 0]
        .groupby(KEY_COLUMN)
        .size()
        .reset_index(name="INST_LOANS_WITH_LATE_COUNT")
    )
    result = merge_features(
        result,
        AggregationResult(
            frame=loans_with_late, families={"INST_LOANS_WITH_LATE_COUNT": "counts"}
        ),
        on=KEY_COLUMN,
    )
    result = fill_counts(result, _ZERO_FILLED_COUNTS)

    result = merge_features(result, _windowed_features(frame), on=KEY_COLUMN)
    result = merge_features(result, _sequence_features(frame), on=KEY_COLUMN)

    assert_unique_key(result.frame, KEY_COLUMN, "installments client aggregate")
    return result.frame, result.families
