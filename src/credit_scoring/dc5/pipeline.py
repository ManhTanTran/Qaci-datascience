"""One-call orchestration, caching and CLI for the DC5 research pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from credit_scoring.dc5.analysis import build_eda
from credit_scoring.dc5.clustering import run_clustering, validate_clustering_schema
from credit_scoring.dc5.config import PipelineConfig, load_config
from credit_scoring.dc5.data import (
    TARGET_COLUMN,
    load_prepared_frame,
    prepare_population,
    summarize_population,
    validate_prepared_schema,
)
from credit_scoring.dc5.modeling import run_model_suite
from credit_scoring.dc5.reporting import write_run_artifacts


@dataclass(frozen=True)
class PipelineRun:
    """Paths and aggregate outputs returned to notebooks and the UI."""

    report_path: Path
    run_dir: Path
    metrics: pd.DataFrame
    cached: bool

    def display(self) -> None:
        """Render a link in Jupyter, with a plain-text fallback."""

        try:
            from IPython.display import HTML, display
        except ImportError:  # pragma: no cover - notebook-only convenience
            print(self.report_path)
            return
        display(HTML(f'<a href="{self.report_path.as_uri()}" target="_blank">Mở báo cáo DC5</a>'))


def smoke_check() -> None:
    """Fast synthetic assertion executed before a notebook reads real data."""

    synthetic = pd.DataFrame(
        {
            "user_id": ["synthetic-a", "synthetic-b"],
            "has_telco": [1, 1],
            "household_type": ["Nhà thường", "Nhà thường"],
            "telco_monetary_group_ord": [3, 4],
        }
    )
    prepared = prepare_population(synthetic)
    assert prepared[TARGET_COLUMN].tolist() == [0, 1]
    assert prepared["user_id"].is_unique


def _dataset_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "resolved_path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _run_fingerprint(config: PipelineConfig, signature: dict[str, Any]) -> str:
    payload = {"config": config.to_dict(), "dataset": signature, "pipeline_version": "dc5-v1"}
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:16]


def _read_cached_run(run_dir: Path) -> PipelineRun:
    report_path = (run_dir / "report.html").resolve()
    metrics_path = run_dir / "metrics.csv"
    if not report_path.is_file() or not metrics_path.is_file():
        raise FileNotFoundError(f"Cached run is incomplete: {run_dir.resolve()}")
    return PipelineRun(
        report_path=report_path,
        run_dir=run_dir.resolve(),
        metrics=pd.read_csv(metrics_path),
        cached=True,
    )


def _latest_run(output_dir: Path) -> PipelineRun:
    pointer = output_dir / "latest.json"
    if not pointer.is_file():
        raise FileNotFoundError(f"No previous DC5 run found in {output_dir.resolve()}.")
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    return _read_cached_run(Path(payload["run_dir"]))


def _write_latest_pointer(output_dir: Path, run_dir: Path, report_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(
        json.dumps(
            {"run_dir": str(run_dir.resolve()), "report_path": str(report_path.resolve())},
            indent=2,
        ),
        encoding="utf-8",
    )
    relative_report = report_path.relative_to(output_dir.resolve()).as_posix()
    (output_dir / "latest.html").write_text(
        "<!doctype html><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='0; url={relative_report}'>"
        f"<a href='{relative_report}'>Mở báo cáo mới nhất</a>",
        encoding="utf-8",
    )


def run_pipeline(
    config_path: str | Path | None = None,
    *,
    config: PipelineConfig | None = None,
    force: bool = False,
) -> PipelineRun:
    """Run the prepared-data pipeline or reuse artifacts with an identical fingerprint."""

    if (config_path is None) == (config is None):
        raise ValueError("Pass exactly one of config_path or config.")
    resolved_config = load_config(config_path) if config_path is not None else config
    assert resolved_config is not None
    resolved_config.validate()
    output_dir = resolved_config.output_dir.resolve()
    if resolved_config.mode == "report-only":
        return _latest_run(output_dir)

    data_path = resolved_config.data_path
    if not data_path.is_file():
        raise FileNotFoundError(
            f"Prepared dataset not found: {data_path.resolve()}. "
            "Set data_path in configs/dc5_customer_analysis.yaml."
        )
    signature = _dataset_signature(data_path)
    run_id = _run_fingerprint(resolved_config, signature)
    run_dir = output_dir / "runs" / run_id
    if not force and (run_dir / "report.html").is_file():
        cached = _read_cached_run(run_dir)
        _write_latest_pointer(output_dir, run_dir, cached.report_path)
        return cached

    frame = load_prepared_frame(data_path)
    model_names = resolved_config.resolved_model_names()
    validate_prepared_schema(
        frame,
        requested_models=model_names,
        include_city_comparison=resolved_config.include_city_comparison,
    )
    if resolved_config.mode == "full" and resolved_config.clustering_enabled:
        validate_clustering_schema(frame)
    population = prepare_population(
        frame,
        individual_customers_only=resolved_config.individual_customers_only,
    )
    results = run_model_suite(
        population,
        model_names=model_names,
        include_city_comparison=resolved_config.include_city_comparison,
        n_splits=resolved_config.effective_n_splits(),
        random_state=resolved_config.validation.random_state,
        model_config=resolved_config.model,
    )
    all_model_features = tuple(
        dict.fromkeys(feature for result in results for feature in result.features)
    )
    eda = build_eda(frame, population, model_features=all_model_features)
    clustering = None
    if resolved_config.mode == "full" and resolved_config.clustering_enabled:
        clustering = run_clustering(
            frame,
            n_clusters=resolved_config.n_clusters,
            random_state=resolved_config.validation.random_state,
        )
    metadata = {
        "run_id": run_id,
        "pipeline_version": "dc5-v1",
        "config": resolved_config.to_dict(),
        "dataset": signature,
        "status": "research_candidate",
        "clustering": (
            {
                "enabled": True,
                "n_input_rows": clustering.n_input_rows,
                "n_complete_rows": clustering.n_complete_rows,
                "silhouette": clustering.silhouette,
                "pca_explained_variance": clustering.pca_explained_variance,
            }
            if clustering is not None
            else {"enabled": False}
        ),
    }
    report_path, metrics, _importance, _fold_metrics = write_run_artifacts(
        results,
        eda=eda,
        clustering=clustering,
        population_summary=summarize_population(population),
        metadata=metadata,
        run_dir=run_dir,
        top_n_importance=resolved_config.top_n_importance,
    )
    _write_latest_pointer(output_dir, run_dir, report_path)
    return PipelineRun(
        report_path=report_path,
        run_dir=run_dir.resolve(),
        metrics=metrics,
        cached=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DC5 customer analysis pipeline.")
    parser.add_argument("--config", default="configs/dc5_customer_analysis.yaml")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_pipeline(args.config, force=args.force)
    print(result.report_path)


if __name__ == "__main__":  # pragma: no cover
    main()
