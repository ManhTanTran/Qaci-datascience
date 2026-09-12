"""Persist and use a research-only CatBoost inference bundle."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from credit_scoring.dc5.config import ModelConfig
from credit_scoring.dc5.data import TARGET_COLUMN, feature_sets, prepare_population
from credit_scoring.dc5.modeling import _categorical_columns

BUNDLE_MODEL_NAME = "research_inference_model.cbm"
BUNDLE_MANIFEST_NAME = "research_inference_manifest.json"
EXCLUDED_INFERENCE_FEATURES = frozenset({"age_group_ord", "gender", "city"})


@dataclass(frozen=True)
class LocalReason:
    feature: str
    contribution: float
    direction: str


@dataclass(frozen=True)
class IndividualModelResult:
    target_probability: float
    target_definition: str
    model_name: str
    setting: str
    run_id: str
    local_reasons: tuple[LocalReason, ...]
    research_candidate: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_catboost_inference_bundle(
    population: pd.DataFrame,
    *,
    run_dir: str | Path,
    run_id: str,
    model_name: str,
    setting: str,
    model_config: ModelConfig,
    iterations: int,
) -> Path | None:
    """Fit the selected variant on all research rows and persist model + schema."""

    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('CatBoost inference requires: python -m pip install -e ".[dc5]"') from exc

    destination = Path(run_dir)
    destination.mkdir(parents=True, exist_ok=True)
    include_city = setting == "With City"
    declared_features = feature_sets(include_city=include_city)[model_name]
    features = tuple(
        feature for feature in declared_features if feature not in EXCLUDED_INFERENCE_FEATURES
    )
    matrix = population.loc[:, features].copy()
    if matrix.empty or not matrix.nunique(dropna=False).gt(1).any():
        return None
    categorical = _categorical_columns(matrix, features)
    for column in categorical:
        matrix[column] = matrix[column].fillna("MISSING").astype(str)
    model = CatBoostClassifier(
        iterations=max(1, iterations),
        depth=model_config.depth,
        learning_rate=model_config.learning_rate,
        loss_function="Logloss",
        random_seed=42,
        verbose=False,
        allow_writing_files=False,
    )
    model.fit(matrix, population[TARGET_COLUMN].astype(int), cat_features=categorical)
    model_path = destination / BUNDLE_MODEL_NAME
    model.save_model(model_path)
    manifest = {
        "bundle_version": "dc5-catboost-inference-v1",
        "run_id": run_id,
        "model_name": f"{model_name}-safe",
        "source_model_name": model_name,
        "setting": setting,
        "target_definition": "target_high_telco_monetary (telco_monetary_group_ord == 4)",
        "features": list(features),
        "categorical_features": categorical,
        "feature_schema": {
            feature: {"type": "string" if feature in categorical else "number"}
            for feature in features
        },
        "excluded_features": sorted(set(declared_features) - set(features)),
        "iterations": max(1, iterations),
        "status": "research_candidate",
    }
    (destination / BUNDLE_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return model_path.resolve()


def build_latest_catboost_bundle(
    data_path: str | Path,
    run_dir: str | Path,
) -> Path | None:
    """Build a full-data bundle for the best CatBoost CV result in a run."""

    destination = Path(run_dir)
    metadata = json.loads((destination / "run_metadata.json").read_text(encoding="utf-8"))
    backend = metadata.get("config", {}).get("model", {}).get("backend")
    if backend != "catboost":
        raise ValueError("Latest run does not use the CatBoost backend.")
    metrics = pd.read_csv(destination / "metrics.csv")
    best = metrics.sort_values(["roc_auc", "pr_auc"], ascending=False).iloc[0]
    frame = pd.read_parquet(data_path)
    population = prepare_population(
        frame,
        individual_customers_only=bool(
            metadata.get("config", {}).get("individual_customers_only", True)
        ),
    )
    config_payload = metadata["config"]["model"]
    config = ModelConfig(
        backend="catboost",
        iterations=int(config_payload.get("iterations", 500)),
        depth=int(config_payload.get("depth", 6)),
        learning_rate=float(config_payload.get("learning_rate", 0.05)),
    )
    mean_iteration = best.get("mean_best_iteration", config.iterations)
    iterations = config.iterations if pd.isna(mean_iteration) else round(float(mean_iteration))
    return build_catboost_inference_bundle(
        population,
        run_dir=destination,
        run_id=str(metadata["run_id"]),
        model_name=str(best["model"]),
        setting=str(best["setting"]),
        model_config=config,
        iterations=iterations,
    )


def predict_catboost_bundle(
    run_dir: str | Path,
    feature_values: dict[str, Any],
    *,
    top_n_reasons: int = 5,
) -> IndividualModelResult:
    """Validate an exact feature vector and produce prediction + local SHAP signals."""

    try:
        from catboost import CatBoostClassifier, Pool
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError('CatBoost inference requires: python -m pip install -e ".[dc5]"') from exc

    source = Path(run_dir)
    manifest = json.loads((source / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))
    features = tuple(manifest["features"])
    missing = sorted(set(features) - set(feature_values))
    unknown = sorted(set(feature_values) - set(features))
    if missing or unknown:
        details = []
        if missing:
            details.append(f"thiếu: {', '.join(missing)}")
        if unknown:
            details.append(f"không hỗ trợ: {', '.join(unknown)}")
        raise ValueError("model_features không khớp inference schema (" + "; ".join(details) + ").")
    row = pd.DataFrame([{feature: feature_values[feature] for feature in features}])
    categorical = list(manifest["categorical_features"])
    for column in categorical:
        row[column] = row[column].fillna("MISSING").astype(str)
    numeric = [column for column in features if column not in categorical]
    for column in numeric:
        row[column] = pd.to_numeric(row[column], errors="raise")

    model = CatBoostClassifier()
    model.load_model(source / BUNDLE_MODEL_NAME)
    pool = Pool(row, cat_features=categorical)
    probability = float(model.predict_proba(pool)[0, 1])
    shap = np.asarray(model.get_feature_importance(pool, type="ShapValues"))[0, :-1]
    ranked = np.argsort(np.abs(shap))[::-1][:top_n_reasons]
    reasons = tuple(
        LocalReason(
            feature=features[index],
            contribution=float(shap[index]),
            direction="tăng" if shap[index] >= 0 else "giảm",
        )
        for index in ranked
    )
    return IndividualModelResult(
        target_probability=probability,
        target_definition=str(manifest["target_definition"]),
        model_name=str(manifest["model_name"]),
        setting=str(manifest["setting"]),
        run_id=str(manifest["run_id"]),
        local_reasons=reasons,
    )
