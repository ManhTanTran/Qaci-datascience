from __future__ import annotations

import json

import pytest

from credit_scoring.dc5.config import ModelConfig
from credit_scoring.dc5.data import prepare_population
from credit_scoring.dc5.inference import (
    BUNDLE_MANIFEST_NAME,
    build_catboost_inference_bundle,
    predict_catboost_bundle,
)
from credit_scoring.dc5.synthetic import build_demo_frame


def test_catboost_bundle_round_trip_excludes_sensitive_features(tmp_path) -> None:
    pytest.importorskip("catboost")
    population = prepare_population(build_demo_frame(n_rows=240, seed=17))
    build_catboost_inference_bundle(
        population,
        run_dir=tmp_path,
        run_id="synthetic-run",
        model_name="M4",
        setting="No City",
        model_config=ModelConfig(
            backend="catboost", iterations=20, depth=3, learning_rate=0.1
        ),
        iterations=20,
    )
    manifest = json.loads(
        (tmp_path / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["model_name"] == "M4-safe"
    assert set(manifest["excluded_features"]) == {"age_group_ord", "gender"}
    assert "city" not in manifest["features"]
    assert set(manifest["feature_schema"]) == set(manifest["features"])

    row = population.iloc[0]
    feature_values = {feature: row[feature] for feature in manifest["features"]}
    result = predict_catboost_bundle(tmp_path, feature_values)

    assert 0 <= result.target_probability <= 1
    assert result.model_name == "M4-safe"
    assert 1 <= len(result.local_reasons) <= 5
    assert all(reason.feature in manifest["features"] for reason in result.local_reasons)


def test_catboost_bundle_rejects_incomplete_feature_vector(tmp_path) -> None:
    pytest.importorskip("catboost")
    population = prepare_population(build_demo_frame(n_rows=120, seed=19))
    build_catboost_inference_bundle(
        population,
        run_dir=tmp_path,
        run_id="synthetic-run",
        model_name="M1",
        setting="No City",
        model_config=ModelConfig(
            backend="catboost", iterations=5, depth=2, learning_rate=0.1
        ),
        iterations=5,
    )
    with pytest.raises(ValueError, match="model_features không khớp"):
        predict_catboost_bundle(tmp_path, {})
