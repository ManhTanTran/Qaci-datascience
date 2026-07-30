"""Optional CatBoost model factory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_catboost_model(model_config: Mapping[str, Any] | None = None) -> Any:
    """Build CatBoost lazily; this is not used by the first notebook."""

    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise ImportError("CatBoost is an optional modeling dependency.") from exc
    defaults = {"loss_function": "Logloss", "eval_metric": "AUC", "random_seed": 42, "verbose": False}
    return CatBoostClassifier(**{**defaults, **dict(model_config or {})})
