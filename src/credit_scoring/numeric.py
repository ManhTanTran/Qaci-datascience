"""Generic numeric helpers shared across credit-scoring datasets."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _float32_series(values: pd.Series) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").astype("float32")
    return result.replace([np.inf, -np.inf], np.nan)


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide aligned series, returning float32 NaN for invalid divisions."""

    aligned_numerator, aligned_denominator = numerator.align(denominator, join="left")
    numerator_values = _float32_series(aligned_numerator)
    denominator_values = _float32_series(aligned_denominator)
    valid = denominator_values.notna() & denominator_values.ne(0)
    result = pd.Series(np.nan, index=numerator_values.index, dtype="float32")
    result.loc[valid] = numerator_values.loc[valid] / denominator_values.loc[valid]
    return result.replace([np.inf, -np.inf], np.nan).astype("float32")
