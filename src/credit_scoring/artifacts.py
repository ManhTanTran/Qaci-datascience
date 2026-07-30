"""Small, explicit artifact writers for experiment outputs."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import pandas as pd


def _prepare_output_path(output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def export_json_artifact(payload: Any, output_path: str | Path) -> Path:
    """Write JSON metadata and return the resolved path."""

    path = _prepare_output_path(output_path)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path.resolve()


def export_dataframe_artifact(frame: pd.DataFrame, output_path: str | Path) -> Path:
    """Write a DataFrame as CSV and return the resolved path."""

    path = _prepare_output_path(output_path)
    frame.to_csv(path, index=False)
    return path.resolve()


def export_pickle_artifact(payload: Any, output_path: str | Path) -> Path:
    """Write a Python object as a pickle artifact."""

    path = _prepare_output_path(output_path)
    with path.open("wb") as handle:
        pickle.dump(payload, handle)
    return path.resolve()
