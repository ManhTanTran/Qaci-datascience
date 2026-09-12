"""Shared Spark adapter for parity candidates backed by a pandas reference.

The adapter keeps the raw table in Spark and invokes the existing, tested pandas
builder per ``SK_ID_CURR`` through ``applyInPandas``.  It is intentionally a
research/parity bridge: it gives an exact semantic reference for a later fully
vectorised Spark rewrite without collecting the raw auxiliary table on the
driver.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.feature_store import BlockManifest, block_paths

KEY_COLUMN = "SK_ID_CURR"
PandasBuilder = Callable[[pd.DataFrame], tuple[pd.DataFrame, dict[str, str]]]


def _spark_types() -> tuple[Any, Any]:
    try:
        from pyspark.sql import functions, types
    except ImportError as error:  # pragma: no cover - exercised on Spark hosts.
        raise RuntimeError("PySpark is required to run a Spark parity builder.") from error
    return functions, types


def _assert_unique_key(frame: Any, key_column: str, label: str) -> None:
    duplicates = frame.groupBy(key_column).count().filter("count > 1").limit(1).count()
    if duplicates:
        raise ValueError(f"{label}: {key_column} is not unique.")


def spark_feature_schema(feature_names: tuple[str, ...]) -> Any:
    """Return the stable client-level schema shared by every parity builder."""

    _, types = _spark_types()
    return types.StructType(
        [types.StructField(KEY_COLUMN, types.LongType(), nullable=False)]
        + [types.StructField(name, types.DoubleType(), nullable=True) for name in feature_names]
    )


def build_with_pandas_reference_spark(
    frame: Any,
    *,
    pandas_builder: PandasBuilder,
    feature_names: tuple[str, ...],
) -> Any:
    """Build a Spark client block without collecting raw auxiliary rows.

    Each Arrow batch contains a single client's rows only.  The selected pandas
    builder is the locked semantic reference, so output names, order, missing
    policy and category handling remain identical while the table is read and
    partitioned by Spark.
    """

    _spark_types()
    if KEY_COLUMN not in frame.columns:
        raise ValueError(f"Raw Spark frame is missing {KEY_COLUMN!r}.")

    schema = spark_feature_schema(feature_names)

    def build_one_client(pdf: pd.DataFrame) -> pd.DataFrame:
        output, _ = pandas_builder(pdf)
        if len(output) != 1 or not output[KEY_COLUMN].is_unique:
            raise ValueError("Reference builder did not return exactly one client row.")
        return output.reindex(columns=[KEY_COLUMN, *feature_names]).astype(
            {name: "float64" for name in feature_names}, copy=False
        )

    result = frame.groupBy(KEY_COLUMN).applyInPandas(build_one_client, schema=schema)
    _assert_unique_key(result, KEY_COLUMN, "Spark parity client aggregate")
    return result.select(KEY_COLUMN, *feature_names)


def write_spark_candidate_block(
    frame: Any,
    *,
    root: str | Path,
    name: str,
    builder_version: str,
    feature_names: tuple[str, ...],
    families: dict[str, str],
) -> BlockManifest:
    """Write a non-overwriting candidate block plus a feature-store manifest."""

    expected_columns = [KEY_COLUMN, *feature_names]
    if list(frame.columns) != expected_columns:
        raise ValueError(f"{name}: output columns do not match the explicit contract.")
    _assert_unique_key(frame, KEY_COLUMN, f"{name} Spark candidate")
    parquet_path, manifest_path = block_paths(root, name)
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite candidate block {name!r}.")

    row_count = frame.count()
    manifest = BlockManifest(
        name=name,
        key_column=KEY_COLUMN,
        builder_version=builder_version,
        feature_names=feature_names,
        families=families,
        row_count=row_count,
        unique_key_count=frame.select(KEY_COLUMN).distinct().count(),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write.mode("errorifexists").parquet(str(parquet_path))
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return manifest
