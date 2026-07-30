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
