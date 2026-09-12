"""Spark parity implementation for the Home Credit Bureau research block.

The pandas implementation in :mod:`credit_scoring.features.home_credit_bureau`
is the reference contract.  This module deliberately declares the complete
Spark output schema instead of deriving columns from a sample.  PySpark is
imported lazily so the base package and non-Spark tests remain usable without a
local Spark installation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_scoring.feature_store import BlockManifest, block_paths
from credit_scoring.features.home_credit_bureau import CREDIT_TYPES, STATUS_SEVERITY

KEY_COLUMN = "SK_ID_CURR"
LOAN_KEY = "SK_ID_BUREAU"
SPARK_BUILDER_VERSION = "bureau-v1-spark-smoke"
RECENT_BALANCE_MONTHS = 6

BALANCE_FEATURE_SPECS: tuple[tuple[str, str], ...] = (
    ("BB_MONTHS_COUNT", "counts"),
    ("BB_MONTHS_BALANCE_MIN", "recency"),
    ("BB_STATUS_MEAN", "delinquency"),
    ("BB_STATUS_MAX", "delinquency"),
    ("BB_DPD_MONTH_SUM", "delinquency"),
    ("BB_OBSERVED_MONTH_SUM", "counts"),
    ("BB_RECENT_STATUS_MEAN", "delinquency"),
    ("BB_RECENT_DPD_SUM", "delinquency"),
    ("BB_LONGEST_DPD_STREAK", "delinquency"),
    ("BB_DPD_EPISODES", "delinquency"),
    ("BB_DPD_MONTH_SHARE", "delinquency"),
)

BUREAU_FEATURE_SPECS: tuple[tuple[str, str], ...] = (
    ("BUREAU_DAYS_CREDIT_MAX", "recency"),
    ("BUREAU_DAYS_CREDIT_MIN", "recency"),
    ("BUREAU_DAYS_CREDIT_MEAN", "recency"),
    ("BUREAU_DAYS_CREDIT_ENDDATE_MAX", "recency"),
    ("BUREAU_DAYS_CREDIT_ENDDATE_MIN", "recency"),
    ("BUREAU_CREDIT_DAY_OVERDUE_MAX", "delinquency"),
    ("BUREAU_CREDIT_DAY_OVERDUE_MEAN", "delinquency"),
    ("BUREAU_AMT_CREDIT_SUM_SUM", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_MEAN", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_MAX", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_DEBT_SUM", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_DEBT_MEAN", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_DEBT_MAX", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_OVERDUE_MAX", "amounts"),
    ("BUREAU_AMT_CREDIT_SUM_LIMIT_SUM", "amounts"),
    ("BUREAU_AMT_CREDIT_MAX_OVERDUE_MAX", "amounts"),
    ("BUREAU_AMT_CREDIT_MAX_OVERDUE_MEAN", "amounts"),
    ("BUREAU_AMT_ANNUITY_SUM", "amounts"),
    ("BUREAU_AMT_ANNUITY_MEAN", "amounts"),
    ("BUREAU_CNT_CREDIT_PROLONG_SUM", "counts"),
    ("BUREAU_DEBT_CREDIT_RATIO_MEAN", "amounts"),
    ("BUREAU_DEBT_CREDIT_RATIO_MAX", "amounts"),
    ("BUREAU_DEBT_CREDIT_RATIO_MIN", "amounts"),
    ("BUREAU_OVERDUE_CREDIT_RATIO_MEAN", "amounts"),
    ("BUREAU_OVERDUE_CREDIT_RATIO_MAX", "amounts"),
    ("BUREAU_ACTIVE_SUM", "counts"),
    ("BUREAU_CLOSED_SUM", "counts"),
    ("BUREAU_HAS_OVERDUE_SUM", "delinquency"),
    ("BUREAU_HAS_OVERDUE_MEAN", "delinquency"),
    ("BUREAU_LOAN_COUNT", "counts"),
    ("BUREAU_BB_MONTHS_TOTAL_SUM", "counts"),
    ("BUREAU_BB_STATUS_MEAN_MEAN", "delinquency"),
    ("BUREAU_BB_STATUS_MEAN_MAX", "delinquency"),
    ("BUREAU_BB_STATUS_WORST_MAX", "delinquency"),
    ("BUREAU_BB_MONTHS_BALANCE_MIN_MIN", "recency"),
    ("BUREAU_BB_DPD_MONTH_TOTAL_SUM", "delinquency"),
    ("BUREAU_BB_DPD_MONTH_SHARE_MEAN", "delinquency"),
    ("BUREAU_BB_DPD_MONTH_SHARE_MAX", "delinquency"),
    ("BUREAU_BB_LONGEST_DPD_STREAK_MAX", "delinquency"),
    ("BUREAU_BB_LONGEST_DPD_STREAK_MEAN", "delinquency"),
    ("BUREAU_BB_DPD_EPISODES_MAX", "delinquency"),
    ("BUREAU_BB_DPD_EPISODES_SUM", "delinquency"),
    ("BUREAU_BB_RECENT_STATUS_MEAN_MEAN", "delinquency"),
    ("BUREAU_BB_RECENT_STATUS_MEAN_MAX", "delinquency"),
    ("BUREAU_BB_RECENT_DPD_TOTAL_SUM", "delinquency"),
    ("BUREAU_ACTIVE_DEBT_SUM", "amounts"),
    ("BUREAU_ACTIVE_CREDIT_SUM", "amounts"),
    ("BUREAU_ACTIVE_LIMIT_SUM", "amounts"),
    ("BUREAU_ACTIVE_LOAN_COUNT", "counts"),
    *((f"BUREAU_CTYPE_{credit_type}_COUNT", "counts") for credit_type in CREDIT_TYPES),
    ("BUREAU_CTYPE_OTHER_COUNT", "counts"),
    ("BUREAU_LOANS_WITH_DPD_COUNT", "counts"),
    ("BUREAU_ACTIVE_LOAN_RATIO", "counts"),
    ("BUREAU_ACTIVE_UTILIZATION", "amounts"),
    ("BUREAU_DEBT_CREDIT_RATIO_TOTAL", "amounts"),
    ("BUREAU_OVERDUE_DEBT_RATIO_TOTAL", "amounts"),
)

BALANCE_FEATURE_NAMES = tuple(name for name, _ in BALANCE_FEATURE_SPECS)
BALANCE_FEATURE_FAMILIES = dict(BALANCE_FEATURE_SPECS)
BUREAU_FEATURE_NAMES = tuple(name for name, _ in BUREAU_FEATURE_SPECS)
BUREAU_FEATURE_FAMILIES = dict(BUREAU_FEATURE_SPECS)
BUREAU_EXACT_FEATURE_NAMES = (
    "BUREAU_CNT_CREDIT_PROLONG_SUM",
    "BUREAU_ACTIVE_SUM",
    "BUREAU_CLOSED_SUM",
    "BUREAU_HAS_OVERDUE_SUM",
    "BUREAU_LOAN_COUNT",
    "BUREAU_BB_MONTHS_TOTAL_SUM",
    "BUREAU_BB_DPD_MONTH_TOTAL_SUM",
    "BUREAU_BB_DPD_EPISODES_SUM",
    "BUREAU_BB_RECENT_DPD_TOTAL_SUM",
    "BUREAU_ACTIVE_LOAN_COUNT",
    *(f"BUREAU_CTYPE_{credit_type}_COUNT" for credit_type in CREDIT_TYPES),
    "BUREAU_CTYPE_OTHER_COUNT",
    "BUREAU_LOANS_WITH_DPD_COUNT",
)

BUREAU_REQUIRED_COLUMNS = (
    KEY_COLUMN,
    LOAN_KEY,
    "CREDIT_ACTIVE",
    "CREDIT_TYPE",
    "DAYS_CREDIT",
    "DAYS_CREDIT_ENDDATE",
    "CREDIT_DAY_OVERDUE",
    "AMT_CREDIT_SUM",
    "AMT_CREDIT_SUM_DEBT",
    "AMT_CREDIT_SUM_OVERDUE",
    "AMT_CREDIT_SUM_LIMIT",
    "AMT_CREDIT_MAX_OVERDUE",
    "AMT_ANNUITY",
    "CNT_CREDIT_PROLONG",
)
BALANCE_REQUIRED_COLUMNS = (LOAN_KEY, "MONTHS_BALANCE", "STATUS")


def _spark_imports() -> tuple[Any, Any, Any]:
    try:
        from pyspark.sql import Window
        from pyspark.sql import functions as F
        from pyspark.sql import types as T
    except ImportError as exc:  # pragma: no cover - exercised when Spark is installed
        raise ImportError(
            "PySpark is required for the Spark Bureau candidate. "
            "Install the optional Spark runtime or run the Kaggle smoke notebook."
        ) from exc
    return F, Window, T


def bureau_csv_schema_spark() -> Any:
    """Return the explicit schema matching the public ``bureau.csv`` order."""

    _, _, T = _spark_imports()
    return T.StructType(
        [
            T.StructField("SK_ID_CURR", T.IntegerType(), False),
            T.StructField("SK_ID_BUREAU", T.IntegerType(), False),
            T.StructField("CREDIT_ACTIVE", T.StringType(), True),
            T.StructField("CREDIT_CURRENCY", T.StringType(), True),
            T.StructField("DAYS_CREDIT", T.IntegerType(), True),
            T.StructField("CREDIT_DAY_OVERDUE", T.IntegerType(), True),
            T.StructField("DAYS_CREDIT_ENDDATE", T.DoubleType(), True),
            T.StructField("DAYS_ENDDATE_FACT", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_MAX_OVERDUE", T.DoubleType(), True),
            T.StructField("CNT_CREDIT_PROLONG", T.IntegerType(), True),
            T.StructField("AMT_CREDIT_SUM", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_DEBT", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_LIMIT", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_OVERDUE", T.DoubleType(), True),
            T.StructField("CREDIT_TYPE", T.StringType(), True),
            T.StructField("DAYS_CREDIT_UPDATE", T.IntegerType(), True),
            T.StructField("AMT_ANNUITY", T.DoubleType(), True),
        ]
    )


def bureau_balance_csv_schema_spark() -> Any:
    """Return the explicit three-column ``bureau_balance.csv`` schema."""

    _, _, T = _spark_imports()
    return T.StructType(
        [
            T.StructField("SK_ID_BUREAU", T.IntegerType(), False),
            T.StructField("MONTHS_BALANCE", T.IntegerType(), False),
            T.StructField("STATUS", T.StringType(), True),
        ]
    )


def _require_columns_spark(frame: Any, columns: tuple[str, ...], context: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context}: missing columns {missing}")


def _assert_unique_spark_key(frame: Any, key_column: str, context: str) -> None:
    F, _, _ = _spark_imports()
    if frame.filter(F.col(key_column).isNull()).limit(1).count():
        raise ValueError(f"{context}: {key_column!r} contains null values.")
    if frame.groupBy(key_column).count().filter(F.col("count") > 1).limit(1).count():
        raise ValueError(f"{context}: {key_column!r} contains duplicate values.")


def _safe_divide_spark(numerator: Any, denominator: Any) -> Any:
    F, _, _ = _spark_imports()
    return F.when(
        denominator.isNotNull() & (denominator != F.lit(0.0)),
        numerator.cast("double") / denominator.cast("double"),
    ).otherwise(F.lit(None).cast("double"))


def _sum_zero(column: str) -> Any:
    F, _, _ = _spark_imports()
    return F.coalesce(F.sum(F.col(column)), F.lit(0))


def build_bureau_balance_features_spark(frame: Any) -> Any:
    """Collapse monthly rows to one explicit row per ``SK_ID_BUREAU``.

    ``STATUS == 'X'`` maps to null severity and ``IS_OBSERVED == 0``.  Recent
    features use the same inclusive six-month window as the pandas reference.
    """

    F, Window, _ = _spark_imports()
    _require_columns_spark(frame, BALANCE_REQUIRED_COLUMNS, "bureau_balance")

    severity = F.create_map(
        *[
            item
            for status, value in STATUS_SEVERITY.items()
            for item in (F.lit(status), F.lit(float(value)))
        ]
    )[F.col("STATUS")]
    derived = (
        frame.select(*BALANCE_REQUIRED_COLUMNS)
        .withColumn("STATUS_SEVERITY", severity.cast("double"))
        .withColumn(
            "IS_OBSERVED",
            F.when(F.col("STATUS_SEVERITY").isNotNull(), F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn(
            "IS_DPD",
            F.when(F.col("STATUS_SEVERITY") > F.lit(0.0), F.lit(1)).otherwise(F.lit(0)),
        )
    )

    order_window = Window.partitionBy(LOAN_KEY).orderBy("MONTHS_BALANCE")
    cumulative_window = order_window.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    streak_group = F.sum(
        F.when(F.col("IS_DPD") == 0, F.lit(1)).otherwise(F.lit(0))
    ).over(cumulative_window)
    with_runs = (
        derived.withColumn("_STREAK_GROUP", streak_group)
        .withColumn(
            "_DPD_STREAK",
            F.sum("IS_DPD").over(Window.partitionBy(LOAN_KEY, "_STREAK_GROUP")),
        )
        .withColumn("_PREVIOUS_DPD", F.lag("IS_DPD").over(order_window))
        .withColumn(
            "_DPD_EPISODE_START",
            F.when(
                (F.col("IS_DPD") == 1)
                & (F.coalesce(F.col("_PREVIOUS_DPD"), F.lit(0)) == 0),
                F.lit(1),
            ).otherwise(F.lit(0)),
        )
    )

    recent_condition = F.col("MONTHS_BALANCE") >= F.lit(-RECENT_BALANCE_MONTHS)
    aggregated = with_runs.groupBy(LOAN_KEY).agg(
        F.count("MONTHS_BALANCE").alias("BB_MONTHS_COUNT"),
        F.min("MONTHS_BALANCE").alias("BB_MONTHS_BALANCE_MIN"),
        F.avg("STATUS_SEVERITY").alias("BB_STATUS_MEAN"),
        F.max("STATUS_SEVERITY").alias("BB_STATUS_MAX"),
        F.sum("IS_DPD").alias("BB_DPD_MONTH_SUM"),
        F.sum("IS_OBSERVED").alias("BB_OBSERVED_MONTH_SUM"),
        F.avg(F.when(recent_condition, F.col("STATUS_SEVERITY"))).alias(
            "BB_RECENT_STATUS_MEAN"
        ),
        F.sum(F.when(recent_condition, F.col("IS_DPD"))).alias("BB_RECENT_DPD_SUM"),
        F.max("_DPD_STREAK").alias("BB_LONGEST_DPD_STREAK"),
        F.sum("_DPD_EPISODE_START").alias("BB_DPD_EPISODES"),
    )
    result = aggregated.withColumn(
        "BB_DPD_MONTH_SHARE",
        _safe_divide_spark(F.col("BB_DPD_MONTH_SUM"), F.col("BB_OBSERVED_MONTH_SUM")),
    ).select(LOAN_KEY, *BALANCE_FEATURE_NAMES)
    _assert_unique_spark_key(result, LOAN_KEY, "bureau_balance aggregate")
    return result


def build_bureau_features_spark(bureau: Any, bureau_balance_features: Any) -> Any:
    """Build the client-level Spark block with pandas-compatible semantics."""

    F, _, _ = _spark_imports()
    _require_columns_spark(bureau, BUREAU_REQUIRED_COLUMNS, "bureau")
    _require_columns_spark(
        bureau_balance_features,
        (LOAN_KEY, *BALANCE_FEATURE_NAMES),
        "bureau_balance aggregate",
    )
    _assert_unique_spark_key(bureau, LOAN_KEY, "bureau input")
    _assert_unique_spark_key(bureau_balance_features, LOAN_KEY, "bureau_balance aggregate")

    balance_selected = bureau_balance_features.select(LOAN_KEY, *BALANCE_FEATURE_NAMES)
    bureau_row_count = bureau.count()
    frame = bureau.select(*BUREAU_REQUIRED_COLUMNS).join(
        balance_selected,
        on=LOAN_KEY,
        how="left",
    )
    joined_row_count = frame.count()
    if joined_row_count != bureau_row_count:
        raise ValueError(
            "bureau_balance join changed the bureau row count: "
            f"{bureau_row_count} -> {joined_row_count}"
        )
    frame = (
        frame.withColumn(
            "IS_ACTIVE",
            F.when(F.col("CREDIT_ACTIVE") == "Active", F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn(
            "IS_CLOSED",
            F.when(F.col("CREDIT_ACTIVE") == "Closed", F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn(
            "HAS_OVERDUE",
            F.when(F.col("CREDIT_DAY_OVERDUE") > 0, F.lit(1)).otherwise(F.lit(0)),
        )
        .withColumn(
            "DEBT_CREDIT_RATIO",
            _safe_divide_spark(F.col("AMT_CREDIT_SUM_DEBT"), F.col("AMT_CREDIT_SUM")),
        )
        .withColumn(
            "OVERDUE_CREDIT_RATIO",
            _safe_divide_spark(F.col("AMT_CREDIT_SUM_OVERDUE"), F.col("AMT_CREDIT_SUM")),
        )
    )

    main = frame.groupBy(KEY_COLUMN).agg(
        F.max("DAYS_CREDIT").alias("BUREAU_DAYS_CREDIT_MAX"),
        F.min("DAYS_CREDIT").alias("BUREAU_DAYS_CREDIT_MIN"),
        F.avg("DAYS_CREDIT").alias("BUREAU_DAYS_CREDIT_MEAN"),
        F.max("DAYS_CREDIT_ENDDATE").alias("BUREAU_DAYS_CREDIT_ENDDATE_MAX"),
        F.min("DAYS_CREDIT_ENDDATE").alias("BUREAU_DAYS_CREDIT_ENDDATE_MIN"),
        F.max("CREDIT_DAY_OVERDUE").alias("BUREAU_CREDIT_DAY_OVERDUE_MAX"),
        F.avg("CREDIT_DAY_OVERDUE").alias("BUREAU_CREDIT_DAY_OVERDUE_MEAN"),
        F.sum("AMT_CREDIT_SUM").alias("BUREAU_AMT_CREDIT_SUM_SUM"),
        F.avg("AMT_CREDIT_SUM").alias("BUREAU_AMT_CREDIT_SUM_MEAN"),
        F.max("AMT_CREDIT_SUM").alias("BUREAU_AMT_CREDIT_SUM_MAX"),
        F.sum("AMT_CREDIT_SUM_DEBT").alias("BUREAU_AMT_CREDIT_SUM_DEBT_SUM"),
        F.avg("AMT_CREDIT_SUM_DEBT").alias("BUREAU_AMT_CREDIT_SUM_DEBT_MEAN"),
        F.max("AMT_CREDIT_SUM_DEBT").alias("BUREAU_AMT_CREDIT_SUM_DEBT_MAX"),
        F.sum("AMT_CREDIT_SUM_OVERDUE").alias("BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM"),
        F.max("AMT_CREDIT_SUM_OVERDUE").alias("BUREAU_AMT_CREDIT_SUM_OVERDUE_MAX"),
        F.sum("AMT_CREDIT_SUM_LIMIT").alias("BUREAU_AMT_CREDIT_SUM_LIMIT_SUM"),
        F.max("AMT_CREDIT_MAX_OVERDUE").alias("BUREAU_AMT_CREDIT_MAX_OVERDUE_MAX"),
        F.avg("AMT_CREDIT_MAX_OVERDUE").alias("BUREAU_AMT_CREDIT_MAX_OVERDUE_MEAN"),
        F.sum("AMT_ANNUITY").alias("BUREAU_AMT_ANNUITY_SUM"),
        F.avg("AMT_ANNUITY").alias("BUREAU_AMT_ANNUITY_MEAN"),
        _sum_zero("CNT_CREDIT_PROLONG").alias("BUREAU_CNT_CREDIT_PROLONG_SUM"),
        F.avg("DEBT_CREDIT_RATIO").alias("BUREAU_DEBT_CREDIT_RATIO_MEAN"),
        F.max("DEBT_CREDIT_RATIO").alias("BUREAU_DEBT_CREDIT_RATIO_MAX"),
        F.min("DEBT_CREDIT_RATIO").alias("BUREAU_DEBT_CREDIT_RATIO_MIN"),
        F.avg("OVERDUE_CREDIT_RATIO").alias("BUREAU_OVERDUE_CREDIT_RATIO_MEAN"),
        F.max("OVERDUE_CREDIT_RATIO").alias("BUREAU_OVERDUE_CREDIT_RATIO_MAX"),
        F.sum("IS_ACTIVE").alias("BUREAU_ACTIVE_SUM"),
        F.sum("IS_CLOSED").alias("BUREAU_CLOSED_SUM"),
        F.sum("HAS_OVERDUE").alias("BUREAU_HAS_OVERDUE_SUM"),
        F.avg("HAS_OVERDUE").alias("BUREAU_HAS_OVERDUE_MEAN"),
        F.count(LOAN_KEY).alias("BUREAU_LOAN_COUNT"),
        _sum_zero("BB_MONTHS_COUNT").alias("BUREAU_BB_MONTHS_TOTAL_SUM"),
        F.avg("BB_STATUS_MEAN").alias("BUREAU_BB_STATUS_MEAN_MEAN"),
        F.max("BB_STATUS_MEAN").alias("BUREAU_BB_STATUS_MEAN_MAX"),
        F.max("BB_STATUS_MAX").alias("BUREAU_BB_STATUS_WORST_MAX"),
        F.min("BB_MONTHS_BALANCE_MIN").alias("BUREAU_BB_MONTHS_BALANCE_MIN_MIN"),
        _sum_zero("BB_DPD_MONTH_SUM").alias("BUREAU_BB_DPD_MONTH_TOTAL_SUM"),
        F.avg("BB_DPD_MONTH_SHARE").alias("BUREAU_BB_DPD_MONTH_SHARE_MEAN"),
        F.max("BB_DPD_MONTH_SHARE").alias("BUREAU_BB_DPD_MONTH_SHARE_MAX"),
        F.max("BB_LONGEST_DPD_STREAK").alias("BUREAU_BB_LONGEST_DPD_STREAK_MAX"),
        F.avg("BB_LONGEST_DPD_STREAK").alias("BUREAU_BB_LONGEST_DPD_STREAK_MEAN"),
        F.max("BB_DPD_EPISODES").alias("BUREAU_BB_DPD_EPISODES_MAX"),
        _sum_zero("BB_DPD_EPISODES").alias("BUREAU_BB_DPD_EPISODES_SUM"),
        F.avg("BB_RECENT_STATUS_MEAN").alias("BUREAU_BB_RECENT_STATUS_MEAN_MEAN"),
        F.max("BB_RECENT_STATUS_MEAN").alias("BUREAU_BB_RECENT_STATUS_MEAN_MAX"),
        _sum_zero("BB_RECENT_DPD_SUM").alias("BUREAU_BB_RECENT_DPD_TOTAL_SUM"),
    )

    active = frame.filter(F.col("IS_ACTIVE") == 1).groupBy(KEY_COLUMN).agg(
        F.sum("AMT_CREDIT_SUM_DEBT").alias("BUREAU_ACTIVE_DEBT_SUM"),
        F.sum("AMT_CREDIT_SUM").alias("BUREAU_ACTIVE_CREDIT_SUM"),
        F.sum("AMT_CREDIT_SUM_LIMIT").alias("BUREAU_ACTIVE_LIMIT_SUM"),
        F.count(LOAN_KEY).alias("BUREAU_ACTIVE_LOAN_COUNT"),
    )
    result = main.join(active, on=KEY_COLUMN, how="left").fillna(
        0,
        subset=["BUREAU_ACTIVE_LOAN_COUNT"],
    )

    known_type = F.col("CREDIT_TYPE").isin(list(CREDIT_TYPES))
    type_expressions = [
        F.sum(F.when(F.col("CREDIT_TYPE") == value, 1).otherwise(0)).alias(
            f"BUREAU_CTYPE_{value}_COUNT"
        )
        for value in CREDIT_TYPES
    ]
    type_expressions.append(
        F.sum(F.when(~known_type | F.col("CREDIT_TYPE").isNull(), 1).otherwise(0)).alias(
            "BUREAU_CTYPE_OTHER_COUNT"
        )
    )
    credit_types = frame.groupBy(KEY_COLUMN).agg(*type_expressions)
    result = result.join(credit_types, on=KEY_COLUMN, how="left")

    loans_with_dpd = (
        frame.filter(F.col("BB_DPD_MONTH_SUM") > 0)
        .groupBy(KEY_COLUMN)
        .count()
        .withColumnRenamed("count", "BUREAU_LOANS_WITH_DPD_COUNT")
    )
    result = result.join(loans_with_dpd, on=KEY_COLUMN, how="left").fillna(
        0,
        subset=["BUREAU_LOANS_WITH_DPD_COUNT"],
    )
    result = (
        result.withColumn(
            "BUREAU_ACTIVE_LOAN_RATIO",
            _safe_divide_spark(
                F.col("BUREAU_ACTIVE_LOAN_COUNT"), F.col("BUREAU_LOAN_COUNT")
            ),
        )
        .withColumn(
            "BUREAU_ACTIVE_UTILIZATION",
            _safe_divide_spark(
                F.col("BUREAU_ACTIVE_DEBT_SUM"), F.col("BUREAU_ACTIVE_CREDIT_SUM")
            ),
        )
        .withColumn(
            "BUREAU_DEBT_CREDIT_RATIO_TOTAL",
            _safe_divide_spark(
                F.col("BUREAU_AMT_CREDIT_SUM_DEBT_SUM"),
                F.col("BUREAU_AMT_CREDIT_SUM_SUM"),
            ),
        )
        .withColumn(
            "BUREAU_OVERDUE_DEBT_RATIO_TOTAL",
            _safe_divide_spark(
                F.col("BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM"),
                F.col("BUREAU_AMT_CREDIT_SUM_DEBT_SUM"),
            ),
        )
        .select(KEY_COLUMN, *BUREAU_FEATURE_NAMES)
    )
    _assert_unique_spark_key(result, KEY_COLUMN, "bureau client aggregate")
    return result


def write_bureau_feature_block_spark(
    frame: Any,
    *,
    root: str | Path,
    name: str = "bureau_spark_candidate",
    builder_version: str = SPARK_BUILDER_VERSION,
) -> BlockManifest:
    """Write a non-overwriting Spark Parquet block and compatible manifest."""

    if builder_version != SPARK_BUILDER_VERSION:
        raise ValueError(
            f"Spark smoke builder_version must be {SPARK_BUILDER_VERSION!r}, "
            f"got {builder_version!r}."
        )
    if list(frame.columns) != [KEY_COLUMN, *BUREAU_FEATURE_NAMES]:
        raise ValueError("Spark Bureau output columns do not match the explicit contract.")
    _assert_unique_spark_key(frame, KEY_COLUMN, "Spark Bureau feature block")

    parquet_path, manifest_path = block_paths(root, name)
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite Spark candidate block: {parquet_path} / {manifest_path}"
        )
    row_count = frame.count()
    unique_key_count = frame.select(KEY_COLUMN).distinct().count()
    manifest = BlockManifest(
        name=name,
        key_column=KEY_COLUMN,
        builder_version=builder_version,
        feature_names=BUREAU_FEATURE_NAMES,
        families=BUREAU_FEATURE_FAMILIES,
        row_count=row_count,
        unique_key_count=unique_key_count,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write.mode("errorifexists").parquet(str(parquet_path))
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return manifest


__all__ = [
    "BALANCE_FEATURE_FAMILIES",
    "BALANCE_FEATURE_NAMES",
    "BUREAU_EXACT_FEATURE_NAMES",
    "BUREAU_FEATURE_FAMILIES",
    "BUREAU_FEATURE_NAMES",
    "SPARK_BUILDER_VERSION",
    "build_bureau_balance_features_spark",
    "build_bureau_features_spark",
    "bureau_balance_csv_schema_spark",
    "bureau_csv_schema_spark",
    "write_bureau_feature_block_spark",
]
