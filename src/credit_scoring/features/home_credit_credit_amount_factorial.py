"""Factorial decomposition of the Home Credit E02 credit/amount family."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from credit_scoring.features.home_credit_application import (
    build_e01_application_features,
)
from credit_scoring.numeric import safe_divide

FACTOR_NORMALIZE = "N"
FACTOR_CREDIT_ANNUITY = "R"
FACTOR_CREDIT_GOODS_DIFF = "D"
CREDIT_AMOUNT_FACTOR_ORDER: tuple[str, ...] = (
    FACTOR_NORMALIZE,
    FACTOR_CREDIT_ANNUITY,
    FACTOR_CREDIT_GOODS_DIFF,
)

NORMALIZED_RATIO_FORMULAS: dict[str, tuple[str, str]] = {
    "CREDIT_INCOME_RATIO": ("AMT_CREDIT", "AMT_INCOME_TOTAL"),
    "ANNUITY_INCOME_RATIO": ("AMT_ANNUITY", "AMT_INCOME_TOTAL"),
    "GOODS_CREDIT_RATIO": ("AMT_GOODS_PRICE", "AMT_CREDIT"),
    "INCOME_PER_PERSON": ("AMT_INCOME_TOTAL", "CNT_FAM_MEMBERS"),
}
NORMALIZED_RATIO_COLUMNS: tuple[str, ...] = tuple(NORMALIZED_RATIO_FORMULAS)
FACTOR_ADDED_COLUMNS: dict[str, tuple[str, ...]] = {
    FACTOR_NORMALIZE: (),
    FACTOR_CREDIT_ANNUITY: ("CREDIT_ANNUITY_RATIO",),
    FACTOR_CREDIT_GOODS_DIFF: ("CREDIT_GOODS_DIFF",),
}

CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS: dict[str, tuple[str, ...]] = {
    "E01_LOCKED": (),
    "E02-N": (FACTOR_NORMALIZE,),
    "E02-R": (FACTOR_CREDIT_ANNUITY,),
    "E02-D": (FACTOR_CREDIT_GOODS_DIFF,),
    "E02-RD": (FACTOR_CREDIT_ANNUITY, FACTOR_CREDIT_GOODS_DIFF),
    "E02-NR": (FACTOR_NORMALIZE, FACTOR_CREDIT_ANNUITY),
    "E02-ND": (FACTOR_NORMALIZE, FACTOR_CREDIT_GOODS_DIFF),
    "E02-NRD": CREDIT_AMOUNT_FACTOR_ORDER,
}


@dataclass(frozen=True)
class CreditAmountFactorSpec:
    """Canonical feature changes enabled by one factorial configuration."""

    factors: tuple[str, ...]
    added_columns: tuple[str, ...]
    overwritten_columns: tuple[str, ...]


def normalise_credit_amount_factors(factors: Iterable[str] | None) -> tuple[str, ...]:
    """Validate factors and return deterministic N/R/D ordering."""

    requested = tuple(factors or ())
    unknown = sorted(set(requested).difference(CREDIT_AMOUNT_FACTOR_ORDER))
    if unknown:
        raise ValueError(f"Unknown credit/amount factors: {unknown}")
    if len(requested) != len(set(requested)):
        raise ValueError("Credit/amount factors must be unique.")
    return tuple(factor for factor in CREDIT_AMOUNT_FACTOR_ORDER if factor in requested)


def describe_credit_amount_factors(
    factors: Iterable[str] | None,
) -> CreditAmountFactorSpec:
    """Describe additions and explicit overwrites for one factor set."""

    resolved = normalise_credit_amount_factors(factors)
    added = tuple(
        column
        for factor in CREDIT_AMOUNT_FACTOR_ORDER
        if factor in resolved
        for column in FACTOR_ADDED_COLUMNS[factor]
    )
    overwritten = NORMALIZED_RATIO_COLUMNS if FACTOR_NORMALIZE in resolved else ()
    return CreditAmountFactorSpec(resolved, added, overwritten)


def _float32_difference(left: pd.Series, right: pd.Series) -> pd.Series:
    values = pd.to_numeric(left, errors="coerce") - pd.to_numeric(right, errors="coerce")
    return values.astype("float32").replace([np.inf, -np.inf], np.nan)


def build_credit_amount_factorial_features(
    frame: pd.DataFrame,
    *,
    factors: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Build locked E01 plus explicit N/R/D changes in deterministic order."""

    spec = describe_credit_amount_factors(factors)
    result = build_e01_application_features(frame)

    if FACTOR_NORMALIZE in spec.factors:
        for feature, (numerator, denominator) in NORMALIZED_RATIO_FORMULAS.items():
            if feature not in result.columns:
                raise ValueError(f"Cannot explicitly overwrite missing E01 feature: {feature}")
            result[feature] = safe_divide(result[numerator], result[denominator])

    if FACTOR_CREDIT_ANNUITY in spec.factors:
        feature = FACTOR_ADDED_COLUMNS[FACTOR_CREDIT_ANNUITY][0]
        if feature in result.columns:
            raise ValueError(f"Refusing to overwrite existing feature while adding {feature}.")
        result[feature] = safe_divide(result["AMT_CREDIT"], result["AMT_ANNUITY"])

    if FACTOR_CREDIT_GOODS_DIFF in spec.factors:
        feature = FACTOR_ADDED_COLUMNS[FACTOR_CREDIT_GOODS_DIFF][0]
        if feature in result.columns:
            raise ValueError(f"Refusing to overwrite existing feature while adding {feature}.")
        result[feature] = _float32_difference(result["AMT_CREDIT"], result["AMT_GOODS_PRICE"])

    numeric = result.select_dtypes(include="number")
    if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Credit/amount factorial features contain infinite values.")
    return result


def build_aligned_credit_amount_factorial_features(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    factors: Sequence[str] | None = None,
    target_column: str = "TARGET",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one deterministic N/R/D schema for application train and test."""

    train_columns = [column for column in train_frame.columns if column != target_column]
    if set(train_columns) != set(test_frame.columns):
        train_only = sorted(set(train_columns).difference(test_frame.columns))
        test_only = sorted(set(test_frame.columns).difference(train_columns))
        raise ValueError(
            "Train/test application schemas differ: "
            f"train_only={train_only}, test_only={test_only}"
        )
    train_features = build_credit_amount_factorial_features(
        train_frame[train_columns], factors=factors
    )
    test_features = build_credit_amount_factorial_features(
        test_frame[train_columns], factors=factors
    )
    if list(train_features.columns) != list(test_features.columns):
        raise ValueError("Factorial train/test columns differ in name or order.")
    return train_features, test_features


def summarize_feature_matrix_differences(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    explicitly_overwritten: Sequence[str] = (),
) -> pd.DataFrame:
    """Report additions and explicit overwrites, rejecting any silent mutation."""

    if len(reference) != len(candidate) or not reference.index.equals(candidate.index):
        raise ValueError("Feature matrices must have identical rows and index for comparison.")
    removed = [column for column in reference if column not in candidate]
    if removed:
        raise ValueError(f"Candidate removed reference columns: {removed}")
    added = [column for column in candidate if column not in reference]
    overwritten = tuple(explicitly_overwritten)
    unknown_overwrites = sorted(set(overwritten).difference(reference.columns))
    if unknown_overwrites:
        raise ValueError(f"Explicit overwrite columns are absent from reference: {unknown_overwrites}")

    rows: list[dict[str, object]] = []
    silently_changed: list[str] = []
    for column in reference.columns:
        left = reference[column]
        right = candidate[column]
        equal = left.eq(right) | (left.isna() & right.isna())
        rows_different = int((~equal).sum())
        dtype_changed = left.dtype != right.dtype
        if (rows_different or dtype_changed) and column not in overwritten:
            silently_changed.append(column)
        if column not in overwritten:
            continue
        max_difference = np.nan
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            valid = left.notna() & right.notna()
            if valid.any():
                differences = (
                    pd.to_numeric(left[valid], errors="coerce").astype("float64")
                    - pd.to_numeric(right[valid], errors="coerce").astype("float64")
                ).abs()
                max_difference = float(differences.max())
        rows.append(
            {
                "feature": column,
                "change_type": "overwritten",
                "reference_dtype": str(left.dtype),
                "candidate_dtype": str(right.dtype),
                "dtype_changed": bool(dtype_changed),
                "rows_value_different": rows_different,
                "max_abs_numeric_difference": max_difference,
            }
        )
    if silently_changed:
        raise ValueError(f"Candidate silently changed E01 features: {silently_changed}")

    for column in added:
        rows.append(
            {
                "feature": column,
                "change_type": "added",
                "reference_dtype": None,
                "candidate_dtype": str(candidate[column].dtype),
                "dtype_changed": False,
                "rows_value_different": pd.NA,
                "max_abs_numeric_difference": np.nan,
            }
        )
    return pd.DataFrame(rows)
