"""Metrics used by the Home Credit competition pipeline."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.metrics import roc_auc_score


def validate_prediction_array(
    predictions: Sequence[float] | np.ndarray,
    expected_length: int | None = None,
) -> np.ndarray:
    """Validate binary-probability predictions and return a flat float array."""

    values = np.asarray(predictions, dtype=float)
    if values.ndim != 1:
        raise ValueError(f"Predictions must be one-dimensional; got shape {values.shape}.")
    if expected_length is not None and len(values) != expected_length:
        raise ValueError(f"Expected {expected_length} predictions; got {len(values)}.")
    if not np.isfinite(values).all():
        raise ValueError("Predictions contain NaN or infinite values.")
    if ((values < 0) | (values > 1)).any():
        raise ValueError("Predictions must be probabilities in [0, 1].")
    return values


def calculate_roc_auc(
    target: Sequence[int] | np.ndarray,
    predictions: Sequence[float] | np.ndarray,
) -> float:
    """Calculate ROC-AUC after validating target and prediction arrays."""

    y_true = np.asarray(target)
    if y_true.ndim != 1:
        raise ValueError("Target must be one-dimensional.")
    if len(y_true) != len(predictions):
        raise ValueError("Target and predictions must have equal length.")
    if not np.isfinite(y_true).all() or not set(np.unique(y_true)).issubset({0, 1}):
        raise ValueError("Target must contain only finite binary values 0/1.")
    values = validate_prediction_array(predictions, expected_length=len(y_true))
    if len(np.unique(y_true)) < 2:
        raise ValueError("ROC-AUC requires both target classes.")
    return float(roc_auc_score(y_true, values))
