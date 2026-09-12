"""Reusable contracts for alternative-data LLM reasoning experiments."""

from credit_scoring.reasoning.evaluation import (
    EvaluationRecord,
    evaluate_text_response,
    parse_one_shot_assessments,
)
from credit_scoring.reasoning.feature_registry import (
    feature_registry_index,
    load_feature_definitions_yaml,
    normalize_customer_features,
)
from credit_scoring.reasoning.harness import HarnessResult, run_reasoning_harness
from credit_scoring.reasoning.llm_client import (
    LLMClientConfig,
    StructuredLLMReasoner,
    create_reasoner_from_environment,
)
from credit_scoring.reasoning.retriever import DetectedDomains, detect_domains, retrieve_rules
from credit_scoring.reasoning.rules import (
    RuleRecord,
    load_rules_yaml,
    normalize_rule_payload,
    validate_rule_payload,
)
from credit_scoring.reasoning.schemas import validate_reasoning_output

__all__ = [
    "DetectedDomains",
    "EvaluationRecord",
    "HarnessResult",
    "LLMClientConfig",
    "RuleRecord",
    "StructuredLLMReasoner",
    "create_reasoner_from_environment",
    "detect_domains",
    "evaluate_text_response",
    "feature_registry_index",
    "load_feature_definitions_yaml",
    "load_rules_yaml",
    "normalize_customer_features",
    "normalize_rule_payload",
    "parse_one_shot_assessments",
    "retrieve_rules",
    "run_reasoning_harness",
    "validate_reasoning_output",
    "validate_rule_payload",
]
