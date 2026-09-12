"""Provider-neutral Agent Harness for alternative-data reasoning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from credit_scoring.reasoning.feature_registry import normalize_customer_features
from credit_scoring.reasoning.prompt_builder import build_reasoning_payload, build_reasoning_prompt
from credit_scoring.reasoning.retriever import DetectedDomains, detect_domains, retrieve_rules
from credit_scoring.reasoning.rules import RuleRecord
from credit_scoring.reasoning.schemas import validate_reasoning_output


class Reasoner(Protocol):
    """Minimal adapter contract implemented by OpenAI/Gemini/local clients."""

    def complete(self, prompt: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class HarnessResult:
    normalized_features: dict[str, Any]
    detected: DetectedDomains
    retrieved_rules: tuple[RuleRecord, ...]
    prompt: str
    output: Mapping[str, Any] | None
    llm_called: bool


def run_reasoning_harness(
    customer_features: Mapping[str, Any],
    *,
    feature_index: Mapping[str, Mapping[str, Any]],
    rules: tuple[RuleRecord, ...],
    reasoner: Reasoner | None = None,
) -> HarnessResult:
    """Normalize, detect, retrieve, build and optionally validate an LLM result."""

    normalized = normalize_customer_features(customer_features)
    detected = detect_domains(normalized, feature_index)
    retrieved = retrieve_rules(
        rules,
        detected_domains=detected.domains,
        observed_features=detected.observed_features,
    )
    payload = build_reasoning_payload(
        normalized,
        feature_index=feature_index,
        relevant_rules=retrieved,
        missing_features=detected.missing_features,
    )
    prompt = build_reasoning_prompt(payload)
    if reasoner is None:
        return HarnessResult(normalized, detected, retrieved, prompt, None, False)
    output = reasoner.complete(prompt)
    validate_reasoning_output(
        output,
        known_features=feature_index,
        known_rule_ids={rule.id for rule in retrieved},
    )
    return HarnessResult(normalized, detected, retrieved, prompt, output, True)
