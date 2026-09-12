"""Metadata-first rule retrieval for a small Knowledge Base."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from credit_scoring.reasoning.rules import RuleRecord


@dataclass(frozen=True)
class DetectedDomains:
    domains: tuple[str, ...]
    observed_features: tuple[str, ...]
    missing_features: tuple[str, ...]
    unknown_features: tuple[str, ...]


def detect_domains(
    customer_features: Mapping[str, Any],
    feature_index: Mapping[str, Mapping[str, Any]],
) -> DetectedDomains:
    """Detect domains from known, non-missing fields.

    A missing field remains a missing-information signal and does not activate a
    domain. Unknown fields are excluded from the prompt until explicitly added
    to the registry.
    """

    observed: list[str] = []
    missing: list[str] = []
    unknown: list[str] = []
    domains: set[str] = set()
    for feature, value in customer_features.items():
        definition = feature_index.get(feature)
        if definition is None:
            unknown.append(feature)
            continue
        if value is None:
            missing.append(feature)
            continue
        observed.append(feature)
        domains.add(str(definition["domain"]))
    return DetectedDomains(
        domains=tuple(sorted(domains)),
        observed_features=tuple(sorted(observed)),
        missing_features=tuple(sorted(missing)),
        unknown_features=tuple(sorted(unknown)),
    )


def retrieve_rules(
    rules: Sequence[RuleRecord],
    *,
    detected_domains: Collection[str],
    observed_features: Collection[str],
    include_limitations: bool = True,
) -> tuple[RuleRecord, ...]:
    """Retrieve candidate rules by domain/feature metadata with deterministic ranking."""

    domain_set = set(detected_domains)
    feature_set = set(observed_features)
    ranked: list[tuple[int, RuleRecord]] = []
    for rule in rules:
        if rule.type == "limitation" and not include_limitations:
            continue
        domain_hits = len(domain_set.intersection(rule.domains))
        feature_hits = len(feature_set.intersection(rule.features))
        score = domain_hits + (2 * feature_hits)
        if score:
            ranked.append((score, rule))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return tuple(rule for _, rule in ranked)
