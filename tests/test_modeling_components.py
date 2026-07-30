from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from credit_scoring.artifacts import export_dataframe_artifact, export_json_artifact
from credit_scoring.evaluation.cross_validation import (
    create_stratified_folds,
    validate_oof_coverage,
)
from credit_scoring.evaluation.metrics import calculate_roc_auc, validate_prediction_array
from credit_scoring.modeling import lightgbm_model
from credit_scoring.submission.home_credit import create_home_credit_submission


def test_roc_auc_and_prediction_validation() -> None:
    assert calculate_roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)
    np.testing.assert_allclose(validate_prediction_array([0.1, 0.9]), [0.1, 0.9])

    with pytest.raises(ValueError, match="probabilities"):
        validate_prediction_array([0.1, 1.1])


def test_stratified_folds_cover_each_row_once() -> None:
    target = np.array([0, 0, 0, 1, 1, 1])
    folds = create_stratified_folds(target, n_splits=3)
    validation_indices = np.concatenate([valid for _, valid in folds])
    assert sorted(validation_indices.tolist()) == list(range(len(target)))
    validate_oof_coverage(np.full(len(target), 0.5), target, np.ones(len(target)))


@pytest.mark.parametrize(
    "validation_counts",
    [
        np.array([1, 1, 1, 1, 1, 0]),  # missing one validation assignment
        np.array([2, 1, 1, 1, 1, 0]),  # duplicate assignment plus missing assignment
        np.array([1, 1, 1, 2, 1, 1]),  # overwritten OOF value at one index
    ],
    ids=["missing_oof_assignment", "duplicate_oof_assignment", "overwritten_oof_assignment"],
)
def test_oof_coverage_rejects_non_exactly_once_counts(
    validation_counts: np.ndarray,
) -> None:
    target = np.array([0, 0, 0, 1, 1, 1])
    predictions = np.full(len(target), 0.5)

    with pytest.raises(ValueError, match="exactly one"):
        validate_oof_coverage(predictions, target, validation_counts)


def test_submission_builder_validates_schema_and_writes_file(tmp_path: Path) -> None:
    path = create_home_credit_submission(
        pd.Series([10, 11]),
        np.array([0.2, 0.8]),
        tmp_path / "submission.csv",
    )
    submission = pd.read_csv(path)
    assert list(submission.columns) == ["SK_ID_CURR", "TARGET"]
    assert submission["TARGET"].tolist() == [0.2, 0.8]

    with pytest.raises(ValueError, match="duplicate"):
        create_home_credit_submission(pd.Series([10, 10]), [0.1, 0.2], tmp_path / "bad.csv")


def test_artifact_writers_create_parent_directories(tmp_path: Path) -> None:
    json_path = export_json_artifact({"auc": 0.8}, tmp_path / "nested" / "meta.json")
    csv_path = export_dataframe_artifact(
        pd.DataFrame({"feature": ["x"], "importance": [1.0]}),
        tmp_path / "nested" / "importance.csv",
    )
    assert json_path.is_file()
    assert csv_path.is_file()


def test_lightgbm_runner_writes_complete_oof_without_importing_booster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        best_iteration_ = 7

        def fit(self, *_args, **_kwargs) -> None:
            return None

        def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
            probability = np.full(len(frame), 0.5)
            return np.column_stack([1 - probability, probability])

        @property
        def feature_importances_(self) -> np.ndarray:
            return np.array([2.0, 1.0])

    monkeypatch.setattr(lightgbm_model, "build_lightgbm_model", lambda _config: FakeModel())
    monkeypatch.setattr(lightgbm_model, "_fit_lightgbm", lambda *_args, **_kwargs: None)
    features = pd.DataFrame({"feature_a": range(12), "feature_b": range(12)})
    target = np.array([0, 1] * 6)

    result = lightgbm_model.run_lightgbm_cv(
        features,
        target,
        features.iloc[:3],
        validation_config={"n_splits": 3, "keep_models": False},
    )

    assert len(result["oof_predictions"]) == len(target)
    assert not np.isnan(result["oof_predictions"]).any()
    assert len(result["test_predictions"]) == 3
    assert result["validation_counts"].tolist() == [1] * len(target)
    assert result["best_iterations"] == [7, 7, 7]
