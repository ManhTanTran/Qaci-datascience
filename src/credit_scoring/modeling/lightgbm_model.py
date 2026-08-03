"""LightGBM model factory and leakage-safe OOF runner."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from credit_scoring.evaluation.cross_validation import (
    create_stratified_folds,
    validate_oof_coverage,
)
from credit_scoring.evaluation.metrics import calculate_roc_auc

DEFAULT_LIGHTGBM_CONFIG: dict[str, Any] = {
    "objective": "binary",
    "learning_rate": 0.02,
    "n_estimators": 5000,
    "num_leaves": 31,
    "max_depth": -1,
    "min_child_samples": 80,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 5.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": -1,
}


class CVResult(TypedDict):
    """Stable result contract returned by :func:`run_lightgbm_cv`."""

    oof_predictions: np.ndarray
    test_predictions: np.ndarray
    validation_counts: np.ndarray
    fold_scores: list[float]
    mean_auc: float
    std_auc: float
    oof_auc: float
    best_iterations: list[int]
    feature_importance: pd.DataFrame
    fitted_models: list[Any]
    runtime: float
    metadata: dict[str, Any]


def build_lightgbm_model(model_config: Mapping[str, Any] | None = None) -> Any:
    """Build an ``LGBMClassifier``; LightGBM is imported only when called."""

    try:
        from lightgbm import LGBMClassifier
    except ImportError as exc:
        raise ImportError(
            "LightGBM is required for modeling. Kaggle usually includes it; "
            "locally install the optional modeling dependencies."
        ) from exc
    config = {**DEFAULT_LIGHTGBM_CONFIG, **dict(model_config or {})}
    return LGBMClassifier(**config)


def _fit_lightgbm(
    model: Any,
    x_train: pd.DataFrame,
    y_train: Sequence[int],
    x_valid: pd.DataFrame,
    y_valid: Sequence[int],
    categorical_features: Sequence[str],
    early_stopping_rounds: int,
) -> None:
    import lightgbm as lgb

    callbacks = [
        lgb.early_stopping(early_stopping_rounds, verbose=False),
        lgb.log_evaluation(period=0),
    ]
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_valid, y_valid)],
        eval_metric="auc",
        categorical_feature=list(categorical_features) or "auto",
        callbacks=callbacks,
    )


def run_lightgbm_cv(
    train_features: pd.DataFrame,
    target: Sequence[int],
    test_features: pd.DataFrame,
    categorical_features: Sequence[str] | None = None,
    model_config: Mapping[str, Any] | None = None,
    validation_config: Mapping[str, Any] | None = None,
    folds: Sequence[tuple[Sequence[int], Sequence[int]]] | None = None,
) -> CVResult:
    """Train LightGBM with stratified folds and return OOF/test artifacts."""

    if list(train_features.columns) != list(test_features.columns):
        raise ValueError("Train and test feature columns must match in the same order.")
    if len(train_features) != len(target):
        raise ValueError("Target length must equal the number of train rows.")
    if train_features.isnull().all(axis=0).any():
        raise ValueError("A feature column is entirely missing in train data.")
    categories = list(categorical_features or [])
    missing_categories = sorted(set(categories).difference(train_features.columns))
    if missing_categories:
        raise ValueError(f"Unknown categorical feature columns: {missing_categories}")

    validation = {
        "n_splits": 5,
        "shuffle": True,
        "random_state": 42,
        "early_stopping_rounds": 200,
        "keep_models": True,
        **dict(validation_config or {}),
    }
    if folds is None:
        resolved_folds = create_stratified_folds(
            target,
            n_splits=int(validation["n_splits"]),
            shuffle=bool(validation["shuffle"]),
            random_state=int(validation["random_state"]),
        )
    else:
        resolved_folds = [
            (np.asarray(train_idx, dtype=int), np.asarray(valid_idx, dtype=int))
            for train_idx, valid_idx in folds
        ]
        if len(resolved_folds) != int(validation["n_splits"]):
            raise ValueError("Precomputed fold count must equal validation n_splits.")
        fold_counts = np.zeros(len(train_features), dtype=np.int8)
        for train_idx, valid_idx in resolved_folds:
            if not len(train_idx) or not len(valid_idx):
                raise ValueError("Precomputed folds cannot contain an empty split.")
            if (
                train_idx.min() < 0
                or valid_idx.min() < 0
                or train_idx.max() >= len(train_features)
                or valid_idx.max() >= len(train_features)
            ):
                raise ValueError("Precomputed fold indices are out of bounds.")
            if np.intersect1d(train_idx, valid_idx).size:
                raise ValueError("Precomputed train and validation indices overlap.")
            fold_counts[valid_idx] += 1
        if not np.all(fold_counts == 1):
            raise ValueError("Precomputed folds must validate every row exactly once.")
    fold_assignments = np.full(len(train_features), -1, dtype=np.int16)
    for fold_number, (_, valid_idx) in enumerate(resolved_folds):
        fold_assignments[valid_idx] = fold_number
    fold_fingerprint = sha256(fold_assignments.tobytes()).hexdigest()
    oof = np.full(len(train_features), np.nan, dtype=float)
    validation_counts = np.zeros(len(train_features), dtype=np.int8)
    test_predictions = np.zeros(len(test_features), dtype=float)
    fold_scores: list[float] = []
    best_iterations: list[int] = []
    models: list[Any] = []
    importance_frames: list[pd.DataFrame] = []
    started = time.perf_counter()

    for fold_number, (train_idx, valid_idx) in enumerate(resolved_folds, start=1):
        model = build_lightgbm_model(model_config)
        _fit_lightgbm(
            model,
            train_features.iloc[train_idx],
            np.asarray(target)[train_idx],
            train_features.iloc[valid_idx],
            np.asarray(target)[valid_idx],
            categories,
            int(validation["early_stopping_rounds"]),
        )
        valid_predictions = model.predict_proba(train_features.iloc[valid_idx])[:, 1]
        oof[valid_idx] = valid_predictions
        validation_counts[valid_idx] += 1
        if len(test_features):
            test_predictions += model.predict_proba(test_features)[:, 1] / len(resolved_folds)
        fold_scores.append(calculate_roc_auc(np.asarray(target)[valid_idx], valid_predictions))
        best_iteration = int(getattr(model, "best_iteration_", 0) or 0)
        best_iterations.append(best_iteration)
        importance_frames.append(
            pd.DataFrame(
                {
                    "feature": train_features.columns,
                    "importance": model.feature_importances_,
                    "fold": fold_number,
                }
            )
        )
        if bool(validation["keep_models"]):
            models.append(model)

    validate_oof_coverage(oof, target, validation_counts)
    importance = pd.concat(importance_frames, ignore_index=True)
    feature_importance = (
        importance.groupby("feature", as_index=False)
        .agg(
            importance_mean=("importance", "mean"),
            importance_std=("importance", "std"),
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )
    result: CVResult = {
        "oof_predictions": oof,
        "test_predictions": test_predictions,
        "validation_counts": validation_counts,
        "fold_scores": fold_scores,
        "mean_auc": float(np.mean(fold_scores)),
        "std_auc": float(np.std(fold_scores, ddof=1)) if len(fold_scores) > 1 else 0.0,
        "oof_auc": calculate_roc_auc(target, oof),
        "best_iterations": best_iterations,
        "feature_importance": feature_importance,
        "fitted_models": models,
        "runtime": time.perf_counter() - started,
        "metadata": {
            "model": "lightgbm",
            "n_splits": len(resolved_folds),
            "fold_fingerprint": fold_fingerprint,
            "categorical_features": categories,
            "validation_config": validation,
        },
    }
    return result
