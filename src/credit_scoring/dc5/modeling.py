"""Paired model comparison for the DC5 Telco monetary research target."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from credit_scoring.dc5.config import ModelConfig
from credit_scoring.dc5.data import TARGET_COLUMN, feature_sets
from credit_scoring.evaluation.cross_validation import (
    create_stratified_folds,
    validate_oof_coverage,
)


@dataclass(frozen=True)
class ExperimentResult:
    """Aggregate metrics and artifacts from one paired CV experiment."""

    setting: str
    model_name: str
    features: tuple[str, ...]
    roc_auc: float
    pr_auc: float
    positive_rate: float
    pr_lift: float
    runtime_seconds: float
    best_iterations: tuple[int, ...]
    importance: pd.DataFrame
    fold_metrics: pd.DataFrame

    def summary_row(self) -> dict[str, Any]:
        return {
            "setting": self.setting,
            "model": self.model_name,
            "n_features": len(self.features),
            "roc_auc": self.roc_auc,
            "pr_auc": self.pr_auc,
            "positive_rate": self.positive_rate,
            "pr_lift": self.pr_lift,
            "runtime_seconds": self.runtime_seconds,
            "mean_best_iteration": (
                float(np.mean(self.best_iterations)) if self.best_iterations else np.nan
            ),
        }


def _categorical_columns(frame: pd.DataFrame, features: tuple[str, ...]) -> list[str]:
    categorical: list[str] = []
    for column in features:
        dtype = frame[column].dtype
        if (
            isinstance(dtype, pd.CategoricalDtype)
            or pd.api.types.is_object_dtype(dtype)
            or pd.api.types.is_string_dtype(dtype)
        ):
            categorical.append(column)
    return categorical


def _build_logistic_pipeline(
    categorical: list[str],
    numeric: list[str],
) -> Pipeline:
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("categorical", categorical_pipeline, categorical),
            ("numeric", numeric_pipeline, numeric),
        ]
    )
    return Pipeline(
        [
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=1_000, random_state=42)),
        ]
    )


def _logistic_importance(
    model: Pipeline,
    categorical: list[str],
    numeric: list[str],
) -> dict[str, float]:
    coefficients = np.abs(model.named_steps["classifier"].coef_[0])
    preprocessor = model.named_steps["preprocessor"]
    importance: dict[str, float] = {}
    categorical_slice = preprocessor.output_indices_["categorical"]
    categorical_values = coefficients[categorical_slice]
    encoder = preprocessor.named_transformers_["categorical"].named_steps["encoder"]
    offset = 0
    for column, categories in zip(categorical, encoder.categories_, strict=True):
        width = len(categories)
        importance[column] = float(categorical_values[offset : offset + width].sum())
        offset += width
    numeric_values = coefficients[preprocessor.output_indices_["numeric"]]
    for column, value in zip(numeric, numeric_values, strict=True):
        importance[column] = float(value)
    return importance


def _fit_logistic_fold(
    train_features: pd.DataFrame,
    train_target: pd.Series,
    valid_features: pd.DataFrame,
    categorical: list[str],
) -> tuple[np.ndarray, dict[str, float], int]:
    numeric = [column for column in train_features.columns if column not in categorical]
    model = _build_logistic_pipeline(categorical, numeric)
    model.fit(train_features, train_target)
    predictions = model.predict_proba(valid_features)[:, 1]
    return predictions, _logistic_importance(model, categorical, numeric), 0


def _fit_catboost_fold(
    train_features: pd.DataFrame,
    train_target: pd.Series,
    valid_features: pd.DataFrame,
    valid_target: pd.Series,
    categorical: list[str],
    config: ModelConfig,
) -> tuple[np.ndarray, dict[str, float], int]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            'CatBoost backend requires: python -m pip install -e ".[dc5]"'
        ) from exc

    train = train_features.copy()
    valid = valid_features.copy()
    for column in categorical:
        train[column] = train[column].fillna("MISSING").astype(str)
        valid[column] = valid[column].fillna("MISSING").astype(str)
    model = CatBoostClassifier(
        iterations=config.iterations,
        depth=config.depth,
        learning_rate=config.learning_rate,
        loss_function="Logloss",
        eval_metric="AUC",
        random_seed=42,
        verbose=False,
        allow_writing_files=False,
    )
    model.fit(
        train,
        train_target,
        cat_features=categorical,
        eval_set=(valid, valid_target),
        early_stopping_rounds=50,
        verbose=False,
    )
    predictions = model.predict_proba(valid)[:, 1]
    importance = dict(
        zip(train.columns, model.get_feature_importance().astype(float), strict=True)
    )
    return predictions, importance, int(model.get_best_iteration())


def run_experiment(
    population: pd.DataFrame,
    *,
    features: tuple[str, ...],
    model_name: str,
    setting: str,
    folds: list[tuple[np.ndarray, np.ndarray]],
    model_config: ModelConfig,
) -> ExperimentResult:
    """Run one model variant on precomputed folds and produce complete OOF metrics."""

    started = time.perf_counter()
    matrix = population.loc[:, features]
    target = population[TARGET_COLUMN].astype(int)
    categorical = _categorical_columns(matrix, features)
    oof = np.full(len(population), np.nan, dtype=float)
    validation_counts = np.zeros(len(population), dtype=np.int8)
    fold_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, float]] = []
    best_iterations: list[int] = []

    for fold_number, (train_idx, valid_idx) in enumerate(folds, start=1):
        x_train = matrix.iloc[train_idx].copy()
        x_valid = matrix.iloc[valid_idx].copy()
        y_train = target.iloc[train_idx]
        y_valid = target.iloc[valid_idx]
        if model_config.backend == "catboost":
            predictions, importance, best_iteration = _fit_catboost_fold(
                x_train,
                y_train,
                x_valid,
                y_valid,
                categorical,
                model_config,
            )
        else:
            predictions, importance, best_iteration = _fit_logistic_fold(
                x_train,
                y_train,
                x_valid,
                categorical,
            )
        oof[valid_idx] = predictions
        validation_counts[valid_idx] += 1
        fold_rows.append(
            {
                "setting": setting,
                "model": model_name,
                "fold": fold_number,
                "roc_auc": float(roc_auc_score(y_valid, predictions)),
                "pr_auc": float(average_precision_score(y_valid, predictions)),
                "n_validation": len(valid_idx),
                "positive_rate": float(y_valid.mean()),
            }
        )
        importance_rows.append(importance)
        best_iterations.append(best_iteration)

    validate_oof_coverage(oof, target, validation_counts)
    positive_rate = float(target.mean())
    importance = (
        pd.DataFrame(importance_rows)
        .mean(axis=0)
        .rename("importance")
        .rename_axis("feature")
        .reset_index()
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    return ExperimentResult(
        setting=setting,
        model_name=model_name,
        features=features,
        roc_auc=float(roc_auc_score(target, oof)),
        pr_auc=float(average_precision_score(target, oof)),
        positive_rate=positive_rate,
        pr_lift=float(average_precision_score(target, oof) / positive_rate),
        runtime_seconds=float(time.perf_counter() - started),
        best_iterations=tuple(best_iterations),
        importance=importance,
        fold_metrics=pd.DataFrame(fold_rows),
    )


def run_model_suite(
    population: pd.DataFrame,
    *,
    model_names: tuple[str, ...],
    include_city_comparison: bool,
    n_splits: int,
    random_state: int,
    model_config: ModelConfig,
) -> list[ExperimentResult]:
    """Run every requested variant on the same population and fold assignments."""

    target = population[TARGET_COLUMN].astype(int)
    smallest_class = int(target.value_counts().min())
    if smallest_class < n_splits:
        raise ValueError(
            f"Smallest target class has {smallest_class} rows; cannot create {n_splits} folds."
        )
    folds = create_stratified_folds(
        target,
        n_splits=n_splits,
        random_state=random_state,
    )
    settings = [("With City", True)]
    if include_city_comparison:
        settings.append(("No City", False))
    results: list[ExperimentResult] = []
    for setting, include_city in settings:
        schemas = feature_sets(include_city=include_city)
        for model_name in model_names:
            results.append(
                run_experiment(
                    population,
                    features=schemas[model_name],
                    model_name=model_name,
                    setting=setting,
                    folds=folds,
                    model_config=model_config,
                )
            )
    return results
