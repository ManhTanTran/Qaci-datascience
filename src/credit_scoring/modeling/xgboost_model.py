"""Optional XGBoost model factory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_xgboost_model(model_config: Mapping[str, Any] | None = None) -> Any:
    """Build XGBoost lazily; this is not used by the first notebook."""

    try:
        from xgboost import XGBClassifier
    except ImportError as exc:
        raise ImportError("XGBoost is an optional modeling dependency.") from exc
    defaults = {"objective": "binary:logistic", "eval_metric": "auc", "random_state": 42}
    return XGBClassifier(**{**defaults, **dict(model_config or {})})
