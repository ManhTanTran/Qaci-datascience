"""Lazy model factory so data-only workflows do not require every booster."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_model(model_name: str, model_config: Mapping[str, Any] | None = None) -> Any:
    """Build a supported model by name using lazy optional imports."""

    name = model_name.lower()
    config = dict(model_config or {})
    if name == "lightgbm":
        from credit_scoring.modeling.lightgbm_model import build_lightgbm_model

        return build_lightgbm_model(config)
    if name == "catboost":
        from credit_scoring.modeling.catboost_model import build_catboost_model

        return build_catboost_model(config)
    if name == "xgboost":
        from credit_scoring.modeling.xgboost_model import build_xgboost_model

        return build_xgboost_model(config)
    raise ValueError("Unknown model_name. Supported values: lightgbm, catboost, xgboost.")
