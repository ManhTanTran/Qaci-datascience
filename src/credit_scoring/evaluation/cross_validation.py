"""Cross-validation utilities kept independent of any model implementation."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.model_selection import StratifiedKFold


def create_stratified_folds(
    target: Sequence[int] | np.ndarray,
    *,
    n_splits: int = 5,
    shuffle: bool = True,
    random_state: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Create reproducible stratified train/validation index pairs."""

    y = np.asarray(target)
    if y.ndim != 1:
        raise ValueError("Target must be one-dimensional.")
    if not set(np.unique(y)).issubset({0, 1}):
        raise ValueError("Target must contain only binary values 0/1.")
    splitter = StratifiedKFold(
        n_splits=n_splits,
        shuffle=shuffle,
        random_state=random_state if shuffle else None,
    )
    return list(splitter.split(np.zeros(len(y)), y))


def validate_oof_coverage(
    oof_predictions: Sequence[float] | np.ndarray,
    target: Sequence[int] | np.ndarray,
    validation_counts: Sequence[int] | np.ndarray,
) -> None:
    """Raise when OOF predictions are not present exactly once per row."""

    oof = np.asarray(oof_predictions, dtype=float)
    y = np.asarray(target)
    counts = np.asarray(validation_counts, dtype=int)
    if oof.ndim != 1 or len(oof) != len(y):
        raise ValueError("OOF predictions must be one-dimensional and match target length.")
    if counts.ndim != 1 or len(counts) != len(y):
        raise ValueError("Validation counts must be one-dimensional and match target length.")
    if not np.all(counts == 1):
        raise ValueError("Each sample must receive exactly one OOF validation prediction.")
    if not np.isfinite(oof).all():
        raise ValueError("OOF predictions contain missing or infinite values.")
    if ((oof < 0) | (oof > 1)).any():
        raise ValueError("OOF predictions must be probabilities in [0, 1].")
