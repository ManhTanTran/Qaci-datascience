"""Domain registry. Add a new domain here to extend beyond real estate."""

from __future__ import annotations

from typing import Callable

from ..domain import Domain
from .real_estate import build_domain as _build_real_estate

_REGISTRY: dict[str, Callable[[], Domain]] = {
    "real_estate": _build_real_estate,
}


def get_domain(name: str) -> Domain:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"Unknown domain {name!r}. Available: {', '.join(sorted(_REGISTRY))}") from None


def available_domains() -> list[str]:
    return sorted(_REGISTRY)
