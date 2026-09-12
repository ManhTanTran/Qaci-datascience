"""Spark parity candidate for the ``installments_payments`` feature block."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.features.home_credit_installments import build_installments_features
from credit_scoring.features.home_credit_spark_parity import (
    build_with_pandas_reference_spark,
    write_spark_candidate_block,
)

SPARK_BUILDER_VERSION = "installments-v1-spark"


def _contract() -> tuple[tuple[str, ...], dict[str, str]]:
    fixture = pd.DataFrame({"SK_ID_CURR": [1], "SK_ID_PREV": [1], "NUM_INSTALMENT_NUMBER": [1], "DAYS_INSTALMENT": [-1.0], "DAYS_ENTRY_PAYMENT": [-1.0], "AMT_INSTALMENT": [1.0], "AMT_PAYMENT": [1.0]})
    output, families = build_installments_features(fixture)
    return tuple(output.columns[1:]), families


INSTALLMENTS_FEATURE_NAMES, INSTALLMENTS_FEATURE_FAMILIES = _contract()


def installments_csv_schema_spark() -> Any:
    from pyspark.sql import types as T
    return T.StructType([
        T.StructField("SK_ID_CURR", T.LongType(), True), T.StructField("SK_ID_PREV", T.LongType(), True), T.StructField("NUM_INSTALMENT_NUMBER", T.IntegerType(), True), T.StructField("DAYS_INSTALMENT", T.DoubleType(), True), T.StructField("DAYS_ENTRY_PAYMENT", T.DoubleType(), True), T.StructField("AMT_INSTALMENT", T.DoubleType(), True), T.StructField("AMT_PAYMENT", T.DoubleType(), True),
    ])


def build_installments_features_spark(frame: Any) -> Any:
    return build_with_pandas_reference_spark(frame, pandas_builder=build_installments_features, feature_names=INSTALLMENTS_FEATURE_NAMES)


def write_installments_feature_block_spark(frame: Any, *, root: str | Path, name: str = "installments_spark") -> Any:
    return write_spark_candidate_block(frame, root=root, name=name, builder_version=SPARK_BUILDER_VERSION, feature_names=INSTALLMENTS_FEATURE_NAMES, families=INSTALLMENTS_FEATURE_FAMILIES)
