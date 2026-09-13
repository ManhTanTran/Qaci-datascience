"""Input inspection and loading for CSV/Excel application uploads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.reasoning.mapping import load_feature_mapping


@dataclass(frozen=True)
class InputInspection:
    """Metadata shown by the upload screen and carried into source traces."""

    file_name: str
    file_type: str
    row_count: int
    column_count: int
    sheet_names: tuple[str, ...]
    selected_sheet: str | None
    detected_users: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_type": self.file_type,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "sheet_names": list(self.sheet_names),
            "selected_sheet": self.selected_sheet,
            "detected_users": list(self.detected_users),
        }


def _sheet_choice(sheets: dict[str, pd.DataFrame], mapping: dict[str, Any]) -> str:
    preferred = mapping.get("source", {}).get("sheet_preference", "Synthetic_Customers")
    if preferred in sheets:
        return preferred
    declared = {
        column
        for spec in mapping["fields"].values()
        for column in spec["raw_columns"]
    }
    return max(sheets, key=lambda name: len(declared.intersection(sheets[name].columns)))


def _read_csv(path: Path, mapping: dict[str, Any]) -> pd.DataFrame:
    id_column = mapping.get("source", {}).get("id_column", "user_id")
    dtype = {id_column: "string"}
    return pd.read_csv(path, dtype=dtype)


def load_input(
    path: str | Path,
    *,
    sheet: str | None = None,
    mapping: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, InputInspection]:
    """Load an input and select the semantic source sheet.

    Excel's ``Prompt_View`` is intentionally never preferred over
    ``Synthetic_Customers``.  For a non-FPT workbook, the sheet with the most
    declared source columns is selected and the choice is surfaced in metadata.
    """

    input_path = Path(path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path.resolve()}")
    resolved_mapping = mapping or load_feature_mapping()
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        frame = _read_csv(input_path, resolved_mapping)
        sheet_names: tuple[str, ...] = ()
        selected_sheet = None
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        sheets = pd.read_excel(input_path, sheet_name=None)
        if not sheets:
            raise ValueError("Excel workbook contains no sheets.")
        selected_sheet = sheet or _sheet_choice(sheets, resolved_mapping)
        if selected_sheet not in sheets:
            raise ValueError(
                f"Unknown sheet {selected_sheet!r}; available sheets: {list(sheets)}"
            )
        frame = sheets[selected_sheet].copy()
        sheet_names = tuple(str(name) for name in sheets)
    else:
        raise ValueError("Only .xlsx, .xlsm, .xls and .csv inputs are supported.")
    if frame.empty:
        raise ValueError("Selected input sheet is empty.")
    id_column = resolved_mapping.get("source", {}).get("id_column", "user_id")
    detected_users = (
        tuple(frame[id_column].dropna().astype(str).tolist()) if id_column in frame else ()
    )
    inspection = InputInspection(
        file_name=input_path.name,
        file_type=suffix.lstrip("."),
        row_count=len(frame),
        column_count=len(frame.columns),
        sheet_names=sheet_names,
        selected_sheet=selected_sheet,
        detected_users=detected_users,
    )
    frame.attrs["source_file"] = str(input_path)
    frame.attrs["source_sheet"] = selected_sheet
    return frame, inspection


def inspect_input(
    path: str | Path,
    *,
    sheet: str | None = None,
    mapping: dict[str, Any] | None = None,
) -> InputInspection:
    """Inspect an input using the same selection logic as :func:`load_input`."""

    return load_input(path, sheet=sheet, mapping=mapping)[1]
