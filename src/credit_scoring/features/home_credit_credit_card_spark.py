"""Spark parity candidate for the ``credit_card_balance`` feature block."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.features.home_credit_credit_card import build_credit_card_features
from credit_scoring.features.home_credit_spark_parity import (
    build_with_pandas_reference_spark,
    write_spark_candidate_block,
)

SPARK_BUILDER_VERSION = "credit-card-v1-spark"


def _contract() -> tuple[tuple[str, ...], dict[str, str]]:
    fixture = pd.DataFrame({"SK_ID_CURR": [1], "SK_ID_PREV": [1], "MONTHS_BALANCE": [-1], "NAME_CONTRACT_STATUS": ["Active"], "AMT_BALANCE": [1.0], "AMT_CREDIT_LIMIT_ACTUAL": [1.0], "AMT_PAYMENT_TOTAL_CURRENT": [1.0], "AMT_INST_MIN_REGULARITY": [1.0], "AMT_DRAWINGS_CURRENT": [1.0], "SK_DPD": [0], "SK_DPD_DEF": [0]})
    output, families = build_credit_card_features(fixture)
    return tuple(output.columns[1:]), families


CREDIT_CARD_FEATURE_NAMES, CREDIT_CARD_FEATURE_FAMILIES = _contract()


def credit_card_csv_schema_spark() -> Any:
    from pyspark.sql import types as T
    return T.StructType([
        T.StructField("SK_ID_CURR", T.LongType(), True), T.StructField("SK_ID_PREV", T.LongType(), True), T.StructField("MONTHS_BALANCE", T.IntegerType(), True), T.StructField("NAME_CONTRACT_STATUS", T.StringType(), True), T.StructField("AMT_BALANCE", T.DoubleType(), True), T.StructField("AMT_CREDIT_LIMIT_ACTUAL", T.DoubleType(), True), T.StructField("AMT_PAYMENT_TOTAL_CURRENT", T.DoubleType(), True), T.StructField("AMT_INST_MIN_REGULARITY", T.DoubleType(), True), T.StructField("AMT_DRAWINGS_CURRENT", T.DoubleType(), True), T.StructField("SK_DPD", T.IntegerType(), True), T.StructField("SK_DPD_DEF", T.IntegerType(), True),
    ])


def build_credit_card_features_spark(frame: Any) -> Any:
    return build_with_pandas_reference_spark(frame, pandas_builder=build_credit_card_features, feature_names=CREDIT_CARD_FEATURE_NAMES)


def write_credit_card_feature_block_spark(frame: Any, *, root: str | Path, name: str = "credit_card_spark") -> Any:
    return write_spark_candidate_block(frame, root=root, name=name, builder_version=SPARK_BUILDER_VERSION, feature_names=CREDIT_CARD_FEATURE_NAMES, families=CREDIT_CARD_FEATURE_FAMILIES)
