"""Typed configuration for the DC5 research pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

PipelineMode = Literal["quick", "full", "report-only"]
ModelBackend = Literal["catboost", "logistic"]


@dataclass(frozen=True)
class ValidationConfig:
    """Reproducible validation settings shared by every model variant."""

    n_splits: int = 5
    random_state: int = 42

    def validate(self) -> None:
        if self.n_splits < 2:
            raise ValueError("validation.n_splits must be at least 2.")


@dataclass(frozen=True)
class ModelConfig:
    """Estimator settings; CatBoost remains the notebook-compatible default."""

    backend: ModelBackend = "catboost"
    iterations: int = 500
    depth: int = 6
    learning_rate: float = 0.05

    def validate(self) -> None:
        if self.backend not in {"catboost", "logistic"}:
            raise ValueError(f"Unsupported model backend: {self.backend}")
        if self.iterations < 1:
            raise ValueError("model.iterations must be positive.")
        if self.depth < 1:
            raise ValueError("model.depth must be positive.")
        if self.learning_rate <= 0:
            raise ValueError("model.learning_rate must be positive.")


@dataclass(frozen=True)
class PipelineConfig:
    """End-to-end pipeline configuration."""

    data_path: Path = Path("data_extracted/model_df_extracted.parquet")
    output_dir: Path = Path("artifacts/dc5_customer_analysis")
    mode: PipelineMode = "quick"
    model_names: tuple[str, ...] = ()
    include_city_comparison: bool = True
    individual_customers_only: bool = True
    clustering_enabled: bool = True
    n_clusters: int = 4
    top_n_importance: int = 15
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    def validate(self) -> None:
        if self.mode not in {"quick", "full", "report-only"}:
            raise ValueError(f"Unsupported pipeline mode: {self.mode}")
        if self.top_n_importance < 1:
            raise ValueError("top_n_importance must be positive.")
        if self.n_clusters < 2:
            raise ValueError("n_clusters must be at least 2.")
        allowed_models = {"M0", "M1", "M2", "M3", "M4"}
        unknown = sorted(set(self.resolved_model_names()).difference(allowed_models))
        if unknown:
            raise ValueError(f"Unknown model variants: {unknown}")
        self.validation.validate()
        self.model.validate()

    def resolved_model_names(self) -> tuple[str, ...]:
        """Return explicit variants or the mode-specific default set."""

        if self.model_names:
            return self.model_names
        if self.mode == "quick":
            return ("M0", "M1", "M4")
        return ("M0", "M1", "M2", "M3", "M4")

    def effective_n_splits(self) -> int:
        """Quick mode trades variance estimation for faster feedback."""

        return min(self.validation.n_splits, 3) if self.mode == "quick" else self.validation.n_splits

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["data_path"] = str(self.data_path)
        payload["output_dir"] = str(self.output_dir)
        return payload


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise ImportError('YAML config requires: python -m pip install -e ".[dc5]"') from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError("Pipeline config root must be a mapping.")
    return payload


def load_config(path: str | Path) -> PipelineConfig:
    """Load YAML and resolve relative artifact paths from the config directory."""

    config_path = Path(path)
    payload = _load_yaml(config_path)
    validation = ValidationConfig(**payload.pop("validation", {}))
    model = ModelConfig(**payload.pop("model", {}))
    config_dir = config_path.resolve().parent
    if "data_path" in payload:
        data_path = Path(payload["data_path"])
        payload["data_path"] = (
            data_path if data_path.is_absolute() else (config_dir / data_path).resolve()
        )
    if "output_dir" in payload:
        output_dir = Path(payload["output_dir"])
        payload["output_dir"] = (
            output_dir if output_dir.is_absolute() else (config_dir / output_dir).resolve()
        )
    if "model_names" in payload:
        payload["model_names"] = tuple(payload["model_names"] or ())
    config = PipelineConfig(validation=validation, model=model, **payload)
    config.validate()
    return config
