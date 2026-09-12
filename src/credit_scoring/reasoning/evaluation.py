"""Deterministic baseline evaluation helpers for the simulate bundle.

These helpers produce checks, not fabricated quality scores. Aggregate rates
are only calculated when callers provide actual response records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Assessment = Literal["Relatively stable", "Mixed", "Potentially risky"]
SCENARIO_CUSTOMER_NUMBERS = {"A_stable": 1, "B_conflict": 2, "C_deteriorating": 3}

_ONE_SHOT_PATTERN = re.compile(
    r"Customer\s*(?P<number>[1-3])\s*[—-]\s*\*\*(?P<assessment>[^*]+)\*\*",
    flags=re.IGNORECASE,
)
_CUSTOMER_SECTION_PATTERN = re.compile(
    r"(?:^|\n)[ \t]*#{2,4}\s*(?:[1-3]\.\s*)?(?:Customer|Khách hàng)\s*(?P<number>[1-3])\b(?P<body>.*?)(?=\n[ \t]*#{2,4}\s*(?:[1-3]\.\s*)?(?:Customer|Khách hàng)\s*[1-3]\b|\Z)",
    flags=re.IGNORECASE | re.DOTALL,
)
_SECTION_ASSESSMENT_PATTERN = re.compile(
    r"Overall assessment\s*:\s*\**\s*(?P<assessment>Relatively stable|Mixed|Potentially risky)",
    flags=re.IGNORECASE,
)


def _normalize_assessment(value: str) -> Assessment | None:
    return next(
        (
            item
            for item in ("Relatively stable", "Mixed", "Potentially risky")
            if item.lower() == value.strip().lower()
        ),
        None,
    )


@dataclass(frozen=True)
class EvaluationRecord:
    """A response reference; raw attachment content stays outside Git."""

    model: str
    turn: Literal["one_shot", "counter_argument"]
    response_file: str
    prompt_variant: str | None = None


def parse_one_shot_assessments(text: str) -> dict[int, Assessment]:
    """Extract the explicit per-customer labels used by the sample outputs."""

    assessments: dict[int, Assessment] = {}
    for match in _ONE_SHOT_PATTERN.finditer(text):
        normalized = _normalize_assessment(match.group("assessment"))
        if normalized is not None:
            assessments[int(match.group("number"))] = normalized  # type: ignore[assignment]
    for match in _CUSTOMER_SECTION_PATTERN.finditer(text):
        assessment_match = _SECTION_ASSESSMENT_PATTERN.search(match.group("body"))
        if assessment_match is not None:
            normalized = _normalize_assessment(assessment_match.group("assessment"))
            if normalized is not None:
                assessments[int(match.group("number"))] = normalized
    return assessments


def evaluate_text_response(text: str, *, turn: Literal["one_shot", "counter_argument"] = "one_shot") -> dict[str, object]:
    """Return auditable response checks without interpreting correctness.

    A counter-argument response is not parsed as a final classification because
    the attachment does not preserve the exact counter prompt or a structured
    final answer. The limitation is returned explicitly.
    """

    assessments = parse_one_shot_assessments(text) if turn == "one_shot" else {}
    lower = text.lower()
    return {
        "turn": turn,
        "parsed_assessments": assessments,
        "coverage_complete": set(assessments) == {1, 2, 3} if turn == "one_shot" else None,
        "proxy_distinction_present": any(
            marker in lower for marker in ("proxy", "gián tiếp", "không trực tiếp")
        ),
        "conflict_handling_present": any(
            marker in lower for marker in ("mâu thuẫn", "conflict", "đối lập")
        ),
        "missingness_awareness_present": any(
            marker in lower
            for marker in ("thiếu dữ liệu", "thiếu hụt", "không có dữ liệu", "khuyết", "missing")
        ),
        "causal_caution_present": any(
            marker in lower for marker in ("không chứng minh", "không phải quan hệ nhân quả", "không đồng nghĩa")
        ),
        "counter_prompt_linkage_available": turn == "one_shot",
        "notes": (
            "Counter response requires the original prompt and a final structured output before scoring stability."
            if turn == "counter_argument"
            else "Checks are descriptive; no gold-label accuracy is inferred."
        ),
    }
