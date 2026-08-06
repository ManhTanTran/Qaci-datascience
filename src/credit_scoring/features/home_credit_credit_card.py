"""Research features from ``credit_card_balance`` at ``SK_ID_CURR`` grain.

Two-level aggregation: monthly snapshots collapse to one row per ``SK_ID_PREV``
card, then cards collapse to one row per client.

Portfolio utilisation is a ratio of sums taken on each card's most recent
snapshot, not a mean of per-card ratios: a nearly-exhausted small card should not
count as much as a large one that is barely used.

Ported from the team's standalone pipeline, with explicitly declared
client-level statistics so the schema does not depend on the data.

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
)
from credit_scoring.numeric import safe_divide

KEY_COLUMN = "SK_ID_CURR"
CARD_KEY = "SK_ID_PREV"
BUILDER_VERSION = "credit-card-v1"

#: Utilisation above this share of the limit counts as a high-utilisation month.
HIGH_UTILIZATION_THRESHOLD = 0.9
#: Months before application counted as "recent".
RECENT_MONTHS = 6

_CARD_AGGREGATIONS = (
    Aggregation("MONTHS_BALANCE", ("count",), "counts", name="CC_MONTHS"),
    Aggregation("UTILIZATION", ("mean", "max", "min", "last"), "amounts"),
    Aggregation("IS_HIGH_UTILIZATION", ("sum",), "amounts", name="CC_HIGH_UTIL_MONTH"),
    Aggregation("PAYMENT_RATIO", ("mean", "min"), "amounts"),
    Aggregation("SK_DPD", ("mean", "max", "sum"), "delinquency"),
    Aggregation("SK_DPD_DEF", ("mean", "max"), "delinquency"),
    Aggregation("IS_DPD", ("sum",), "delinquency", name="CC_DPD_MONTH"),
    Aggregation("AMT_BALANCE", ("mean", "max", "last"), "amounts"),
    Aggregation("AMT_CREDIT_LIMIT_ACTUAL", ("mean", "max", "last"), "amounts"),
    Aggregation("AMT_DRAWINGS_CURRENT", ("mean", "sum_observed"), "amounts"),
    Aggregation("HAS_DRAWING", ("sum",), "counts", name="CC_DRAWING_MONTH"),
    Aggregation("IS_ACTIVE", ("last",), "counts", name="CC_ACTIVE"),
)

_CLIENT_AGGREGATIONS = (
    Aggregation(CARD_KEY, ("count",), "counts", name="CC_CARD"),
    Aggregation("CC_MONTHS_COUNT", ("sum", "mean"), "counts"),
    Aggregation("UTILIZATION_MEAN", ("mean", "max"), "amounts"),
    Aggregation("UTILIZATION_MAX", ("max",), "amounts", name="UTILIZATION_WORST"),
    Aggregation("UTILIZATION_LAST", ("mean", "max"), "amounts"),
    Aggregation("CC_HIGH_UTIL_MONTH_SUM", ("sum", "max"), "amounts", name="CC_HIGH_UTIL_MONTH"),
    Aggregation("CC_HIGH_UTIL_RATE", ("mean", "max"), "amounts"),
    Aggregation("PAYMENT_RATIO_MEAN", ("mean", "min"), "amounts"),
    Aggregation("SK_DPD_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("SK_DPD_MAX", ("max",), "delinquency", name="SK_DPD_WORST"),
    Aggregation("SK_DPD_DEF_MAX", ("max",), "delinquency", name="SK_DPD_DEF_WORST"),
    Aggregation("CC_DPD_MONTH_SUM", ("sum", "max"), "delinquency", name="CC_DPD_MONTH"),
    Aggregation("CC_DPD_RATE", ("mean", "max"), "delinquency"),
    Aggregation("AMT_BALANCE_MEAN", ("mean", "max"), "amounts"),
    Aggregation("AMT_CREDIT_LIMIT_ACTUAL_MAX", ("max", "sum_observed"), "amounts"),
    Aggregation("AMT_DRAWINGS_CURRENT_SUM", ("sum_observed",), "amounts"),
    Aggregation("CC_UTIL_TREND_SLOPE", ("mean", "max"), "amounts"),
    Aggregation("CC_ACTIVE_LAST", ("sum",), "counts", name="CC_ACTIVE_CARD"),
)

_RECENT_AGGREGATIONS = (
    Aggregation("UTILIZATION", ("mean", "max"), "amounts", name="CC_RECENT_UTILIZATION"),
    Aggregation("SK_DPD", ("max",), "delinquency", name="CC_RECENT_DPD"),
)

_ZERO_FILLED_COUNTS = ("CC_CC_ACTIVE_CARD_SUM",)


def _add_row_features(credit_card: pd.DataFrame) -> pd.DataFrame:
    frame = credit_card.copy()
    frame["UTILIZATION"] = safe_divide(
        frame["AMT_BALANCE"], frame["AMT_CREDIT_LIMIT_ACTUAL"]
    )
    frame["IS_HIGH_UTILIZATION"] = (
        frame["UTILIZATION"] > HIGH_UTILIZATION_THRESHOLD
    ).fillna(False).astype("int8")
    frame["PAYMENT_RATIO"] = safe_divide(
        frame["AMT_PAYMENT_TOTAL_CURRENT"], frame["AMT_INST_MIN_REGULARITY"]
    )
    frame["IS_DPD"] = (frame["SK_DPD"] > 0).astype("int8")
    frame["IS_ACTIVE"] = (frame["NAME_CONTRACT_STATUS"] == "Active").astype("int8")
    frame["HAS_DRAWING"] = (frame["AMT_DRAWINGS_CURRENT"] > 0).fillna(False).astype("int8")
    return frame


def _build_card_features(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values([CARD_KEY, "MONTHS_BALANCE"])
    result = aggregate(ordered, [KEY_COLUMN, CARD_KEY], _CARD_AGGREGATIONS)

    slopes = ordered.groupby(CARD_KEY)["UTILIZATION"].agg(linear_trend_slope)
    card = result.frame.merge(
        slopes.reset_index(name="CC_UTIL_TREND_SLOPE"), on=CARD_KEY, how="left"
    )
    card["CC_HIGH_UTIL_RATE"] = safe_divide(
        card["CC_HIGH_UTIL_MONTH_SUM"], card["CC_MONTHS_COUNT"]
    )
    card["CC_DPD_RATE"] = safe_divide(card["CC_DPD_MONTH_SUM"], card["CC_MONTHS_COUNT"])
    return card


def _portfolio_utilization(frame: pd.DataFrame) -> pd.DataFrame:
    """Ratio of summed balance to summed limit across each card's last snapshot."""

    latest = (
        frame.sort_values([CARD_KEY, "MONTHS_BALANCE"])
        .groupby([KEY_COLUMN, CARD_KEY], as_index=False)
        .last()
    )
    portfolio = latest.groupby(KEY_COLUMN).agg(
        CC_PORTFOLIO_BALANCE=pd.NamedAgg("AMT_BALANCE", lambda s: s.sum(min_count=1)),
        CC_PORTFOLIO_LIMIT=pd.NamedAgg("AMT_CREDIT_LIMIT_ACTUAL", lambda s: s.sum(min_count=1)),
    )
    portfolio = portfolio.reset_index()
    portfolio["CC_PORTFOLIO_UTILIZATION"] = safe_divide(
        portfolio["CC_PORTFOLIO_BALANCE"], portfolio["CC_PORTFOLIO_LIMIT"]
    )
    return portfolio


def build_credit_card_features(
    credit_card: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build client-level credit-card features and their families."""

    frame = _add_row_features(credit_card)
    card = _build_card_features(frame)

    result = aggregate(card, KEY_COLUMN, _CLIENT_AGGREGATIONS, prefix="CC_")

    recent = frame[frame["MONTHS_BALANCE"] >= -RECENT_MONTHS]
    result = merge_features(
        result, aggregate(recent, KEY_COLUMN, _RECENT_AGGREGATIONS, prefix="CC_"), on=KEY_COLUMN
    )

    portfolio = _portfolio_utilization(frame)
    result = merge_features(
        result,
        AggregationResult(
            frame=portfolio,
            families={
                "CC_PORTFOLIO_BALANCE": "amounts",
                "CC_PORTFOLIO_LIMIT": "amounts",
                "CC_PORTFOLIO_UTILIZATION": "amounts",
            },
        ),
        on=KEY_COLUMN,
    )
    result = fill_counts(result, _ZERO_FILLED_COUNTS)

    assert_unique_key(result.frame, KEY_COLUMN, "credit card client aggregate")
    return result.frame, result.families
