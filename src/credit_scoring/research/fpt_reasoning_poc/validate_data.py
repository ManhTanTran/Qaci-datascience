from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .common import PROCESSED_DIR, RAW_DIR, ensure_directories, is_missing, number_or_none

SOURCE_FILE = RAW_DIR / "FPT_credit_scoring_synthetic_10_cases.xlsx"
SHEET_NAME = "Synthetic_Customers"

REQUIRED_COLUMNS = {
    "user_id",
    "age_group",
    "city",
    "avg_monthly_income",
    "district",
    "payment_month_count_12M",
    "is_late_sum_12M",
    "total_late_day_max_12M",
    "telco_monetary_sum_12M",
}


def validate_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing_columns = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing_columns:
        errors.append({"type": "missing_columns", "columns": missing_columns})

    if "user_id" in frame:
        duplicated = frame.loc[frame["user_id"].duplicated(keep=False), "user_id"].tolist()
        if duplicated:
            errors.append({"type": "duplicate_user_id", "values": duplicated})

    range_checks = {
        "is_late_mean_3M": (0, 1),
        "is_late_mean_6M": (0, 1),
        "is_late_mean_12M": (0, 1),
        "is_late_mean_ALL": (0, 1),
        "is_late_sum_12M": (0, 12),
        "payment_month_count_12M": (0, 12),
        "total_late_day_max_12M": (0, 366),
        "telco_monetary_sum_12M": (0, 1_000_000_000),
        "telco_monetary_mean_12M": (0, 100_000_000),
        "telco_monetary_trend": (0, 10),
    }
    for column, (minimum, maximum) in range_checks.items():
        if column not in frame:
            continue
        for index, value in frame[column].items():
            if is_missing(value):
                continue
            if number_or_none(value, minimum=minimum, maximum=maximum) is None:
                warnings.append({
                    "type": "invalid_range",
                    "row": int(index),
                    "user_id": str(frame.at[index, "user_id"]),
                    "column": column,
                    "value": str(value),
                    "expected": f"{minimum}..{maximum}",
                })

    if {"is_late_sum_12M", "payment_month_count_12M"}.issubset(frame.columns):
        for index, row in frame.iterrows():
            late = number_or_none(row["is_late_sum_12M"], minimum=0, maximum=12)
            observed = number_or_none(row["payment_month_count_12M"], minimum=0, maximum=12)
            if late is not None and observed is not None and late > observed:
                warnings.append({
                    "type": "late_months_exceed_observed_months",
                    "row": int(index),
                    "user_id": str(row["user_id"]),
                    "late_months": late,
                    "observed_months": observed,
                })

    return {
        "source": str(SOURCE_FILE),
        "sheet": SHEET_NAME,
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "errors": errors,
        "warnings": warnings,
        "valid_for_profile_build": not errors,
    }


def run(source: Path = SOURCE_FILE) -> tuple[pd.DataFrame, dict[str, Any]]:
    ensure_directories()
    if not source.exists():
        raise FileNotFoundError(
            f"Thiếu dữ liệu nguồn: {source}. Chạy `python -m src.prepare_data --zip <path>` trước."
        )
    frame = pd.read_excel(source, sheet_name=SHEET_NAME)
    report = validate_dataframe(frame)
    report["source"] = str(source)
    report_path = PROCESSED_DIR / "validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return frame, report


def main() -> None:
    _, report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid_for_profile_build"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
