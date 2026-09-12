"""Spark parity candidate for the ``previous_application`` feature block."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.features.home_credit_previous_application import (
    CONTRACT_TYPES,
    RECENT_REFUSAL_DAYS,
    TREND_APPLICATIONS,
    YIELD_GROUPS,
    build_previous_application_features,
)
from credit_scoring.features.home_credit_spark_parity import (
    write_spark_candidate_block,
)

SPARK_BUILDER_VERSION = "previous-application-v1-spark"


def _contract() -> tuple[tuple[str, ...], dict[str, str]]:
    fixture = pd.DataFrame(
        {
            "SK_ID_CURR": [1],
            "SK_ID_PREV": [1],
            "NAME_CONTRACT_STATUS": ["Approved"],
            "NAME_CONTRACT_TYPE": ["Cash loans"],
            "NAME_YIELD_GROUP": ["high"],
            "AMT_CREDIT": [1.0],
            "AMT_APPLICATION": [1.0],
            "AMT_ANNUITY": [1.0],
            "AMT_DOWN_PAYMENT": [1.0],
            "AMT_GOODS_PRICE": [1.0],
            "RATE_DOWN_PAYMENT": [1.0],
            "DAYS_DECISION": [-1],
            "CNT_PAYMENT": [1.0],
        }
    )
    output, families = build_previous_application_features(fixture)
    return tuple(output.columns[1:]), families


PREVIOUS_APPLICATION_FEATURE_NAMES, PREVIOUS_APPLICATION_FEATURE_FAMILIES = _contract()


def previous_application_csv_schema_spark() -> Any:
    """Explicit schema for precisely the raw columns used by the reference."""
    from pyspark.sql import types as T

    return T.StructType(
        [
            T.StructField("SK_ID_CURR", T.LongType(), True),
            T.StructField("SK_ID_PREV", T.LongType(), True),
            T.StructField("NAME_CONTRACT_STATUS", T.StringType(), True),
            T.StructField("NAME_CONTRACT_TYPE", T.StringType(), True),
            T.StructField("NAME_YIELD_GROUP", T.StringType(), True),
            T.StructField("AMT_CREDIT", T.DoubleType(), True),
            T.StructField("AMT_APPLICATION", T.DoubleType(), True),
            T.StructField("AMT_ANNUITY", T.DoubleType(), True),
            T.StructField("AMT_DOWN_PAYMENT", T.DoubleType(), True),
            T.StructField("AMT_GOODS_PRICE", T.DoubleType(), True),
            T.StructField("RATE_DOWN_PAYMENT", T.DoubleType(), True),
            T.StructField("DAYS_DECISION", T.IntegerType(), True),
            T.StructField("CNT_PAYMENT", T.DoubleType(), True),
        ]
    )


def build_previous_application_features_spark(frame: Any) -> Any:
    """Build the locked previous-application contract with Spark aggregations."""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    def divide(numerator: Any, denominator: Any) -> Any:
        return F.when(denominator.isNull() | (denominator == 0), F.lit(None)).otherwise(
            numerator / denominator
        )

    derived = (
        frame.withColumn("IS_APPROVED", (F.col("NAME_CONTRACT_STATUS") == "Approved").cast("int"))
        .withColumn("IS_REFUSED", (F.col("NAME_CONTRACT_STATUS") == "Refused").cast("int"))
        .withColumn("IS_CANCELLED", (F.col("NAME_CONTRACT_STATUS") == "Canceled").cast("int"))
        .withColumn("AMT_DIFF_APPLICATION_CREDIT", F.col("AMT_APPLICATION") - F.col("AMT_CREDIT"))
        .withColumn(
            "DOWN_PAYMENT_RATIO", divide(F.col("AMT_DOWN_PAYMENT"), F.col("AMT_GOODS_PRICE"))
        )
        .withColumn("LOAN_TO_PRICE", divide(F.col("AMT_CREDIT"), F.col("AMT_GOODS_PRICE")))
    )
    main = derived.groupBy("SK_ID_CURR").agg(
        F.count("SK_ID_PREV").alias("PREV_APPLICATION_COUNT"),
        F.sum("IS_APPROVED").alias("PREV_APPROVED_SUM"),
        F.avg("IS_APPROVED").alias("PREV_APPROVED_MEAN"),
        F.sum("IS_REFUSED").alias("PREV_REFUSED_SUM"),
        F.avg("IS_REFUSED").alias("PREV_REFUSED_MEAN"),
        F.sum("IS_CANCELLED").alias("PREV_CANCELLED_SUM"),
        F.avg("IS_CANCELLED").alias("PREV_CANCELLED_MEAN"),
        F.sum("AMT_CREDIT").alias("PREV_AMT_CREDIT_SUM"),
        F.avg("AMT_CREDIT").alias("PREV_AMT_CREDIT_MEAN"),
        F.max("AMT_CREDIT").alias("PREV_AMT_CREDIT_MAX"),
        F.avg("AMT_APPLICATION").alias("PREV_AMT_APPLICATION_MEAN"),
        F.max("AMT_APPLICATION").alias("PREV_AMT_APPLICATION_MAX"),
        F.avg("AMT_ANNUITY").alias("PREV_AMT_ANNUITY_MEAN"),
        F.max("AMT_ANNUITY").alias("PREV_AMT_ANNUITY_MAX"),
        F.avg("AMT_DIFF_APPLICATION_CREDIT").alias("PREV_AMT_DIFF_APPLICATION_CREDIT_MEAN"),
        F.max("AMT_DIFF_APPLICATION_CREDIT").alias("PREV_AMT_DIFF_APPLICATION_CREDIT_MAX"),
        F.min("AMT_DIFF_APPLICATION_CREDIT").alias("PREV_AMT_DIFF_APPLICATION_CREDIT_MIN"),
        F.avg("DOWN_PAYMENT_RATIO").alias("PREV_DOWN_PAYMENT_RATIO_MEAN"),
        F.max("DOWN_PAYMENT_RATIO").alias("PREV_DOWN_PAYMENT_RATIO_MAX"),
        F.avg("RATE_DOWN_PAYMENT").alias("PREV_RATE_DOWN_PAYMENT_MEAN"),
        F.max("RATE_DOWN_PAYMENT").alias("PREV_RATE_DOWN_PAYMENT_MAX"),
        F.avg("LOAN_TO_PRICE").alias("PREV_LOAN_TO_PRICE_MEAN"),
        F.max("LOAN_TO_PRICE").alias("PREV_LOAN_TO_PRICE_MAX"),
        F.max("DAYS_DECISION").alias("PREV_DAYS_DECISION_MAX"),
        F.min("DAYS_DECISION").alias("PREV_DAYS_DECISION_MIN"),
        F.avg("DAYS_DECISION").alias("PREV_DAYS_DECISION_MEAN"),
        F.avg("CNT_PAYMENT").alias("PREV_CNT_PAYMENT_MEAN"),
        F.max("CNT_PAYMENT").alias("PREV_CNT_PAYMENT_MAX"),
    )
    approved = (
        derived.filter(F.col("IS_APPROVED") == 1)
        .groupBy("SK_ID_CURR")
        .agg(
            F.max("AMT_CREDIT").alias("PREV_HIST_CREDIT_MAX"),
            F.avg("AMT_CREDIT").alias("PREV_HIST_CREDIT_MEAN"),
            F.max("AMT_ANNUITY").alias("PREV_HIST_ANNUITY_MAX"),
        )
    )
    refusal = (
        derived.filter(
            (F.col("IS_REFUSED") == 1) & (F.col("DAYS_DECISION") >= -RECENT_REFUSAL_DAYS)
        )
        .groupBy("SK_ID_CURR")
        .count()
        .withColumnRenamed("count", "PREV_RECENT_REFUSAL_COUNT")
    )
    ranked = derived.withColumn(
        "rank",
        F.row_number().over(
            Window.partitionBy("SK_ID_CURR").orderBy(F.col("DAYS_DECISION").desc())
        ),
    ).filter(F.col("rank") <= TREND_APPLICATIONS)
    trend_rows = ranked.filter(F.col("AMT_APPLICATION").isNotNull()).withColumn(
        "position",
        F.row_number().over(Window.partitionBy("SK_ID_CURR").orderBy(F.col("DAYS_DECISION")))
        - 1,
    )
    stats = trend_rows.groupBy("SK_ID_CURR").agg(
        F.count("AMT_APPLICATION").alias("n"),
        F.sum("position").alias("sum_x"),
        F.sum("AMT_APPLICATION").alias("sum_y"),
        F.sum(F.col("position") * F.col("AMT_APPLICATION")).alias("sum_xy"),
        F.sum(F.col("position") * F.col("position")).alias("sum_xx"),
    )
    trend = stats.select(
        "SK_ID_CURR",
        F.when(F.col("n") < 2, F.lit(None))
        .otherwise(
            (F.col("n") * F.col("sum_xy") - F.col("sum_x") * F.col("sum_y"))
            / (F.col("n") * F.col("sum_xx") - F.col("sum_x") * F.col("sum_x"))
        )
        .alias("PREV_AMT_APPLICATION_TREND"),
    )
    result = (
        main.join(approved, "SK_ID_CURR", "left")
        .join(refusal, "SK_ID_CURR", "left")
        .join(trend, "SK_ID_CURR", "left")
        .fillna(0, subset=["PREV_RECENT_REFUSAL_COUNT"])
    )
    for column, values, prefix in (
        ("NAME_CONTRACT_TYPE", CONTRACT_TYPES, "PREV_CONTRACT_"),
        ("NAME_YIELD_GROUP", YIELD_GROUPS, "PREV_YIELD_"),
    ):
        expressions = [
            F.sum(F.when(F.col(column) == value, 1).otherwise(0)).alias(f"{prefix}{value}_COUNT")
            for value in values
        ]
        expressions.append(
            F.sum(
                F.when(~F.col(column).isin(list(values)) | F.col(column).isNull(), 1).otherwise(0)
            ).alias(f"{prefix}OTHER_COUNT")
        )
        result = result.join(derived.groupBy("SK_ID_CURR").agg(*expressions), "SK_ID_CURR", "left")
    return result.withColumn(
        "PREV_HAS_RECENT_REFUSAL", (F.col("PREV_RECENT_REFUSAL_COUNT") > 0).cast("int")
    ).select("SK_ID_CURR", *PREVIOUS_APPLICATION_FEATURE_NAMES)


def write_previous_application_feature_block_spark(
    frame: Any, *, root: str | Path, name: str = "previous_application_spark"
) -> Any:
    return write_spark_candidate_block(
        frame,
        root=root,
        name=name,
        builder_version=SPARK_BUILDER_VERSION,
        feature_names=PREVIOUS_APPLICATION_FEATURE_NAMES,
        families=PREVIOUS_APPLICATION_FEATURE_FAMILIES,
    )
