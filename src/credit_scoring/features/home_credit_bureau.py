"""Research features from ``bureau`` and ``bureau_balance``.

Two-level aggregation: monthly ``bureau_balance`` rows collapse to one row per
``SK_ID_BUREAU``, join one-to-one onto ``bureau``, and that collapses to one row
per ``SK_ID_CURR``.

Ported from the team's standalone pipeline with three deliberate changes:

* Amount totals use ``SUM_OBSERVED`` so a client with no observed amount keeps
  ``NaN``. The original emitted ``0``, which contradicted its own ``MEAN`` and
  ``MAX`` on the same column returning ``NaN`` for that client.
* ``CREDIT_TYPE`` counts come from a declared category list instead of whatever
  the data contains above a frequency cut-off, so the schema is stable.
* ``STATUS == "X"`` is treated as unobserved rather than as "no delinquency".
  ``X`` means the month was not reported; scoring it as zero pulls the severity
  mean down for exactly the clients whose history is least visible.

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
    longest_true_streak,
    merge_features,
    one_hot_counts,
)
from credit_scoring.numeric import safe_divide

KEY_COLUMN = "SK_ID_CURR"
LOAN_KEY = "SK_ID_BUREAU"
BUILDER_VERSION = "bureau-v1"

#: Declared ``CREDIT_TYPE`` values. Anything else is counted under ``OTHER``.
CREDIT_TYPES: tuple[str, ...] = (
    "Consumer credit",
    "Credit card",
    "Car loan",
    "Mortgage",
    "Microloan",
)

#: ``STATUS`` severity. ``C`` closed months carry no delinquency; ``X`` months
#: were not reported and stay unobserved.
STATUS_SEVERITY: dict[str, float] = {
    "C": 0.0,
    "0": 0.0,
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
}

_BALANCE_AGGREGATIONS = (
    Aggregation("MONTHS_BALANCE", ("count",), "counts", name="BB_MONTHS"),
    Aggregation("MONTHS_BALANCE", ("min",), "recency", name="BB_MONTHS_BALANCE"),
    Aggregation("STATUS_SEVERITY", ("mean", "max"), "delinquency", name="BB_STATUS"),
    Aggregation("IS_DPD", ("sum",), "delinquency", name="BB_DPD_MONTH"),
    Aggregation("IS_OBSERVED", ("sum",), "counts", name="BB_OBSERVED_MONTH"),
)

_RECENT_BALANCE_AGGREGATIONS = (
    Aggregation("STATUS_SEVERITY", ("mean",), "delinquency", name="BB_RECENT_STATUS"),
    Aggregation("IS_DPD", ("sum",), "delinquency", name="BB_RECENT_DPD"),
)

_BUREAU_AGGREGATIONS = (
    Aggregation("DAYS_CREDIT", ("max", "min", "mean"), "recency"),
    Aggregation("DAYS_CREDIT_ENDDATE", ("max", "min"), "recency"),
    Aggregation("CREDIT_DAY_OVERDUE", ("max", "mean"), "delinquency"),
    Aggregation("AMT_CREDIT_SUM", ("sum_observed", "mean", "max"), "amounts"),
    Aggregation("AMT_CREDIT_SUM_DEBT", ("sum_observed", "mean", "max"), "amounts"),
    Aggregation("AMT_CREDIT_SUM_OVERDUE", ("sum_observed", "max"), "amounts"),
    Aggregation("AMT_CREDIT_SUM_LIMIT", ("sum_observed",), "amounts"),
    Aggregation("AMT_CREDIT_MAX_OVERDUE", ("max", "mean"), "amounts"),
    Aggregation("AMT_ANNUITY", ("sum_observed", "mean"), "amounts"),
    Aggregation("CNT_CREDIT_PROLONG", ("sum",), "counts"),
    Aggregation("DEBT_CREDIT_RATIO", ("mean", "max", "min"), "amounts"),
    Aggregation("OVERDUE_CREDIT_RATIO", ("mean", "max"), "amounts"),
    Aggregation("IS_ACTIVE", ("sum",), "counts", name="ACTIVE"),
    Aggregation("IS_CLOSED", ("sum",), "counts", name="CLOSED"),
    Aggregation("HAS_OVERDUE", ("sum", "mean"), "delinquency"),
    Aggregation(LOAN_KEY, ("count",), "counts", name="LOAN"),
    Aggregation("BB_MONTHS_COUNT", ("sum",), "counts", name="BB_MONTHS_TOTAL"),
    Aggregation("BB_STATUS_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("BB_STATUS_MAX", ("max",), "delinquency", name="BB_STATUS_WORST"),
    Aggregation("BB_MONTHS_BALANCE_MIN", ("min",), "recency"),
    Aggregation("BB_DPD_MONTH_SUM", ("sum",), "delinquency", name="BB_DPD_MONTH_TOTAL"),
    Aggregation("BB_DPD_MONTH_SHARE", ("mean", "max"), "delinquency"),
    Aggregation("BB_LONGEST_DPD_STREAK", ("max", "mean"), "delinquency"),
    Aggregation("BB_DPD_EPISODES", ("max", "sum"), "delinquency"),
    Aggregation("BB_RECENT_STATUS_MEAN", ("mean", "max"), "delinquency"),
    Aggregation("BB_RECENT_DPD_SUM", ("sum",), "delinquency", name="BB_RECENT_DPD_TOTAL"),
)

_ACTIVE_AGGREGATIONS = (
    Aggregation("AMT_CREDIT_SUM_DEBT", ("sum_observed",), "amounts", name="ACTIVE_DEBT"),
    Aggregation("AMT_CREDIT_SUM", ("sum_observed",), "amounts", name="ACTIVE_CREDIT"),
    Aggregation("AMT_CREDIT_SUM_LIMIT", ("sum_observed",), "amounts", name="ACTIVE_LIMIT"),
    Aggregation(LOAN_KEY, ("count",), "counts", name="ACTIVE_LOAN"),
)

#: Count columns where an absent source row genuinely means zero.
_ZERO_FILLED_COUNTS = (
    "BUREAU_ACTIVE_LOAN_COUNT",
    "BUREAU_LOANS_WITH_DPD_COUNT",
)

RECENT_BALANCE_MONTHS = 6


def build_bureau_balance_features(bureau_balance: pd.DataFrame) -> pd.DataFrame:
    """Collapse monthly ``bureau_balance`` rows to one row per ``SK_ID_BUREAU``."""

    frame = bureau_balance.copy()
    severity = frame["STATUS"].astype("object").map(STATUS_SEVERITY)
    frame["STATUS_SEVERITY"] = severity.astype("float32")
    frame["IS_OBSERVED"] = severity.notna().astype("int8")
    frame["IS_DPD"] = (severity > 0).fillna(False).astype("int8")

    result = aggregate(frame, LOAN_KEY, _BALANCE_AGGREGATIONS)

    recent = frame[frame["MONTHS_BALANCE"] >= -RECENT_BALANCE_MONTHS]
    recent_result = aggregate(recent, LOAN_KEY, _RECENT_BALANCE_AGGREGATIONS)
    result = merge_features(result, recent_result, on=LOAN_KEY)

    ordered = frame.sort_values([LOAN_KEY, "MONTHS_BALANCE"])
    flags = ordered.groupby(LOAN_KEY)["IS_DPD"].agg(
        BB_LONGEST_DPD_STREAK=longest_true_streak,
        BB_DPD_EPISODES=count_true_episodes,
    )
    result = merge_features(
        result,
        AggregationResult(
            frame=flags.reset_index(),
            families={
                "BB_LONGEST_DPD_STREAK": "delinquency",
                "BB_DPD_EPISODES": "delinquency",
            },
        ),
        on=LOAN_KEY,
    )

    output = result.frame
    output["BB_DPD_MONTH_SHARE"] = safe_divide(
        output["BB_DPD_MONTH_SUM"], output["BB_OBSERVED_MONTH_SUM"]
    )
    assert_unique_key(output, LOAN_KEY, "bureau_balance aggregate")
    return output


def build_bureau_features(
    bureau: pd.DataFrame,
    bureau_balance: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build client-level bureau features and their semantic families."""

    frame = bureau.copy()
    balance_columns = [
        "BB_MONTHS_COUNT",
        "BB_MONTHS_BALANCE_MIN",
        "BB_STATUS_MEAN",
        "BB_STATUS_MAX",
        "BB_DPD_MONTH_SUM",
        "BB_OBSERVED_MONTH_SUM",
        "BB_RECENT_STATUS_MEAN",
        "BB_RECENT_DPD_SUM",
        "BB_LONGEST_DPD_STREAK",
        "BB_DPD_EPISODES",
        "BB_DPD_MONTH_SHARE",
    ]
    if bureau_balance is not None and len(bureau_balance):
        balance_features = build_bureau_balance_features(bureau_balance)
        before = len(frame)
        frame = frame.merge(balance_features, on=LOAN_KEY, how="left")
        if len(frame) != before:
            raise ValueError(
                f"bureau_balance join changed the bureau row count: {before} -> {len(frame)}"
            )
    else:
        for column in balance_columns:
            frame[column] = np.nan

    frame["IS_ACTIVE"] = (frame["CREDIT_ACTIVE"] == "Active").astype("int8")
    frame["IS_CLOSED"] = (frame["CREDIT_ACTIVE"] == "Closed").astype("int8")
    frame["HAS_OVERDUE"] = (frame["CREDIT_DAY_OVERDUE"] > 0).astype("int8")
    frame["DEBT_CREDIT_RATIO"] = safe_divide(
        frame["AMT_CREDIT_SUM_DEBT"], frame["AMT_CREDIT_SUM"]
    )
    frame["OVERDUE_CREDIT_RATIO"] = safe_divide(
        frame["AMT_CREDIT_SUM_OVERDUE"], frame["AMT_CREDIT_SUM"]
    )

    result = aggregate(frame, KEY_COLUMN, _BUREAU_AGGREGATIONS, prefix="BUREAU_")

    active = frame[frame["IS_ACTIVE"] == 1]
    active_result = aggregate(active, KEY_COLUMN, _ACTIVE_AGGREGATIONS, prefix="BUREAU_")
    result = merge_features(result, active_result, on=KEY_COLUMN)

    credit_types = one_hot_counts(
        frame,
        "CREDIT_TYPE",
        categories=CREDIT_TYPES,
        group_column=KEY_COLUMN,
        prefix="BUREAU_CTYPE_",
        family="counts",
    )
    result = merge_features(result, credit_types, on=KEY_COLUMN)

    loans_with_dpd = (
        frame[frame["BB_DPD_MONTH_SUM"] > 0]
        .groupby(KEY_COLUMN)
        .size()
        .reset_index(name="BUREAU_LOANS_WITH_DPD_COUNT")
    )
    result = merge_features(
        result,
        AggregationResult(
            frame=loans_with_dpd, families={"BUREAU_LOANS_WITH_DPD_COUNT": "counts"}
        ),
        on=KEY_COLUMN,
    )
    result = fill_counts(result, _ZERO_FILLED_COUNTS)

    output = result.frame
    output["BUREAU_ACTIVE_LOAN_RATIO"] = safe_divide(
        output["BUREAU_ACTIVE_LOAN_COUNT"], output["BUREAU_LOAN_COUNT"]
    )
    output["BUREAU_ACTIVE_UTILIZATION"] = safe_divide(
        output["BUREAU_ACTIVE_DEBT_SUM"], output["BUREAU_ACTIVE_CREDIT_SUM"]
    )
    output["BUREAU_DEBT_CREDIT_RATIO_TOTAL"] = safe_divide(
        output["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"], output["BUREAU_AMT_CREDIT_SUM_SUM"]
    )
    output["BUREAU_OVERDUE_DEBT_RATIO_TOTAL"] = safe_divide(
        output["BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM"], output["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"]
    )
    families = {
        **result.families,
        "BUREAU_ACTIVE_LOAN_RATIO": "counts",
        "BUREAU_ACTIVE_UTILIZATION": "amounts",
        "BUREAU_DEBT_CREDIT_RATIO_TOTAL": "amounts",
        "BUREAU_OVERDUE_DEBT_RATIO_TOTAL": "amounts",
    }

    assert_unique_key(output, KEY_COLUMN, "bureau client aggregate")
    return output, families
