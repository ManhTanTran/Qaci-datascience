"""Contract and optional runtime tests for the Spark Bureau candidate."""

from __future__ import annotations

import importlib.util
import json

import numpy as np
import pandas as pd
import pytest

from credit_scoring.features.home_credit_bureau import (
    build_bureau_balance_features,
    build_bureau_features,
)
from credit_scoring.features.home_credit_bureau_spark import (
    BALANCE_FEATURE_FAMILIES,
    BALANCE_FEATURE_NAMES,
    BUREAU_FEATURE_FAMILIES,
    BUREAU_FEATURE_NAMES,
    build_bureau_balance_features_spark,
    build_bureau_features_spark,
    write_bureau_feature_block_spark,
)

KEY = "SK_ID_CURR"
LOAN_KEY = "SK_ID_BUREAU"


def make_bureau() -> pd.DataFrame:
    return pd.DataFrame(
        {
            KEY: [1, 1, 2, 3],
            LOAN_KEY: [10, 11, 12, 13],
            "CREDIT_ACTIVE": ["Active", "Closed", "Active", "Closed"],
            "CREDIT_TYPE": ["Credit card", "Car loan", "Mortgage", None],
            "DAYS_CREDIT": [-100, -900, -30, -400],
            "DAYS_CREDIT_ENDDATE": [200.0, -700.0, 100.0, -300.0],
            "CREDIT_DAY_OVERDUE": [0, 12, 0, 0],
            "AMT_CREDIT_SUM": [1000.0, 0.0, 5000.0, 800.0],
            "AMT_CREDIT_SUM_DEBT": [400.0, 100.0, 2500.0, np.nan],
            "AMT_CREDIT_SUM_OVERDUE": [0.0, 50.0, 0.0, np.nan],
            "AMT_CREDIT_SUM_LIMIT": [-10.0, 0.0, 1000.0, np.nan],
            "AMT_CREDIT_MAX_OVERDUE": [0.0, 75.0, np.nan, np.nan],
            "AMT_ANNUITY": [np.nan, np.nan, 300.0, np.nan],
            "CNT_CREDIT_PROLONG": [0, 1, 0, 0],
        }
    )


def make_bureau_balance() -> pd.DataFrame:
    return pd.DataFrame(
        {
            LOAN_KEY: [10, 10, 10, 10, 11, 11, 11, 12],
            "MONTHS_BALANCE": [-1, -2, -3, -4, -1, -2, -3, -1],
            "STATUS": ["0", "1", "3", "X", "C", "5", "X", "0"],
        }
    )


def test_explicit_schema_and_family_contract_matches_pandas_reference() -> None:
    reference, reference_families = build_bureau_features(
        make_bureau(), make_bureau_balance()
    )
    balance = build_bureau_balance_features(make_bureau_balance())

    assert list(BUREAU_FEATURE_NAMES) == list(reference.columns[1:])
    assert BUREAU_FEATURE_FAMILIES == reference_families
    assert list(BALANCE_FEATURE_NAMES) == list(balance.columns[1:])
    assert set(BALANCE_FEATURE_FAMILIES) == set(BALANCE_FEATURE_NAMES)


def test_declared_spark_schema_is_independent_of_available_subset() -> None:
    full, full_families = build_bureau_features(make_bureau(), make_bureau_balance())
    subset_bureau = make_bureau().loc[lambda frame: frame[KEY].eq(1)]
    subset_balance = make_bureau_balance().loc[lambda frame: frame[LOAN_KEY].isin([10, 11])]
    subset, subset_families = build_bureau_features(subset_bureau, subset_balance)

    assert list(full.columns[1:]) == list(subset.columns[1:]) == list(BUREAU_FEATURE_NAMES)
    assert full_families == subset_families == BUREAU_FEATURE_FAMILIES


@pytest.fixture(scope="module")
def spark():
    if importlib.util.find_spec("pyspark") is None:
        pytest.skip("PySpark is not installed; Spark runtime parity tests require PySpark.")
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[2]")
        .appName("credit-scoring-bureau-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


def _spark_bureau(spark):
    from pyspark.sql import types as T

    schema = T.StructType(
        [
            T.StructField(KEY, T.IntegerType(), False),
            T.StructField(LOAN_KEY, T.IntegerType(), False),
            T.StructField("CREDIT_ACTIVE", T.StringType(), True),
            T.StructField("CREDIT_TYPE", T.StringType(), True),
            T.StructField("DAYS_CREDIT", T.IntegerType(), True),
            T.StructField("DAYS_CREDIT_ENDDATE", T.DoubleType(), True),
            T.StructField("CREDIT_DAY_OVERDUE", T.IntegerType(), True),
            T.StructField("AMT_CREDIT_SUM", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_DEBT", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_OVERDUE", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_SUM_LIMIT", T.DoubleType(), True),
            T.StructField("AMT_CREDIT_MAX_OVERDUE", T.DoubleType(), True),
            T.StructField("AMT_ANNUITY", T.DoubleType(), True),
            T.StructField("CNT_CREDIT_PROLONG", T.IntegerType(), True),
        ]
    )
    frame = make_bureau().replace({np.nan: None})
    return spark.createDataFrame(list(frame.itertuples(index=False, name=None)), schema=schema)


def _spark_balance(spark):
    from pyspark.sql import types as T

    schema = T.StructType(
        [
            T.StructField(LOAN_KEY, T.IntegerType(), False),
            T.StructField("MONTHS_BALANCE", T.IntegerType(), False),
            T.StructField("STATUS", T.StringType(), True),
        ]
    )
    frame = make_bureau_balance()
    return spark.createDataFrame(list(frame.itertuples(index=False, name=None)), schema=schema)


def _spark_outputs(spark):
    balance = build_bureau_balance_features_spark(_spark_balance(spark))
    clients = build_bureau_features_spark(_spark_bureau(spark), balance)
    return balance, clients


def test_spark_intermediate_and_final_keys_are_unique(spark) -> None:
    balance, clients = _spark_outputs(spark)

    assert balance.count() == balance.select(LOAN_KEY).distinct().count()
    assert clients.count() == clients.select(KEY).distinct().count()


def test_spark_x_is_unobserved_and_dpd_share_uses_observed_denominator(spark) -> None:
    balance, _ = _spark_outputs(spark)
    loan = balance.filter(f"{LOAN_KEY} = 10").first().asDict()

    assert loan["BB_MONTHS_COUNT"] == 4
    assert loan["BB_OBSERVED_MONTH_SUM"] == 3
    assert loan["BB_DPD_MONTH_SUM"] == 2
    assert loan["BB_DPD_MONTH_SHARE"] == pytest.approx(2 / 3)


def test_spark_all_null_amount_and_invalid_ratios_remain_null(spark) -> None:
    _, clients = _spark_outputs(spark)
    client = clients.filter(f"{KEY} = 3").first().asDict()

    assert client["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"] is None
    assert client["BUREAU_AMT_ANNUITY_SUM"] is None
    assert client["BUREAU_DEBT_CREDIT_RATIO_MEAN"] is None
    assert client["BUREAU_OVERDUE_DEBT_RATIO_TOTAL"] is None


def test_spark_schema_is_identical_on_different_subsets(spark) -> None:
    balance, full = _spark_outputs(spark)
    subset_bureau = _spark_bureau(spark).filter(f"{KEY} = 1")
    subset = build_bureau_features_spark(subset_bureau, balance)

    assert full.columns == subset.columns == [KEY, *BUREAU_FEATURE_NAMES]


def test_spark_and_pandas_match_on_deterministic_fixture(spark) -> None:
    _, candidate_spark = _spark_outputs(spark)
    candidate = candidate_spark.toPandas().sort_values(KEY).reset_index(drop=True)
    reference, families = build_bureau_features(make_bureau(), make_bureau_balance())
    reference = reference.sort_values(KEY).reset_index(drop=True)

    assert candidate.columns.tolist() == reference.columns.tolist()
    assert families == BUREAU_FEATURE_FAMILIES
    assert candidate[KEY].is_unique
    assert not np.isinf(candidate.select_dtypes(include="number").to_numpy()).any()

    for column in BUREAU_FEATURE_NAMES:
        left = pd.to_numeric(reference[column], errors="coerce").to_numpy(dtype="float64")
        right = pd.to_numeric(candidate[column], errors="coerce").to_numpy(dtype="float64")
        np.testing.assert_allclose(left, right, rtol=1e-5, atol=1e-6, equal_nan=True)


def test_spark_candidate_manifest_is_compatible_and_never_overwritten(
    spark, tmp_path
) -> None:
    _, clients = _spark_outputs(spark)

    manifest = write_bureau_feature_block_spark(clients, root=tmp_path)
    payload = json.loads(
        (tmp_path / "bureau_spark_candidate.manifest.json").read_text(encoding="utf-8")
    )

    assert manifest.feature_names == BUREAU_FEATURE_NAMES
    assert dict(manifest.families) == BUREAU_FEATURE_FAMILIES
    assert payload["builder_version"] == "bureau-v1-spark-smoke"
    assert (tmp_path / "bureau_spark_candidate.parquet").is_dir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_bureau_feature_block_spark(clients, root=tmp_path)
