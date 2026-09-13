"""Deterministic rule evaluation; the result is never delegated to an LLM."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from credit_scoring.reasoning.mapping import default_mapping_path
from credit_scoring.reasoning.validation import INVALID

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"


def _default_rules_path() -> Path:
    return default_mapping_path().with_name("rules.yaml")


def _age_payload(profile: Mapping[str, Any]) -> Mapping[str, Any] | None:
    age = profile.get("age")
    return age if isinstance(age, Mapping) else None


def compare_age(age: Mapping[str, Any] | None, threshold: int = 23) -> str:
    """Compare exact/range age without assigning a midpoint to a range."""

    if not age or age.get("status") == "missing" or age.get("status") == "invalid":
        return UNKNOWN
    exact = age.get("exact")
    if exact is not None:
        return PASS if exact > threshold else FAIL
    minimum = age.get("min")
    maximum = age.get("max")
    if minimum is not None and minimum > threshold:
        return PASS
    if maximum is not None and maximum <= threshold:
        return FAIL
    return UNKNOWN


def _value(profile: Mapping[str, Any], dotted: str) -> Any:
    current: Any = profile
    for part in dotted.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _payment_result(profile: Mapping[str, Any], thresholds: Mapping[str, Any]) -> str:
    payment_group = profile.get("payment_history_12m")
    if isinstance(payment_group, Mapping) and payment_group.get("status") == INVALID:
        return UNKNOWN
    values = {
        "observed_months": _value(profile, "payment_history_12m.observed_months"),
        "late_months": _value(profile, "payment_history_12m.late_months"),
        "max_late_days": _value(profile, "payment_history_12m.max_late_days"),
    }
    if any(value is None for value in values.values()):
        return UNKNOWN
    try:
        return (
            PASS
            if values["observed_months"] >= thresholds["observed_months_min"]
            and values["late_months"] <= thresholds["late_months_max"]
            and values["max_late_days"] <= thresholds["max_late_days_max"]
            else FAIL
        )
    except (TypeError, KeyError):
        return UNKNOWN


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("Rule configuration requires PyYAML.") from exc
    rule_path = Path(path) if path is not None else _default_rules_path()
    payload = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("rules"), list):
        raise ValueError("Rule configuration must contain a rules list.")
    return dict(payload)


def evaluate_profile_rules(
    profile: Mapping[str, Any],
    rules_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return PASS/FAIL/UNKNOWN and detailed deterministic rule evidence."""

    config = rules_config or load_rules()
    rules = config["rules"]
    details: list[dict[str, Any]] = []
    age_rule = next(rule for rule in rules if rule["id"] == "AGE_OVER_23_RESEARCH")
    age_outcome = compare_age(_age_payload(profile), int(age_rule["value"]))
    age = _age_payload(profile)
    details.append(
        {
            "rule_id": age_rule["id"],
            "type": age_rule["type"],
            "input_value": age.get("exact") if age else None,
            "input_range": {
                "min": age.get("min") if age else None,
                "max": age.get("max") if age else None,
            },
            "result": age_outcome,
            "reason": {
                PASS: "Tuổi quan sát được chắc chắn lớn hơn 23.",
                FAIL: "Tuổi quan sát được không lớn hơn 23.",
                UNKNOWN: "Khoảng tuổi giao với ngưỡng 23 hoặc tuổi bị thiếu/không hợp lệ.",
            }[age_outcome],
            "official_hard_rule": bool(age_rule.get("official_hard_rule", False)),
        }
    )
    payment_rule = next(
        rule for rule in rules if rule["id"] == "PAYMENT_HISTORY_12M_SUPPORT"
    )
    payment_outcome = _payment_result(profile, payment_rule["thresholds"])
    details.append(
        {
            "rule_id": payment_rule["id"],
            "type": payment_rule["type"],
            "input_fields": list(payment_rule["fields"]),
            "result": payment_outcome,
            "reason": (
                "Lịch sử thanh toán đáp ứng điều kiện supporting evidence."
                if payment_outcome == PASS
                else "Lịch sử thanh toán có tín hiệu cần chú ý."
                if payment_outcome == FAIL
                else "Thiếu một hoặc nhiều trường lịch sử thanh toán."
            ),
            "official_hard_rule": False,
        }
    )
    decision = age_outcome
    return {
        "user_id": profile.get("user_id"),
        "decision": decision,
        "rule_result": decision,
        "rule_id": age_rule["id"],
        "input_value": details[0]["input_value"],
        "result": decision,
        "reason": details[0]["reason"],
        "policy_status": "research_only_boundary_unresolved",
        "rules": details,
    }


# Short name used by application callers.
evaluate_profile = evaluate_profile_rules
