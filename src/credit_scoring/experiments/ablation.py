"""Dataset-independent preparation contract and paired ablation runner."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

import numpy as np
import pandas as pd

from credit_scoring.modeling.lightgbm_model import CVResult, run_lightgbm_cv


@dataclass(frozen=True)
class PreparedDataset:
    """Aligned model matrices, target, identifiers and categorical columns."""

    train_features: pd.DataFrame
    test_features: pd.DataFrame
    target: pd.Series | np.ndarray
    train_ids: pd.Series | pd.DataFrame
    test_ids: pd.Series | pd.DataFrame
    categorical_features: tuple[str, ...]


class AblationResult(TypedDict):
    """Artifacts returned by :func:`run_ablation`."""

    summary: pd.DataFrame
    fold_metrics: pd.DataFrame
    results: dict[str, CVResult]
    fold_fingerprint: str


CVRunner = Callable[..., CVResult]


def _validate_prepared_dataset(name: str, dataset: PreparedDataset) -> None:
    if list(dataset.train_features.columns) != list(dataset.test_features.columns):
        raise ValueError(f"{name}: train/test feature columns must match in order.")
    if len(dataset.train_features) != len(dataset.target):
        raise ValueError(f"{name}: target length must equal train row count.")
    if len(dataset.train_ids) != len(dataset.train_features):
        raise ValueError(f"{name}: train identifier length must equal train row count.")
    if len(dataset.test_ids) != len(dataset.test_features):
        raise ValueError(f"{name}: test identifier length must equal test row count.")
    missing_categories = sorted(
        set(dataset.categorical_features).difference(dataset.train_features.columns)
    )
    if missing_categories:
        raise ValueError(f"{name}: unknown categorical columns: {missing_categories}")


def _identifiers_equal(
    left: pd.Series | pd.DataFrame,
    right: pd.Series | pd.DataFrame,
) -> bool:
    return type(left) is type(right) and left.reset_index(drop=True).equals(
        right.reset_index(drop=True)
    )


def run_ablation(
    configs: Mapping[str, PreparedDataset],
    folds: Sequence[tuple[Sequence[int], Sequence[int]]],
    *,
    baseline_name: str,
    model_config: Mapping[str, Any] | None = None,
    validation_config: Mapping[str, Any] | None = None,
    runner: CVRunner = run_lightgbm_cv,
) -> AblationResult:
    """Run prepared configurations on identical folds and compute paired deltas."""

    if not configs:
        raise ValueError("Ablation requires at least one configuration.")
    if not folds:
        raise ValueError("Ablation requires a non-empty precomputed fold list.")
    if baseline_name not in configs:
        raise ValueError(f"Unknown ablation baseline: {baseline_name}")

    baseline = configs[baseline_name]
    _validate_prepared_dataset(baseline_name, baseline)
    baseline_target = np.asarray(baseline.target)
    execution_order = [baseline_name, *(name for name in configs if name != baseline_name)]
    results: dict[str, CVResult] = {}
    fold_fingerprint: str | None = None

    for name in execution_order:
        dataset = configs[name]
        _validate_prepared_dataset(name, dataset)
        if not np.array_equal(np.asarray(dataset.target), baseline_target):
            raise ValueError(f"{name}: target differs from the ablation baseline.")
        if not _identifiers_equal(dataset.train_ids, baseline.train_ids):
            raise ValueError(f"{name}: train identifiers differ from the ablation baseline.")
        if not _identifiers_equal(dataset.test_ids, baseline.test_ids):
            raise ValueError(f"{name}: test identifiers differ from the ablation baseline.")

    for name in execution_order:
        dataset = configs[name]
        result = runner(
            dataset.train_features,
            dataset.target,
            dataset.test_features,
            categorical_features=dataset.categorical_features,
            model_config=model_config,
            validation_config=validation_config,
            folds=folds,
        )
        current_fingerprint = str(result["metadata"]["fold_fingerprint"])
        if fold_fingerprint is None:
            fold_fingerprint = current_fingerprint
        elif current_fingerprint != fold_fingerprint:
            raise RuntimeError(f"{name}: fold fingerprint differs from the baseline.")
        if not np.all(np.asarray(result["validation_counts"]) == 1):
            raise RuntimeError(f"{name}: OOF validation coverage is not exactly once.")
        results[name] = result

    baseline_result = results[baseline_name]
    baseline_fold_scores = np.asarray(baseline_result["fold_scores"], dtype=float)
    baseline_oof_auc = float(baseline_result["oof_auc"])
    summary_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    for name in execution_order:
        dataset = configs[name]
        result = results[name]
        fold_scores = np.asarray(result["fold_scores"], dtype=float)
        if len(fold_scores) != len(baseline_fold_scores):
            raise RuntimeError(f"{name}: fold score count differs from the baseline.")
        fold_deltas = fold_scores - baseline_fold_scores
        summary_rows.append(
            {
                "experiment": name,
                "n_features": int(dataset.train_features.shape[1]),
                "mean_fold_auc": float(result["mean_auc"]),
                "std_fold_auc": float(result["std_auc"]),
                "oof_auc": float(result["oof_auc"]),
                "delta_oof_auc_vs_baseline": float(result["oof_auc"] - baseline_oof_auc),
                "positive_fold_count_vs_baseline": int((fold_deltas > 0).sum()),
                "runtime_seconds": float(result["runtime"]),
                "fold_fingerprint": fold_fingerprint,
            }
        )
        for fold_number, (auc, delta, best_iteration) in enumerate(
            zip(fold_scores, fold_deltas, result["best_iterations"], strict=True),
            start=1,
        ):
            fold_rows.append(
                {
                    "experiment": name,
                    "fold": fold_number,
                    "auc": float(auc),
                    "delta_auc_vs_baseline": float(delta),
                    "best_iteration": int(best_iteration),
                    "fold_fingerprint": fold_fingerprint,
                }
            )

    if fold_fingerprint is None:  # pragma: no cover - guarded by non-empty configs
        raise RuntimeError("Ablation did not produce a fold fingerprint.")
    return {
        "summary": pd.DataFrame(summary_rows),
        "fold_metrics": pd.DataFrame(fold_rows),
        "results": results,
        "fold_fingerprint": fold_fingerprint,
    }
