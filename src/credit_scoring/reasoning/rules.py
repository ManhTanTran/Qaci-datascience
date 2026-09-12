"""Rule Knowledge Base contracts and validation for alternative-data reasoning."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RULE_TYPES = ("interpretation", "evidence_priority", "guardrail", "cross_domain", "limitation")
RULE_SOURCES = ("ml_discovery", "domain_rule", "failure_analysis", "human")
RULE_STATUSES = ("candidate", "validated", "rejected", "deprecated")
CONFIDENCES = ("low", "medium", "high")
VALIDATION_CHECKS = (
    "data_support",
    "holdout",
    "logical_consistency",
    "causal_claim_check",
    "human_review",
)
VALIDATION_STATES = ("passed", "not_run", "pending", "failed", "not_applicable")
_RULE_ID_PATTERN = re.compile(r"^RULE_[A-Z0-9]+_[0-9]{3}$")
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+$")
_CAUSAL_MARKERS = ("causes", "caused by", "gây ra", "chứng minh", "dẫn đến")


@dataclass(frozen=True)
class RuleRecord:
    """Normalized representation of one knowledge-base rule."""

    id: str
    type: str
    domains: tuple[str, ...]
    features: tuple[str, ...]
    rule: str
    source: str
    evidence: str
    limitation: str
    confidence: str
    status: str
    version: str
    owner: str
    validation: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "domains": list(self.domains),
            "features": list(self.features),
            "rule": self.rule,
            "source": self.source,
            "evidence": self.evidence,
            "limitation": self.limitation,
            "confidence": self.confidence,
            "status": self.status,
            "version": self.version,
            "owner": self.owner,
            "validation": dict(self.validation),
        }


def validate_rule_payload(
    payload: Mapping[str, Any],
    *,
    known_features: Collection[str] = (),
) -> None:
    """Validate one rule without promoting it or evaluating its truth.

    Promotion requires evidence and review outside this structural validator.
    Causal wording is rejected by default because the supplied bundle contains
    no causal identification evidence.
    """

    required = {
        "id",
        "type",
        "domains",
        "features",
        "rule",
        "source",
        "evidence",
        "limitation",
        "confidence",
        "status",
        "version",
        "owner",
        "validation",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError("Rule is missing fields: " + ", ".join(missing))
    if not isinstance(payload["id"], str) or not _RULE_ID_PATTERN.fullmatch(payload["id"]):
        raise ValueError("Rule id must match RULE_<DOMAIN>_<3-digit-number>.")
    for field, allowed in (
        ("type", RULE_TYPES),
        ("source", RULE_SOURCES),
        ("confidence", CONFIDENCES),
        ("status", RULE_STATUSES),
    ):
        if payload[field] not in allowed:
            raise ValueError(f"{field} must be one of: {', '.join(allowed)}.")
    if not isinstance(payload["version"], str) or not _VERSION_PATTERN.fullmatch(payload["version"]):
        raise ValueError("Rule version must use numeric major.minor format.")
    for field in ("domains", "features"):
        values = payload[field]
        if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values):
            raise ValueError(f"{field} must be a non-empty list of strings.")
    for field in ("rule", "evidence", "limitation", "owner"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ValueError(f"{field} must be a non-empty string.")
    validation = payload["validation"]
    if not isinstance(validation, Mapping):
        raise TypeError("validation must be an object.")
    missing_checks = sorted(set(VALIDATION_CHECKS) - set(validation))
    if missing_checks:
        raise ValueError("validation is missing checks: " + ", ".join(missing_checks))
    for check in VALIDATION_CHECKS:
        if validation[check] not in VALIDATION_STATES:
            raise ValueError(f"validation.{check} has an unsupported state.")

    feature_set = set(known_features)
    if feature_set:
        unknown = sorted(set(payload["features"]) - feature_set)
        if unknown:
            raise ValueError("Rule references unknown features: " + ", ".join(unknown))
    text = f"{payload['rule']} {payload['evidence']}".lower()
    if any(marker in text for marker in _CAUSAL_MARKERS):
        raise ValueError("Rule contains unsupported causal wording.")
    if payload["status"] == "validated":
        required_passes = ("data_support", "logical_consistency", "causal_claim_check", "human_review")
        if any(validation[check] != "passed" for check in required_passes):
            raise ValueError("A validated rule requires passed support, logic, causal and human-review checks.")


def normalize_rule_payload(
    payload: Mapping[str, Any],
    *,
    known_features: Collection[str] = (),
) -> RuleRecord:
    """Validate and convert a mapping into an immutable RuleRecord."""

    validate_rule_payload(payload, known_features=known_features)
    return RuleRecord(
        id=str(payload["id"]),
        type=str(payload["type"]),
        domains=tuple(payload["domains"]),
        features=tuple(payload["features"]),
        rule=str(payload["rule"]),
        source=str(payload["source"]),
        evidence=str(payload["evidence"]),
        limitation=str(payload["limitation"]),
        confidence=str(payload["confidence"]),
        status=str(payload["status"]),
        version=str(payload["version"]),
        owner=str(payload["owner"]),
        validation={str(key): str(value) for key, value in payload["validation"].items()},
    )


def load_rules_yaml(
    path: str | Path,
    *,
    known_features: Collection[str] = (),
) -> tuple[RuleRecord, ...]:
    """Load and validate a YAML rule bundle using the optional dev dependency."""

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Loading YAML rules requires PyYAML.") from exc
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("rules"), list):
        raise TypeError("Rule Knowledge Base must be an object with a rules list.")
    records = tuple(
        normalize_rule_payload(rule, known_features=known_features)
        for rule in document["rules"]
    )
    ids = [rule.id for rule in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Rule IDs must be unique.")
    return records
