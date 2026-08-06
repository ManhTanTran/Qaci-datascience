from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from credit_scoring.data.home_credit import (
    HomeCreditSchemaError,
    audit_home_credit_data,
    load_home_credit_data,
    load_home_credit_table,
)


def _write_application_files(data_dir: Path) -> None:
    pd.DataFrame(
        {
            "SK_ID_CURR": [100001, 100002, 100003],
            "TARGET": [0, 1, 0],
            "AMT_CREDIT": [100_000.0, 200_000.0, None],
        }
    ).to_csv(data_dir / "application_train.csv", index=False)
    pd.DataFrame(
        {
            "SK_ID_CURR": [200001, 200002],
            "AMT_CREDIT": [150_000.0, 250_000.0],
        }
    ).to_csv(data_dir / "application_test.csv", index=False)


def test_load_default_application_tables(tmp_path: Path) -> None:
    _write_application_files(tmp_path)

    data = load_home_credit_data(tmp_path)

    assert set(data) == {"application_train", "application_test"}
    assert len(data["application_train"]) == 3
    assert data["application_train"]["SK_ID_CURR"].is_unique


def test_load_table_respects_nrows(tmp_path: Path) -> None:
    _write_application_files(tmp_path)

    frame = load_home_credit_table("application_train", tmp_path, nrows=2)

    assert len(frame) == 2


def test_missing_file_error_names_expected_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="application_train.csv"):
        load_home_credit_table("application_train", tmp_path)


def test_schema_validation_rejects_non_binary_target(tmp_path: Path) -> None:
    pd.DataFrame({"SK_ID_CURR": [1], "TARGET": [2]}).to_csv(
        tmp_path / "application_train.csv",
        index=False,
    )

    with pytest.raises(HomeCreditSchemaError, match="binary 0/1"):
        load_home_credit_table("application_train", tmp_path)


def test_schema_validation_rejects_duplicate_application_key(tmp_path: Path) -> None:
    pd.DataFrame({"SK_ID_CURR": [1, 1], "TARGET": [0, 1]}).to_csv(
        tmp_path / "application_train.csv",
        index=False,
    )

    with pytest.raises(HomeCreditSchemaError, match="duplicate key"):
        load_home_credit_table("application_train", tmp_path)


def test_audit_reports_only_structural_statistics(tmp_path: Path) -> None:
    _write_application_files(tmp_path)
    data = load_home_credit_data(tmp_path)

    audit = audit_home_credit_data(data)

    assert audit.loc["application_train", "rows"] == 3
    assert audit.loc["application_train", "duplicate_primary_keys"] == 0
    assert audit.loc["application_train", "missing_cells"] == 1


def test_compact_dtypes_cover_ids_categories_and_measures() -> None:
    from credit_scoring.data.home_credit import compact_home_credit_dtypes

    dtypes = compact_home_credit_dtypes(
        [
            "SK_ID_CURR",
            "SK_ID_BUREAU",
            "MONTHS_BALANCE",
            "STATUS",
            "AMT_CREDIT_SUM",
            "DAYS_CREDIT",
            "SK_DPD_DEF",
            "TARGET",
            "UNKNOWN_COLUMN",
        ]
    )

    assert dtypes["SK_ID_CURR"] == "int32"
    assert dtypes["SK_ID_BUREAU"] == "int32"
    assert dtypes["MONTHS_BALANCE"] == "int16"
    assert dtypes["STATUS"] == "category"
    assert dtypes["AMT_CREDIT_SUM"] == "float32"
    assert dtypes["DAYS_CREDIT"] == "float32"
    assert dtypes["SK_DPD_DEF"] == "float32"
    # Columns the mapping does not recognise are left for pandas to infer, and
    # TARGET in particular must not be coerced away from its integer coding.
    assert "TARGET" not in dtypes
    assert "UNKNOWN_COLUMN" not in dtypes


def test_load_home_credit_table_applies_compact_dtypes(tmp_path) -> None:
    from credit_scoring.data.home_credit import load_home_credit_table

    frame = pd.DataFrame(
        {
            "SK_ID_BUREAU": [10, 11],
            "MONTHS_BALANCE": [-1, -2],
            "STATUS": ["C", "0"],
        }
    )
    frame.to_csv(tmp_path / "bureau_balance.csv", index=False)

    loaded = load_home_credit_table(
        "bureau_balance", tmp_path, compact=True, validate=False
    )

    assert loaded["SK_ID_BUREAU"].dtype == "int32"
    assert loaded["MONTHS_BALANCE"].dtype == "int16"
    assert str(loaded["STATUS"].dtype) == "category"


def test_explicit_dtype_overrides_compact(tmp_path) -> None:
    from credit_scoring.data.home_credit import load_home_credit_table

    pd.DataFrame({"SK_ID_BUREAU": [10], "MONTHS_BALANCE": [-1], "STATUS": ["C"]}).to_csv(
        tmp_path / "bureau_balance.csv", index=False
    )

    loaded = load_home_credit_table(
        "bureau_balance",
        tmp_path,
        compact=True,
        dtype={"SK_ID_BUREAU": "int64"},
        validate=False,
    )

    assert loaded["SK_ID_BUREAU"].dtype == "int64"
