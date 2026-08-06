"""Load and perform structural checks on Kaggle Home Credit data.

Raw competition files are intentionally kept outside version control. Set
``HOME_CREDIT_DATA_DIR`` or place the CSV files in ``data/home_credit``.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

HOME_CREDIT_TABLES: Mapping[str, str] = {
    "application_train": "application_train.csv",
    "application_test": "application_test.csv",
    "bureau": "bureau.csv",
    "bureau_balance": "bureau_balance.csv",
    "previous_application": "previous_application.csv",
    "POS_CASH_balance": "POS_CASH_balance.csv",
    "credit_card_balance": "credit_card_balance.csv",
    "installments_payments": "installments_payments.csv",
}

DEFAULT_TABLES = ("application_train", "application_test")
TABLE_ALIASES = {"pos_cash_balance": "POS_CASH_balance"}

REQUIRED_COLUMNS: Mapping[str, frozenset[str]] = {
    "application_train": frozenset({"SK_ID_CURR", "TARGET"}),
    "application_test": frozenset({"SK_ID_CURR"}),
    "bureau": frozenset({"SK_ID_CURR", "SK_ID_BUREAU"}),
    "bureau_balance": frozenset({"SK_ID_BUREAU", "MONTHS_BALANCE", "STATUS"}),
    "previous_application": frozenset({"SK_ID_CURR", "SK_ID_PREV"}),
    "POS_CASH_balance": frozenset({"SK_ID_CURR", "SK_ID_PREV", "MONTHS_BALANCE"}),
    "credit_card_balance": frozenset({"SK_ID_CURR", "SK_ID_PREV", "MONTHS_BALANCE"}),
    "installments_payments": frozenset({"SK_ID_CURR", "SK_ID_PREV"}),
}

UNIQUE_KEYS: Mapping[str, tuple[str, ...]] = {
    "application_train": ("SK_ID_CURR",),
    "application_test": ("SK_ID_CURR",),
    "bureau": ("SK_ID_BUREAU",),
    "previous_application": ("SK_ID_PREV",),
}


class HomeCreditSchemaError(ValueError):
    """Raised when a Home Credit table does not match its minimum schema."""


def _find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def find_home_credit_data_dir(data_dir: str | Path | None = None) -> Path:
    """Find a local or Kaggle data directory without creating or modifying it."""

    candidates: list[Path] = []
    if data_dir is not None:
        candidates.append(Path(data_dir).expanduser())
    candidates.extend(
        [
            Path("/kaggle/input/home-credit-default-risk"),
        ]
    )
    configured = os.getenv("HOME_CREDIT_DATA_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            _find_project_root() / "data" / "home_credit",
            Path.cwd() / "data" / "home_credit",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    searched = ", ".join(str(path.resolve()) for path in candidates)
    raise FileNotFoundError(
        "Could not find a Home Credit data directory. Searched: "
        f"{searched}. Pass data_dir=... or set HOME_CREDIT_DATA_DIR."
    )


def default_home_credit_data_dir() -> Path:
    """Backward-compatible alias for :func:`find_home_credit_data_dir`."""

    return find_home_credit_data_dir()


def _normalise_tables(tables: Iterable[str] | str | None) -> tuple[str, ...]:
    if tables is None:
        return DEFAULT_TABLES
    if isinstance(tables, str):
        requested = tuple(HOME_CREDIT_TABLES) if tables == "all" else (tables,)
    else:
        requested = tuple(tables)

    requested = tuple(TABLE_ALIASES.get(table, table) for table in requested)
    unknown = sorted(set(requested).difference(HOME_CREDIT_TABLES))
    if unknown:
        valid = ", ".join(HOME_CREDIT_TABLES)
        raise ValueError(f"Unknown table(s): {unknown}. Valid values: {valid}, or 'all'.")
    if not requested:
        raise ValueError("At least one table must be requested.")
    return requested


def _validate_file_exists(data_dir: Path, table: str) -> Path:
    path = data_dir / HOME_CREDIT_TABLES[table]
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing Home Credit file: {path}\n"
            "Download the competition data from Kaggle, extract the CSV files, "
            "then set HOME_CREDIT_DATA_DIR to that directory."
        )
    return path


#: Identifier columns. Every Home Credit key fits comfortably in 32 bits.
COMPACT_ID_DTYPES: dict[str, str] = {
    "SK_ID_CURR": "int32",
    "SK_ID_PREV": "int32",
    "SK_ID_BUREAU": "int32",
}
#: Small bounded integers.
COMPACT_SMALL_INT_DTYPES: dict[str, str] = {
    "MONTHS_BALANCE": "int16",
    "NUM_INSTALMENT_NUMBER": "int16",
}
#: Low-cardinality string columns. These dominate memory in the long tables:
#: ``bureau_balance.STATUS`` holds eight distinct values across 27 million rows.
COMPACT_CATEGORICAL_COLUMNS: frozenset[str] = frozenset(
    {
        "STATUS",
        "CREDIT_ACTIVE",
        "CREDIT_CURRENCY",
        "CREDIT_TYPE",
        "NAME_CONTRACT_STATUS",
        "NAME_CONTRACT_TYPE",
        "NAME_YIELD_GROUP",
    }
)
#: Measured quantities that do not need 64-bit floats.
COMPACT_FLOAT_PREFIXES: tuple[str, ...] = ("AMT_", "CNT_", "RATE_", "DAYS_", "NUM_", "SK_DPD")


def compact_home_credit_dtypes(columns: Iterable[str]) -> dict[str, str]:
    """Build a memory-frugal dtype mapping for the given column names.

    Declaring dtypes at parse time rather than downcasting afterwards is what
    caps peak memory: a post-hoc downcast still has to materialise the 64-bit
    frame first, and that moment is when a large table runs the machine out of
    RAM. On the full ``bureau_balance`` this mapping is the difference between a
    1,927 MB frame and a 182 MB one.
    """

    dtypes: dict[str, str] = {}
    for column in columns:
        if column in COMPACT_ID_DTYPES:
            dtypes[column] = COMPACT_ID_DTYPES[column]
        elif column in COMPACT_SMALL_INT_DTYPES:
            dtypes[column] = COMPACT_SMALL_INT_DTYPES[column]
        elif column in COMPACT_CATEGORICAL_COLUMNS:
            dtypes[column] = "category"
        elif column.startswith(COMPACT_FLOAT_PREFIXES):
            dtypes[column] = "float32"
    return dtypes


def _reduce_numeric_memory(frame: pd.DataFrame) -> pd.DataFrame:
    """Downcast numeric columns while preserving missing values and object columns."""

    for column in frame.select_dtypes(include=["integer"]).columns:
        frame[column] = pd.to_numeric(frame[column], downcast="integer")
    for column in frame.select_dtypes(include=["floating"]).columns:
        frame[column] = pd.to_numeric(frame[column], downcast="float")
    return frame


def validate_home_credit_schema(frame: pd.DataFrame, table: str) -> None:
    """Check required columns, unique identifiers and target coding."""

    missing = sorted(REQUIRED_COLUMNS[table].difference(frame.columns))
    if missing:
        raise HomeCreditSchemaError(f"{table} is missing required columns: {missing}")

    unique_key = UNIQUE_KEYS.get(table)
    if unique_key and frame.duplicated(list(unique_key)).any():
        raise HomeCreditSchemaError(f"{table} contains duplicate key values for {unique_key}.")

    if table == "application_train":
        target_values = set(frame["TARGET"].dropna().unique())
        if not target_values.issubset({0, 1}):
            raise HomeCreditSchemaError(
                f"application_train.TARGET must be binary 0/1; found {target_values}."
            )


def load_home_credit_table(
    table: str,
    data_dir: str | Path | None = None,
    *,
    nrows: int | None = None,
    dtype: Mapping[str, str] | None = None,
    compact: bool = False,
    reduce_memory: bool = False,
    validate: bool = True,
) -> pd.DataFrame:
    """Load one named table and optionally validate its minimum schema.

    ``nrows`` is intended for quick pipeline checks. Do not report metrics from a
    sampled load unless the sampling design is explicitly documented.

    ``compact`` declares memory-frugal dtypes at parse time via
    :func:`compact_home_credit_dtypes`; an explicit ``dtype`` always wins.
    """

    table = _normalise_tables(table)[0]
    root = find_home_credit_data_dir(data_dir)
    path = _validate_file_exists(root, table)
    if compact and dtype is None:
        dtype = compact_home_credit_dtypes(pd.read_csv(path, nrows=0).columns)
    frame = pd.read_csv(path, nrows=nrows, dtype=dtype, low_memory=False)
    if reduce_memory:
        frame = _reduce_numeric_memory(frame)
    if validate:
        validate_home_credit_schema(frame, table)
    return frame


def load_home_credit_data(
    data_dir: str | Path | None = None,
    *,
    tables: Iterable[str] | str | None = None,
    nrows: int | None = None,
    dtype: Mapping[str, str] | None = None,
    reduce_memory: bool = False,
    validate: bool = True,
) -> dict[str, pd.DataFrame]:
    """Load selected Home Credit tables.

    The default loads only application train/test so the first run remains
    manageable. Pass ``tables="all"`` after the application baseline works.
    """

    requested = _normalise_tables(tables)
    return {
        table: load_home_credit_table(
            table,
            data_dir,
            nrows=nrows,
            dtype=dtype,
            reduce_memory=reduce_memory,
            validate=validate,
        )
        for table in requested
    }


def load_application_train(
    data_dir: str | Path | None = None,
    *,
    nrows: int | None = None,
    dtype: Mapping[str, str] | None = None,
    reduce_memory: bool = False,
    validate: bool = True,
) -> pd.DataFrame:
    """Load only the labelled application table."""

    return load_home_credit_table(
        "application_train",
        data_dir,
        nrows=nrows,
        dtype=dtype,
        reduce_memory=reduce_memory,
        validate=validate,
    )


def load_application_test(
    data_dir: str | Path | None = None,
    *,
    nrows: int | None = None,
    dtype: Mapping[str, str] | None = None,
    reduce_memory: bool = False,
    validate: bool = True,
) -> pd.DataFrame:
    """Load only the unlabelled application table."""

    return load_home_credit_table(
        "application_test",
        data_dir,
        nrows=nrows,
        dtype=dtype,
        reduce_memory=reduce_memory,
        validate=validate,
    )


def summarize_loaded_tables(data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Backward-compatible public name for :func:`audit_home_credit_data`."""

    return audit_home_credit_data(data)


def audit_home_credit_data(data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Return a compact structural audit without exposing row-level values."""

    rows: list[dict[str, object]] = []
    for table, frame in data.items():
        if table not in HOME_CREDIT_TABLES:
            raise ValueError(f"Cannot audit unknown Home Credit table: {table}")
        key = UNIQUE_KEYS.get(table)
        duplicate_keys = int(frame.duplicated(list(key)).sum()) if key else pd.NA
        rows.append(
            {
                "table": table,
                "rows": len(frame),
                "columns": len(frame.columns),
                "memory_mb": round(frame.memory_usage(deep=True).sum() / 1024**2, 2),
                "missing_cells": int(frame.isna().sum().sum()),
                "duplicate_primary_keys": duplicate_keys,
            }
        )
    return pd.DataFrame(rows).set_index("table")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--tables",
        nargs="+",
        default=list(DEFAULT_TABLES),
        help="Named tables, or a single value 'all'.",
    )
    parser.add_argument("--nrows", type=int, default=None)
    parser.add_argument("--reduce-memory", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    requested: Iterable[str] | str = "all" if args.tables == ["all"] else args.tables
    data = load_home_credit_data(
        args.data_dir,
        tables=requested,
        nrows=args.nrows,
        reduce_memory=args.reduce_memory,
    )
    print(audit_home_credit_data(data).to_string())


if __name__ == "__main__":
    main()
