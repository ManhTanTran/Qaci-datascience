from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from credit_scoring.dc5.clustering import CLUSTER_FEATURES, run_clustering
from credit_scoring.dc5.config import ModelConfig, PipelineConfig, ValidationConfig
from credit_scoring.dc5.data import (
    TARGET_COLUMN,
    feature_sets,
    prepare_population,
    validate_prepared_schema,
)
from credit_scoring.dc5.pipeline import run_pipeline, smoke_check
from credit_scoring.dc5.simulation import simulate_profile
from credit_scoring.dc5.synthetic import SAMPLE_COLUMNS, build_demo_frame


def _synthetic_model_frame(n_rows: int = 120) -> pd.DataFrame:
    all_features = sorted(
        {feature for schema in feature_sets().values() for feature in schema}
        | set(CLUSTER_FEATURES)
    )
    frame = pd.DataFrame({"user_id": [f"synthetic-{index}" for index in range(n_rows)]})
    for offset, feature in enumerate(all_features):
        frame[feature] = (np.arange(n_rows) + offset) % 5
    frame["gender"] = np.where(np.arange(n_rows) % 2, "Nữ", "Nam")
    frame["city"] = np.where(np.arange(n_rows) % 3, "Hà Nội", "Đà Nẵng")
    frame["household_type"] = "Nhà thường"
    frame["retail_product_group"] = np.where(
        np.arange(n_rows) % 2,
        "MOBILE",
        "ACCESSORY",
    )
    frame["has_telco"] = 1
    frame["has_pharmacy"] = 1
    frame["telco_monetary_group_ord"] = np.where(np.arange(n_rows) % 10 == 0, 4, 3)
    return frame


def test_smoke_check_runs_without_real_data() -> None:
    smoke_check()


def test_phase_one_simulation_is_explainable_and_does_not_use_cic() -> None:
    result = simulate_profile(
        age=35,
        income_million_vnd=15,
        occupation="Nhân viên văn phòng",
        employment_years=3,
        household_type="Chung cư",
        dependents=1,
        service_count=2,
        cic_score=720,
    )
    assert 0 <= result["demo_index"] <= 100
    assert result["cic_score"] == 720
    assert result["cic_used_in_model"] is False
    assert len(result["components"]) == 6


def test_demo_frame_is_deterministic_and_pipeline_ready() -> None:
    first = build_demo_frame(n_rows=120, seed=7)
    second = build_demo_frame(n_rows=120, seed=7)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 120
    assert first["user_id"].is_unique
    assert set(SAMPLE_COLUMNS).issubset(first.columns)
    validate_prepared_schema(
        first,
        requested_models=("M0", "M1", "M2", "M3", "M4"),
        include_city_comparison=True,
    )
    population = prepare_population(first)
    assert set(population[TARGET_COLUMN]) == {0, 1}


def test_feature_schema_is_declared_and_does_not_depend_on_data() -> None:
    with_city = feature_sets(include_city=True)
    without_city = feature_sets(include_city=False)
    assert with_city["M0"] == ("age_group_ord", "gender", "household_type", "city")
    assert "city" not in without_city["M4"]
    assert len(with_city["M4"]) == len(without_city["M4"]) + 1


def test_population_filters_organizations_and_builds_target() -> None:
    frame = _synthetic_model_frame(20)
    frame.loc[0, "household_type"] = "Công ty"
    population = prepare_population(frame, individual_customers_only=True)
    assert len(population) == 19
    assert population["user_id"].is_unique
    assert set(population[TARGET_COLUMN]) == {0, 1}


def test_schema_validation_reports_missing_columns() -> None:
    frame = _synthetic_model_frame().drop(columns=["age_group_ord"])
    with pytest.raises(ValueError, match="age_group_ord"):
        validate_prepared_schema(
            frame,
            requested_models=("M0",),
            include_city_comparison=False,
        )


def test_pipeline_runs_end_to_end_and_reuses_cache(tmp_path: Path) -> None:
    data_path = tmp_path / "model_df.parquet"
    _synthetic_model_frame().to_parquet(data_path, index=False)
    config = PipelineConfig(
        data_path=data_path,
        output_dir=tmp_path / "artifacts",
        mode="quick",
        model_names=("M0",),
        include_city_comparison=False,
        validation=ValidationConfig(n_splits=3, random_state=42),
        model=ModelConfig(backend="logistic"),
    )

    first = run_pipeline(config=config)
    second = run_pipeline(config=config)

    assert first.report_path.is_file()
    assert (first.run_dir / "metrics.csv").is_file()
    assert (first.run_dir / "feature_importance.csv").is_file()
    assert (first.run_dir / "fold_metrics.csv").is_file()
    assert (first.run_dir / "domain_coverage.csv").is_file()
    assert (first.run_dir / "feature_missingness.csv").is_file()
    assert not first.cached
    assert second.cached
    assert second.run_dir == first.run_dir
    report = first.report_path.read_text(encoding="utf-8")
    assert "DC5 Customer Analysis" in report
    assert "data:image/png;base64," in report
    assert "synthetic-" not in report


def test_report_only_opens_latest_artifact_without_data(tmp_path: Path) -> None:
    data_path = tmp_path / "model_df.parquet"
    _synthetic_model_frame().to_parquet(data_path, index=False)
    output_dir = tmp_path / "artifacts"
    run_pipeline(
        config=PipelineConfig(
            data_path=data_path,
            output_dir=output_dir,
            mode="quick",
            model_names=("M0",),
            include_city_comparison=False,
            validation=ValidationConfig(n_splits=3),
            model=ModelConfig(backend="logistic"),
        )
    )
    latest = run_pipeline(
        config=PipelineConfig(
            data_path=tmp_path / "does-not-exist.parquet",
            output_dir=output_dir,
            mode="report-only",
            model=ModelConfig(backend="logistic"),
        )
    )
    assert latest.cached
    assert latest.report_path.is_file()


def test_catboost_backend_runs_when_optional_dependency_is_installed(tmp_path: Path) -> None:
    pytest.importorskip("catboost")
    data_path = tmp_path / "model_df.parquet"
    _synthetic_model_frame().to_parquet(data_path, index=False)
    run = run_pipeline(
        config=PipelineConfig(
            data_path=data_path,
            output_dir=tmp_path / "catboost-artifacts",
            mode="quick",
            model_names=("M0",),
            include_city_comparison=False,
            validation=ValidationConfig(n_splits=3),
            model=ModelConfig(
                backend="catboost",
                iterations=20,
                depth=3,
                learning_rate=0.1,
            ),
        )
    )
    assert run.metrics.loc[0, "model"] == "M0"
    assert 0 <= run.metrics.loc[0, "roc_auc"] <= 1


def test_full_mode_adds_anonymous_clustering_artifacts(tmp_path: Path) -> None:
    frame = _synthetic_model_frame()
    clustering = run_clustering(frame, n_clusters=4)
    assert clustering.sizes["count"].sum() == len(frame)
    assert list(clustering.projection.columns) == ["pca_1", "pca_2", "cluster"]
    assert "user_id" not in clustering.projection

    data_path = tmp_path / "model_df.parquet"
    frame.to_parquet(data_path, index=False)
    run = run_pipeline(
        config=PipelineConfig(
            data_path=data_path,
            output_dir=tmp_path / "full-artifacts",
            mode="full",
            model_names=("M0",),
            include_city_comparison=False,
            clustering_enabled=True,
            n_clusters=4,
            validation=ValidationConfig(n_splits=3),
            model=ModelConfig(backend="logistic"),
        )
    )
    assert (run.run_dir / "cluster_profile.csv").is_file()
    assert (run.run_dir / "cluster_sizes.csv").is_file()
    report = run.report_path.read_text(encoding="utf-8")
    assert "Exploratory clustering" in report
    assert "data:image/png;base64," in report
