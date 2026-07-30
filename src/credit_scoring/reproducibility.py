"""Reproducibility helpers."""

from __future__ import annotations

import os
import random


def set_global_seed(seed: int = 42) -> None:
    """Set Python, NumPy and common hash seeds when those libraries exist."""

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
