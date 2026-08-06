"""Research features from ``POS_CASH_balance`` at ``SK_ID_CURR`` grain.

Two-level aggregation: monthly snapshots collapse to one row per ``SK_ID_PREV``
contract, then contracts collapse to one row per client. Aggregating months
straight to the client would weight a long-running contract more heavily than a
short one purely because it has more rows.

Ported from the team's standalone pipeline. The client-level statistics are
declared explicitly instead of being derived from whichever contract-level
columns happen to be numeric, so the output schema does not depend on the data.

These are research candidates, not production features.
"""

from __future__ import annotations

import pandas as pd

from credit_scoring.features.home_credit_aggregation import (
    Aggregation,
    AggregationResult,
    aggregate,
    assert_unique_key,
    count_true_episodes,
    fill_counts,
    longest_true_streak,
    merge_features,
)
from credit_scoring.numeric import safe_divide

KEY_COLUMN = "SK_ID_CURR"
CONTRACT_KEY = "SK_ID_PREV"
BUILDER_VERSION = "pos-cash-v1"

#: Months before application counted as "recent" for delinquency indicators.
RECENT_MONTHS = 6

_CONTRACT_AGGREGATIONS = (
    Aggregation("MONTHS_BALANCE", ("count",), "counts", name="POS_MONTHS"),
    Aggregation("MONTHS_BALANCE", ("max",), "recency", name="POS_LAST_MONTH"),
    Aggregation("SK_DPD", ("mean", "max", "sum"), "delinquency"),
    Aggregation("SK_DPD_DEF", ("mean", "max", "sum"), "delinquency"),
    Aggregation("IS_DPD", ("sum",), "delinquency", name="POS_DPD_MONTH"),
    Aggregation("CNT_INSTALMENT", ("max",), "counts"),
    Aggregation("CNT_INSTALMENT_FUTURE", ("min",), "counts"),
    Aggregation("COMPLETION_RATIO", ("max",), "counts"),
    Aggregation("IS_COMPLETED", ("max",), "counts", name="POS_COMPLETED"),
)

_CLIENT_AGGREGATIONS = (
    Aggregation(CONTRACT_KEY, ("count",), "counts", name="POS_CONTRACT"),
    Aggregation("POS_MONTHS_COUNT", ("sum", "mean", "max"), "counts"),
    Aggregation("POS_LAST_MONTH_MAX", ("max",), "recency", name="POS_LAST_MONTH"),
    Aggregation("SK_DPD_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("SK_DPD_MAX", ("max",), "delinquency", name="SK_DPD_WORST"),
    Aggregation("SK_DPD_SUM", ("sum",), "delinquency", name="SK_DPD_TOTAL"),
    Aggregation("SK_DPD_DEF_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("SK_DPD_DEF_MAX", ("max",), "delinquency", name="SK_DPD_DEF_WORST"),
    Aggregation("POS_DPD_MONTH_SUM", ("sum", "max"), "delinquency", name="POS_DPD_MONTH"),
    Aggregation("POS_DPD_RATE", ("mean", "max"), "delinquency"),
    Aggregation("POS_LONGEST_DPD_STREAK", ("max", "mean"), "delinquency"),
    Aggregation("POS_DPD_EPISODES", ("max", "sum"), "delinquency"),
    Aggregation("CNT_INSTALMENT_MAX", ("mean", "max"), "counts"),
    Aggregation("CNT_INSTALMENT_FUTURE_MIN", ("mean", "min"), "counts"),
    Aggregation("COMPLETION_RATIO_MAX", ("mean", "min"), "counts"),
    Aggregation("POS_COMPLETED_MAX", ("sum",), "counts", name="POS_COMPLETED"),
)

_RECENT_AGGREGATIONS = (
    Aggregation("SK_DPD", ("max", "mean"), "delinquency", name="POS_RECENT_DPD"),
    Aggregation("IS_DPD", ("sum",), "delinquency", name="POS_RECENT_DPD_MONTH"),
)

_ZERO_FILLED_COUNTS = ("POS_CONTRACTS_WITH_DPD_COUNT",)


def _add_row_features(pos_cash: pd.DataFrame) -> pd.DataFrame:
    frame = pos_cash.copy()
    frame["IS_DPD"] = (frame["SK_DPD"] > 0).astype("int8")
    frame["IS_COMPLETED"] = (frame["NAME_CONTRACT_STATUS"] == "Completed").astype("int8")
    frame["COMPLETION_RATIO"] = safe_divide(
        frame["CNT_INSTALMENT"] - frame["CNT_INSTALMENT_FUTURE"], frame["CNT_INSTALMENT"]
    )
    return frame


def _build_contract_features(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values([CONTRACT_KEY, "MONTHS_BALANCE"])
    result = aggregate(ordered, [KEY_COLUMN, CONTRACT_KEY], _CONTRACT_AGGREGATIONS)

    streaks = ordered.groupby(CONTRACT_KEY)["IS_DPD"].agg(
        POS_LONGEST_DPD_STREAK=longest_true_streak,
        POS_DPD_EPISODES=count_true_episodes,
    )
    contract = result.frame.merge(streaks.reset_index(), on=CONTRACT_KEY, how="left")
    contract["POS_DPD_RATE"] = safe_divide(
        contract["POS_DPD_MONTH_SUM"], contract["POS_MONTHS_COUNT"]
    )
    return contract


def build_pos_cash_features(pos_cash: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build client-level POS cash features and their families."""

    frame = _add_row_features(pos_cash)
    contract = _build_contract_features(frame)

    result = aggregate(contract, KEY_COLUMN, _CLIENT_AGGREGATIONS, prefix="POS_")

    recent = frame[frame["MONTHS_BALANCE"] >= -RECENT_MONTHS]
    result = merge_features(
        result, aggregate(recent, KEY_COLUMN, _RECENT_AGGREGATIONS, prefix="POS_"), on=KEY_COLUMN
    )

    contracts_with_dpd = (
        contract[contract["POS_DPD_MONTH_SUM"] > 0]
        .groupby(KEY_COLUMN)
        .size()
        .reset_index(name="POS_CONTRACTS_WITH_DPD_COUNT")
    )
    result = merge_features(
        result,
        AggregationResult(
            frame=contracts_with_dpd, families={"POS_CONTRACTS_WITH_DPD_COUNT": "counts"}
        ),
        on=KEY_COLUMN,
    )
    result = fill_counts(result, _ZERO_FILLED_COUNTS)

    output = result.frame
    output["POS_COMPLETION_RATE"] = safe_divide(
        output["POS_POS_COMPLETED_SUM"], output["POS_POS_CONTRACT_COUNT"]
    )
    output["POS_DPD_CONTRACT_RATIO"] = safe_divide(
        output["POS_CONTRACTS_WITH_DPD_COUNT"], output["POS_POS_CONTRACT_COUNT"]
    )
    families = {
        **result.families,
        "POS_COMPLETION_RATE": "counts",
        "POS_DPD_CONTRACT_RATIO": "delinquency",
    }

    assert_unique_key(output, KEY_COLUMN, "POS cash client aggregate")
    return output, families
