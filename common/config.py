"""Load `config.yaml` (+ `.env` for secrets) into one validated object.

Secrets never live in config.yaml: it only names the environment variables to read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessingConfig:
    batch_size: int = 20
    poll_interval_seconds: float = 2.0
    stable_file_checks: int = 2
    retry_failed: bool = True
    max_retries: int = 3
    retry_backoff_seconds: float = 60.0
    single_worker: bool = True


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai"  # "openai" = any OpenAI-compatible endpoint
    model: str = "gpt-4o-mini"
    api_key_env: str = "EXTRACTOR_API_KEY"
    base_url_env: str = "EXTRACTOR_BASE_URL"
    temperature: float = 0.0
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class QualityConfig:
    failed_rate: float = 0.10
    rejected_rate: float = 0.25
    flagged_rate: float = 0.30
    empty_rate: float = 0.60
    min_sample: int = 20


@dataclass(frozen=True)
class Module1Cost:
    """Prices for module 1. None = not configured, so no cost is shown (never guessed)."""

    model_input_per_1m: float | None = None
    model_output_per_1m: float | None = None
    search_per_call: float | None = None  # Tavily: price of one basic search


@dataclass(frozen=True)
class Module2Cost:
    input_per_1m: float | None = None
    output_per_1m: float | None = None


@dataclass(frozen=True)
class CostConfig:
    currency: str = "USD"
    module1: Module1Cost = field(default_factory=Module1Cost)
    module2: Module2Cost = field(default_factory=Module2Cost)


@dataclass(frozen=True)
class UIConfig:
    host: str = "127.0.0.1"
    port: int = 8768
    allow_mode_switch: bool = True


@dataclass(frozen=True)
class Config:
    root: Path
    input_file: Path
    database_file: Path
    export_dir: Path
    mode: str = "manual"  # "manual": runs start from UI/CLI; "auto": watcher processes new data
    domain: str = "real_estate"
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    log_level: str = "INFO"
    log_file: Path | None = None

    @property
    def auto(self) -> bool:
        return self.mode == "auto"


def load_env_file(path: Path) -> None:
    """KEY=VALUE lines; never overrides variables already set in the process."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _section(raw: dict[str, Any], name: str, cls: type) -> Any:
    values = raw.get(name) or {}
    if not isinstance(values, dict):
        raise ConfigError(f"'{name}' must be a mapping")
    unknown = set(values) - set(cls.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"unknown keys in '{name}': {', '.join(sorted(unknown))}")
    return cls(**values)


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path or os.environ.get("PIPELINE_CONFIG") or REPO_ROOT / "config.yaml")
    if not config_path.is_file():
        raise ConfigError(f"config file not found: {config_path}")
    root = config_path.resolve().parent
    load_env_file(root / ".env")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    def rel(value: str | None, default: str) -> Path:
        target = Path(value or default)
        return target if target.is_absolute() else root / target

    processing = _section(raw, "processing", ProcessingConfig)
    llm = _section(raw, "llm", LLMConfig)
    quality = _section(raw, "quality", QualityConfig)
    ui = _section(raw, "ui", UIConfig)
    cost_raw = raw.get("cost") or {}
    cost = CostConfig(
        currency=str(cost_raw.get("currency", "USD")),
        module1=_section(cost_raw, "module1", Module1Cost),
        module2=_section(cost_raw, "module2", Module2Cost),
    )
    for price in (*vars(cost.module1).values(), *vars(cost.module2).values()):
        if price is not None and (not isinstance(price, (int, float)) or price < 0):
            raise ConfigError("cost prices must be numbers >= 0 (or empty)")
    logging_cfg = raw.get("logging") or {}
    mode = str(raw.get("mode", "manual")).lower()
    if mode not in {"manual", "auto"}:
        raise ConfigError("mode must be 'manual' or 'auto'")
    if processing.batch_size < 1 or processing.max_retries < 1:
        raise ConfigError("processing.batch_size and processing.max_retries must be >= 1")
    if processing.stable_file_checks < 1 or processing.poll_interval_seconds <= 0:
        raise ConfigError("processing.stable_file_checks >= 1 and poll_interval_seconds > 0 required")
    if not processing.single_worker:
        raise ConfigError("processing.single_worker=false is not supported (SQLite, one writer)")
    log_file = logging_cfg.get("file")
    return Config(
        root=root,
        input_file=rel(raw.get("input_file"), "data/llm_answers.jsonl"),
        database_file=rel(raw.get("database_file"), "data/claims.db"),
        export_dir=rel(raw.get("export_dir"), "data/exports"),
        mode=mode,
        domain=str(raw.get("domain", "real_estate")),
        processing=processing,
        llm=llm,
        quality=quality,
        ui=ui,
        cost=cost,
        log_level=str(logging_cfg.get("level", "INFO")).upper(),
        log_file=rel(log_file, "logs/pipeline.log") if log_file else None,
    )
