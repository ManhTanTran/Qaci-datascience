"""Optional Optuna tuning for LightGBM."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from credit_scoring.modeling.lightgbm_model import run_lightgbm_cv


def _suggest(trial: Any, name: str, specification: Any) -> Any:
    if isinstance(specification, Mapping):
        kind = specification["type"]
        low, high = specification["low"], specification["high"]
        step = specification.get("step")
    else:
        low, high = specification
        kind = "int" if isinstance(low, int) and isinstance(high, int) else "float"
        step = None
    if kind == "int":
        return trial.suggest_int(name, int(low), int(high), step=step or 1)
    if kind == "log_float":
        return trial.suggest_float(name, float(low), float(high), log=True)
    return trial.suggest_float(name, float(low), float(high), step=step)


def tune_lightgbm(
    train_features: pd.DataFrame,
    target: Sequence[int],
    categorical_features: Sequence[str],
    search_space: Mapping[str, Any],
    tuning_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Tune LightGBM with CV, never passing test data to the objective."""

    try:
        import optuna
    except ImportError as exc:
        raise ImportError("Optuna is an optional tuning dependency.") from exc

    started = time.perf_counter()
    config = {
        "n_trials": 30,
        "timeout": 3600,
        "n_splits": 3,
        "random_state": 42,
        "direction": "maximize",
        "metric": "roc_auc",
        "early_stopping_rounds": 100,
        **dict(tuning_config),
    }

    def objective(trial: Any) -> float:
        params = {name: _suggest(trial, name, spec) for name, spec in search_space.items()}
        result = run_lightgbm_cv(
            train_features=train_features,
            target=target,
            test_features=train_features.iloc[:0].copy(),
            categorical_features=categorical_features,
            model_config=params,
            validation_config={
                "n_splits": config["n_splits"],
                "random_state": config["random_state"],
                "early_stopping_rounds": config["early_stopping_rounds"],
                "keep_models": False,
            },
        )
        return float(result["mean_auc"])

    sampler = optuna.samplers.TPESampler(seed=int(config["random_state"]))
    study = optuna.create_study(direction=config["direction"], sampler=sampler)
    study.optimize(
        objective,
        n_trials=int(config["n_trials"]),
        timeout=int(config["timeout"]) if config["timeout"] is not None else None,
        show_progress_bar=False,
    )
    return {
        "best_params": dict(study.best_params),
        "best_score": float(study.best_value),
        "trial_dataframe": study.trials_dataframe(),
        "study_metadata": {
            "direction": config["direction"],
            "metric": config["metric"],
            "n_trials_completed": len(study.trials),
            "random_state": config["random_state"],
        },
        "elapsed_time": time.perf_counter() - started,
    }
