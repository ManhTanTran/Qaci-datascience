"""Home Credit submission validation and export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from credit_scoring.evaluation.metrics import validate_prediction_array


def create_home_credit_submission(
    test_ids: pd.Series,
    predictions: object,
    output_path: str | Path,
) -> Path:
    """Validate and write the exact Kaggle schema."""

    ids = pd.Series(test_ids).reset_index(drop=True)
    if ids.isna().any():
        raise ValueError("SK_ID_CURR contains missing values.")
    if ids.duplicated().any():
        raise ValueError("SK_ID_CURR contains duplicate values.")
    values = validate_prediction_array(predictions, expected_length=len(ids))
    submission = pd.DataFrame({"SK_ID_CURR": ids, "TARGET": values})
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    submission.to_csv(path, index=False)
    return path.resolve()
