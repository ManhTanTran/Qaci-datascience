"""Aggregate-only model evidence supplied to guarded LLM interpretations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.dc5.data import MODEL_DESCRIPTIONS
from credit_scoring.dc5.inference import BUNDLE_MANIFEST_NAME, BUNDLE_MODEL_NAME


@dataclass(frozen=True)
class FeatureEvidence:
    feature: str
    importance: float


@dataclass(frozen=True)
class ModelEvidence:
    run_id: str
    backend: str
    model_name: str
    setting: str
    model_description: str
    target_definition: str
    roc_auc: float
    pr_auc: float
    positive_rate: float
    top_features: tuple[FeatureEvidence, ...]
    inference_available: bool
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe aggregate payload containing no customer rows."""

        return asdict(self)


def load_latest_model_evidence(
    output_dir: str | Path = "artifacts/dc5_customer_analysis",
    *,
    top_n: int = 5,
) -> ModelEvidence | None:
    """Read the best validation result from the latest research run.

    This deliberately does not claim individual inference: current DC5 runs
    persist cross-validation metrics and global importance, but not a fitted
    production inference bundle.
    """

    root = Path(output_dir).resolve()
    pointer = root / "latest.json"
    if not pointer.is_file():
        return None
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    run_dir = Path(payload["run_dir"]).resolve()
    if root not in run_dir.parents:
        raise ValueError("Latest run must stay inside the configured artifact directory.")

    metadata_path = run_dir / "run_metadata.json"
    metrics_path = run_dir / "metrics.csv"
    importance_path = run_dir / "feature_importance.csv"
    if not all(path.is_file() for path in (metadata_path, metrics_path, importance_path)):
        return None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(metrics_path)
    required_metrics = {"setting", "model", "roc_auc", "pr_auc", "positive_rate"}
    if metrics.empty or not required_metrics.issubset(metrics.columns):
        return None
    best = metrics.sort_values(["roc_auc", "pr_auc"], ascending=False).iloc[0]

    importance = pd.read_csv(importance_path)
    required_importance = {"setting", "model", "feature", "importance"}
    if not required_importance.issubset(importance.columns):
        return None
    selected = (
        importance.loc[
            importance["setting"].eq(best["setting"])
            & importance["model"].eq(best["model"])
        ]
        .sort_values("importance", ascending=False)
        .head(top_n)
    )
    features = tuple(
        FeatureEvidence(feature=str(row.feature), importance=float(row.importance))
        for row in selected.itertuples(index=False)
    )
    backend = str(metadata.get("config", {}).get("model", {}).get("backend", "unknown"))
    model_name = str(best["model"])
    inference_available = all(
        (run_dir / name).is_file() for name in (BUNDLE_MODEL_NAME, BUNDLE_MANIFEST_NAME)
    )
    return ModelEvidence(
        run_id=str(metadata.get("run_id", run_dir.name)),
        backend=backend,
        model_name=model_name,
        setting=str(best["setting"]),
        model_description=MODEL_DESCRIPTIONS.get(model_name, "Không có mô tả model."),
        target_definition="target_high_telco_monetary (telco_monetary_group_ord == 4)",
        roc_auc=float(best["roc_auc"]),
        pr_auc=float(best["pr_auc"]),
        positive_rate=float(best["positive_rate"]),
        top_features=features,
        inference_available=inference_available,
        limitation=(
            "Metric và importance là aggregate từ cross-validation. Bundle inference đã "
            "sẵn sàng nhưng chỉ chạy dự đoán cá nhân khi request có đủ model_features."
            if inference_available
            else "Metric và importance là aggregate từ cross-validation; run này chưa có "
            "CatBoost inference bundle."
        ),
    )
