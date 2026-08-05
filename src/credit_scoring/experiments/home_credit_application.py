"""E01/E02 Home Credit comparison on application tables only."""

from __future__ import annotations

import gc
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from credit_scoring.evaluation.cross_validation import create_stratified_folds
from credit_scoring.experiments.ablation import PreparedDataset
from credit_scoring.features.home_credit_application import (
    E02_FEATURE_FAMILIES,
    build_aligned_application_features,
)
from credit_scoring.modeling.lightgbm_model import (
    DEFAULT_LIGHTGBM_CONFIG,
    CVResult,
    run_lightgbm_cv,
)

E01_REFERENCE_OOF_AUC = 0.768696

E01_VALIDATION_CONFIG: dict[str, Any] = {
    "n_splits": 5,
    "shuffle": True,
    "random_state": 42,
    "early_stopping_rounds": 200,
    "keep_models": True,
}

E02_ABLATION_EXPERIMENTS: dict[str, tuple[str, ...]] = {
    "E01_locked": (),
    "E02-A_credit_amount": ("ratios",),
    "E02-B_age_employment": ("age_employment",),
    "E02-C_external_sources": ("external_sources",),
    "E02-D_application_contact": ("application_contact",),
    "E02-E_housing": ("housing",),
    "E02-ALL": E02_FEATURE_FAMILIES,
}


PreparedApplicationData = PreparedDataset


class ExperimentMetrics(TypedDict):
    fold_scores: list[float]
    mean_auc: float
    std_auc: float
    oof_auc: float
    runtime_seconds: float
    fold_fingerprint: str


class E02Comparison(TypedDict):
    reference_oof_auc: float
    e01: ExperimentMetrics
    e02: ExperimentMetrics
    delta_mean_auc: float
    delta_oof_auc: float
    feature_count_e01: int
    feature_count_e02: int
    features_added: list[str]
    feature_families: list[str]
    peak_memory_mb: None


def resolve_e02_ablation_experiments(
    selected: Sequence[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return canonical E02 ablations in a deterministic execution order."""

    requested = list(E02_ABLATION_EXPERIMENTS if selected is None else selected)
    unknown = sorted(set(requested).difference(E02_ABLATION_EXPERIMENTS))
    if unknown:
        raise ValueError(f"Unknown E02 ablation experiments: {unknown}")
    if len(requested) != len(set(requested)):
        raise ValueError("E02 ablation experiment names must be unique.")
    if "E01_locked" not in requested:
        raise ValueError("E02 ablation requires E01_locked as the comparison baseline.")
    return {
        name: E02_ABLATION_EXPERIMENTS[name]
        for name in E02_ABLATION_EXPERIMENTS
        if name in requested
    }


def _validate_raw_application_inputs(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
) -> None:
    required_train = {"SK_ID_CURR", "TARGET"}
    required_test = {"SK_ID_CURR"}
    if missing := sorted(required_train.difference(train_frame.columns)):
        raise ValueError(f"application_train is missing columns: {missing}")
    if missing := sorted(required_test.difference(test_frame.columns)):
        raise ValueError(f"application_test is missing columns: {missing}")
    if not train_frame["TARGET"].isin([0, 1]).all():
        raise ValueError("TARGET must contain only 0/1 values.")
    if not train_frame["SK_ID_CURR"].is_unique or not test_frame["SK_ID_CURR"].is_unique:
        raise ValueError("SK_ID_CURR must be unique within each application table.")


def prepare_application_data(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    feature_set: str,
    families: Sequence[str] | None = None,
) -> PreparedApplicationData:
    """Generate features and align category encoding without using the target."""

    _validate_raw_application_inputs(train_frame, test_frame)
    train_featured, test_featured = build_aligned_application_features(
        train_frame,
        test_frame,
        feature_set=feature_set,
        families=families,
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
        raise ValueError("Prepared train/test columns differ in name or order.")
    numeric = combined.select_dtypes(include="number")
    if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Prepared application matrices contain infinite values.")
    return PreparedApplicationData(
        train_features=train_features,
        test_features=test_features,
        target=target,
        train_ids=train_ids,
        test_ids=test_ids,
        categorical_features=categorical,
    )


def _metrics(result: CVResult) -> ExperimentMetrics:
    return {
        "fold_scores": result["fold_scores"],
        "mean_auc": result["mean_auc"],
        "std_auc": result["std_auc"],
        "oof_auc": result["oof_auc"],
        "runtime_seconds": result["runtime"],
        "fold_fingerprint": str(result["metadata"]["fold_fingerprint"]),
    }


def run_e01_e02_comparison(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    e02_families: Sequence[str] | None = None,
    model_config: Mapping[str, Any] | None = None,
    validation_config: Mapping[str, Any] | None = None,
) -> E02Comparison:
    """Run E01 and E02 on one immutable fold list and locked model settings.

    E02 feature-family ablations can be run by passing a subset of
    ``e02_families``. They always start from the complete locked E01 matrix.
    """

    resolved_model = {**DEFAULT_LIGHTGBM_CONFIG, **dict(model_config or {})}
    resolved_validation = {**E01_VALIDATION_CONFIG, **dict(validation_config or {})}
    target = train_frame["TARGET"].astype("int8")
    folds = create_stratified_folds(
        target,
        n_splits=int(resolved_validation["n_splits"]),
        shuffle=bool(resolved_validation["shuffle"]),
        random_state=int(resolved_validation["random_state"]),
    )

    e01_data = prepare_application_data(train_frame, test_frame, feature_set="e01")
    e01_columns = list(e01_data.train_features.columns)
    e01_result = run_lightgbm_cv(
        e01_data.train_features,
        e01_data.target,
        e01_data.test_features,
        categorical_features=e01_data.categorical_features,
        model_config=resolved_model,
        validation_config=resolved_validation,
        folds=folds,
    )
    e01_metrics = _metrics(e01_result)
    e01_result["fitted_models"].clear()
    del e01_data, e01_result
    gc.collect()

    selected_families = list(E02_FEATURE_FAMILIES if e02_families is None else e02_families)
    e02_data = prepare_application_data(
        train_frame,
        test_frame,
        feature_set="e02",
        families=selected_families,
    )
    e02_columns = list(e02_data.train_features.columns)
    e02_result = run_lightgbm_cv(
        e02_data.train_features,
        e02_data.target,
        e02_data.test_features,
        categorical_features=e02_data.categorical_features,
        model_config=resolved_model,
        validation_config=resolved_validation,
        folds=folds,
    )
    e02_metrics = _metrics(e02_result)
    if e01_metrics["fold_fingerprint"] != e02_metrics["fold_fingerprint"]:
        raise RuntimeError("E01 and E02 were not evaluated on identical folds.")
    return {
        "reference_oof_auc": E01_REFERENCE_OOF_AUC,
        "e01": e01_metrics,
        "e02": e02_metrics,
        "delta_mean_auc": e02_metrics["mean_auc"] - e01_metrics["mean_auc"],
        "delta_oof_auc": e02_metrics["oof_auc"] - e01_metrics["oof_auc"],
        "feature_count_e01": len(e01_columns),
        "feature_count_e02": len(e02_columns),
        "features_added": [column for column in e02_columns if column not in e01_columns],
        "feature_families": selected_families,
        "peak_memory_mb": None,
    }
