"""Preparation and selection helpers for Home Credit credit/amount factorial runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from credit_scoring.experiments.home_credit_application import PreparedApplicationData
from credit_scoring.features.home_credit_application import build_e02_application_features
from credit_scoring.features.home_credit_credit_amount_factorial import (
    CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS,
    NORMALIZED_RATIO_COLUMNS,
    build_aligned_credit_amount_factorial_features,
    build_credit_amount_factorial_features,
    describe_credit_amount_factors,
    summarize_feature_matrix_differences,
)


@dataclass(frozen=True)
class E02FinalSelection:
    """Named E02-FINAL configuration selected from measured full-data results."""

    name: str
    source_experiment: str
    factors: tuple[str, ...]
    oof_auc: float
    positive_fold_count: int
    std_fold_auc: float


def resolve_credit_amount_factorial_experiments(
    selected: Sequence[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return all eight canonical experiments in deterministic order."""

    requested = list(CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS if selected is None else selected)
    unknown = sorted(set(requested).difference(CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS))
    if unknown:
        raise ValueError(f"Unknown credit/amount factorial experiments: {unknown}")
    if len(requested) != len(set(requested)):
        raise ValueError("Factorial experiment names must be unique.")
    if "E01_LOCKED" not in requested:
        raise ValueError("Factorial experiment set requires E01_LOCKED.")
    return {
        name: CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS[name]
        for name in CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS
        if name in requested
    }


def prepare_credit_amount_factorial_data(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    factors: Sequence[str] | None = None,
) -> PreparedApplicationData:
    """Build aligned factor features and one shared categorical vocabulary."""

    required_train = {"SK_ID_CURR", "TARGET"}
    required_test = {"SK_ID_CURR"}
    if missing := sorted(required_train.difference(train_frame.columns)):
        raise ValueError(f"application_train is missing columns: {missing}")
    if missing := sorted(required_test.difference(test_frame.columns)):
        raise ValueError(f"application_test is missing columns: {missing}")
    if not train_frame["TARGET"].isin([0, 1]).all():
        raise ValueError("TARGET must contain only 0/1 values.")
    train_featured, test_featured = build_aligned_credit_amount_factorial_features(
        train_frame,
        test_frame,
        factors=factors,
    )
    train_ids = train_featured.pop("SK_ID_CURR").copy()
    test_ids = test_featured.pop("SK_ID_CURR").copy()
    target = train_frame["TARGET"].astype("int8").copy()

    combined = pd.concat([train_featured, test_featured], axis=0, ignore_index=True)
    categorical = tuple(combined.select_dtypes(include=["object", "string"]).columns)
    for column in categorical:
        combined[column] = combined[column].astype("category")
    train_features = combined.iloc[: len(train_featured)].copy()
    test_features = combined.iloc[len(train_featured) :].copy().reset_index(drop=True)
    if list(train_features.columns) != list(test_features.columns):
        raise ValueError("Prepared factorial train/test columns differ in name or order.")
    return PreparedApplicationData(
        train_features=train_features,
        test_features=test_features,
        target=target,
        train_ids=train_ids,
        test_ids=test_ids,
        categorical_features=categorical,
    )


def compare_e01_to_current_e02_a(frame: pd.DataFrame) -> pd.DataFrame:
    """Diagnose current E02-A additions, overwrites, dtypes and value changes."""

    e01 = build_credit_amount_factorial_features(frame, factors=())
    e02_a = build_e02_application_features(frame, families=("ratios",))
    return summarize_feature_matrix_differences(
        e01,
        e02_a,
        explicitly_overwritten=NORMALIZED_RATIO_COLUMNS,
    )


def nrd_reproduces_current_e02_a(frame: pd.DataFrame) -> bool:
    """Return whether E02-NRD exactly matches the current E02-A feature matrix."""

    nrd = build_credit_amount_factorial_features(frame, factors=("N", "R", "D"))
    e02_a = build_e02_application_features(frame, families=("ratios",))
    if list(nrd.columns) != list(e02_a.columns):
        return False
    if not nrd.dtypes.equals(e02_a.dtypes):
        return False
    for column in nrd.columns:
        equal = nrd[column].eq(e02_a[column]) | (nrd[column].isna() & e02_a[column].isna())
        if not bool(equal.all()):
            return False
    return True


def select_e02_final(
    summary: pd.DataFrame,
    *,
    n_splits: int,
    tie_tolerance: float = 1e-5,
    max_std_increase: float = 5e-4,
) -> E02FinalSelection | None:
    """Select E02-FINAL from measured baseline results using conservative rules."""

    required = {
        "experiment",
        "oof_auc",
        "std_fold_auc",
        "positive_fold_count_vs_e01",
        "n_features",
        "n_overwritten_features",
    }
    missing = sorted(required.difference(summary.columns))
    if missing:
        raise ValueError(f"Factorial summary is missing selection columns: {missing}")
    baseline_rows = summary.loc[summary["experiment"].eq("E01_LOCKED")]
    if len(baseline_rows) != 1:
        raise ValueError("Factorial summary must contain exactly one E01_LOCKED row.")
    baseline = baseline_rows.iloc[0]
    minimum_positive_folds = max(1, int(np.ceil(0.8 * n_splits)))
    candidates = summary.loc[~summary["experiment"].eq("E01_LOCKED")].copy()
    candidates = candidates.loc[
        candidates["oof_auc"].gt(float(baseline["oof_auc"]))
        & candidates["positive_fold_count_vs_e01"].ge(minimum_positive_folds)
        & candidates["std_fold_auc"].le(
            float(baseline["std_fold_auc"]) + max_std_increase
        )
    ]
    if candidates.empty:
        return None
    best_auc = float(candidates["oof_auc"].max())
    tied = candidates.loc[candidates["oof_auc"].ge(best_auc - tie_tolerance)].copy()
    tied = tied.sort_values(
        ["n_features", "n_overwritten_features", "oof_auc", "experiment"],
        ascending=[True, True, False, True],
    )
    winner = tied.iloc[0]
    experiment = str(winner["experiment"])
    factors = describe_credit_amount_factors(
        CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS[experiment]
    ).factors
    return E02FinalSelection(
        name="E02-FINAL",
        source_experiment=experiment,
        factors=factors,
        oof_auc=float(winner["oof_auc"]),
        positive_fold_count=int(winner["positive_fold_count_vs_e01"]),
        std_fold_auc=float(winner["std_fold_auc"]),
    )
