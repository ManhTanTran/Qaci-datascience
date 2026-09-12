"""Spark parity candidate for the ``POS_CASH_balance`` feature block."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.features.home_credit_pos_cash import build_pos_cash_features
from credit_scoring.features.home_credit_spark_parity import (
    build_with_pandas_reference_spark,
    write_spark_candidate_block,
)

SPARK_BUILDER_VERSION = "pos-cash-v1-spark"


def _contract() -> tuple[tuple[str, ...], dict[str, str]]:
    fixture = pd.DataFrame({"SK_ID_CURR": [1], "SK_ID_PREV": [1], "MONTHS_BALANCE": [-1], "NAME_CONTRACT_STATUS": ["Active"], "CNT_INSTALMENT": [1.0], "CNT_INSTALMENT_FUTURE": [0.0], "SK_DPD": [0], "SK_DPD_DEF": [0]})
    output, families = build_pos_cash_features(fixture)
    return tuple(output.columns[1:]), families


POS_CASH_FEATURE_NAMES, POS_CASH_FEATURE_FAMILIES = _contract()


def pos_cash_csv_schema_spark() -> Any:
    from pyspark.sql import types as T
    return T.StructType([
        T.StructField("SK_ID_CURR", T.LongType(), True), T.StructField("SK_ID_PREV", T.LongType(), True), T.StructField("MONTHS_BALANCE", T.IntegerType(), True), T.StructField("NAME_CONTRACT_STATUS", T.StringType(), True), T.StructField("CNT_INSTALMENT", T.DoubleType(), True), T.StructField("CNT_INSTALMENT_FUTURE", T.DoubleType(), True), T.StructField("SK_DPD", T.IntegerType(), True), T.StructField("SK_DPD_DEF", T.IntegerType(), True),
    ])


def build_pos_cash_features_spark(frame: Any) -> Any:
    return build_with_pandas_reference_spark(frame, pandas_builder=build_pos_cash_features, feature_names=POS_CASH_FEATURE_NAMES)


def write_pos_cash_feature_block_spark(frame: Any, *, root: str | Path, name: str = "pos_cash_spark") -> Any:
    return write_spark_candidate_block(frame, root=root, name=name, builder_version=SPARK_BUILDER_VERSION, feature_names=POS_CASH_FEATURE_NAMES, families=POS_CASH_FEATURE_FAMILIES)
