from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
import pytest

from credit_scoring.experiments.ablation import PreparedDataset, run_ablation
from credit_scoring.experiments.home_credit_application import PreparedApplicationData
from credit_scoring.features import safe_divide as exported_safe_divide
from credit_scoring.features.home_credit_application import safe_divide as legacy_safe_divide
from credit_scoring.modeling.lightgbm_model import CVResult
from credit_scoring.numeric import safe_divide


def _prepared(name: str, *, target: Sequence[int] = (0, 1, 0, 1)) -> PreparedDataset:
    train = pd.DataFrame({name: [0.0, 1.0, 2.0, 3.0]})
    test = pd.DataFrame({name: [4.0, 5.0]})
    return PreparedDataset(
        train_features=train,
        test_features=test,
        target=pd.Series(target, dtype="int8"),
        train_ids=pd.Series([10, 11, 12, 13]),
        test_ids=pd.Series([20, 21]),
        categorical_features=(),
    )


def _fake_result(
    *,
    oof_auc: float,
    fold_scores: list[float],
    fingerprint: str = "locked-folds",
) -> CVResult:
    return {
        "oof_predictions": np.array([0.1, 0.9, 0.2, 0.8]),
        "test_predictions": np.array([0.3, 0.7]),
        "validation_counts": np.ones(4, dtype=np.int8),
        "fold_assignments": np.array([0, 1, 0, 1], dtype=np.int16),
        "fold_scores": fold_scores,
        "mean_auc": float(np.mean(fold_scores)),
        "std_auc": float(np.std(fold_scores, ddof=1)),
        "oof_auc": oof_auc,
        "best_iterations": [10, 12],
        "feature_importance": pd.DataFrame(
            {"feature": ["x"], "importance_mean": [1.0], "importance_std": [0.0]}
        ),
        "fitted_models": [],
        "runtime": 0.1,
        "metadata": {"fold_fingerprint": fingerprint},
    }


def test_safe_divide_is_generic_float32_and_never_infinite() -> None:
    assert exported_safe_divide is safe_divide
    assert legacy_safe_divide is safe_divide
    assert PreparedApplicationData is PreparedDataset

    result = safe_divide(
        pd.Series([4.0, 1.0, np.inf, 2.0]),
        pd.Series([2.0, 0.0, 2.0, np.nan]),
    )

    assert result.dtype == "float32"
    assert result.iloc[0] == pytest.approx(2.0)
    assert result.iloc[1:].isna().all()
    assert not np.isinf(result.to_numpy()).any()

    aligned = safe_divide(
        pd.Series([6.0, 9.0], index=[10, 20]),
        pd.Series([3.0], index=[10]),
    )
    assert aligned.index.tolist() == [10, 20]
    assert aligned.loc[10] == pytest.approx(2.0)
    assert pd.isna(aligned.loc[20])


def test_run_ablation_runs_baseline_first_and_returns_paired_deltas() -> None:
    calls: list[str] = []

    def fake_runner(train_features: pd.DataFrame, *_args: Any, **_kwargs: Any) -> CVResult:
        name = str(train_features.columns[0])
        calls.append(name)
        if name == "baseline":
            return _fake_result(oof_auc=0.70, fold_scores=[0.60, 0.70])
        return _fake_result(oof_auc=0.72, fold_scores=[0.61, 0.72])

    result = run_ablation(
        {"candidate": _prepared("candidate"), "baseline": _prepared("baseline")},
        folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
        baseline_name="baseline",
        validation_config={"n_splits": 2},
        runner=fake_runner,
    )

    assert calls == ["baseline", "candidate"]
    assert result["fold_fingerprint"] == "locked-folds"
    assert result["summary"]["experiment"].tolist() == ["baseline", "candidate"]
    candidate = result["summary"].iloc[1]
    assert candidate["delta_oof_auc_vs_baseline"] == pytest.approx(0.02)
    assert candidate["positive_fold_count_vs_baseline"] == 2
    candidate_folds = result["fold_metrics"].query("experiment == 'candidate'")
    np.testing.assert_allclose(candidate_folds["delta_auc_vs_baseline"], [0.01, 0.02])


def test_run_ablation_rejects_target_id_schema_and_fingerprint_drift() -> None:
    baseline = _prepared("baseline")
    bad_target = _prepared("candidate", target=(1, 0, 1, 0))
    with pytest.raises(ValueError, match="target differs"):
        run_ablation(
            {"baseline": baseline, "candidate": bad_target},
            folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
            baseline_name="baseline",
            runner=lambda *_args, **_kwargs: _fake_result(
                oof_auc=0.7, fold_scores=[0.6, 0.7]
            ),
        )

    bad_ids = _prepared("candidate")
    bad_ids.train_ids.iloc[0] = 999
    with pytest.raises(ValueError, match="train identifiers differ"):
        run_ablation(
            {"baseline": baseline, "candidate": bad_ids},
            folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
            baseline_name="baseline",
            runner=lambda *_args, **_kwargs: _fake_result(
                oof_auc=0.7, fold_scores=[0.6, 0.7]
            ),
        )

    def drifting_runner(train_features: pd.DataFrame, *_args: Any, **_kwargs: Any) -> CVResult:
        fingerprint = "baseline-folds" if "baseline" in train_features else "other-folds"
        return _fake_result(
            oof_auc=0.7,
            fold_scores=[0.6, 0.7],
            fingerprint=fingerprint,
        )

    with pytest.raises(RuntimeError, match="fold fingerprint differs"):
        run_ablation(
            {"baseline": baseline, "candidate": _prepared("candidate")},
            folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
            baseline_name="baseline",
            runner=drifting_runner,
        )


def test_run_ablation_validates_prepared_train_test_schema() -> None:
    invalid = _prepared("train_feature")
    invalid.test_features.columns = ["different_feature"]

    with pytest.raises(ValueError, match="train/test feature columns"):
        run_ablation(
            {"baseline": invalid},
            folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
            baseline_name="baseline",
            runner=lambda *_args, **_kwargs: _fake_result(
                oof_auc=0.7, fold_scores=[0.6, 0.7]
            ),
        )


def test_run_ablation_rejects_non_exactly_once_oof_coverage() -> None:
    def invalid_runner(*_args: Any, **_kwargs: Any) -> CVResult:
        result = _fake_result(oof_auc=0.7, fold_scores=[0.6, 0.7])
        result["validation_counts"][0] = 0
        return result

    with pytest.raises(RuntimeError, match="not exactly once"):
        run_ablation(
            {"baseline": _prepared("baseline")},
            folds=[([2, 3], [0, 1]), ([0, 1], [2, 3])],
            baseline_name="baseline",
            runner=invalid_runner,
        )
