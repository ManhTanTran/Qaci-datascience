"""Shared contracts for the FPT credit-reasoning proof of concept.

The package contains deterministic ingestion, validation, profile/evidence and
rule helpers.  It deliberately has no dependency on Streamlit, notebooks or a
research experiment runner.
"""

from credit_scoring.reasoning.ai import (
    build_explanation_context,
    build_explanation_prompt,
    normalize_ai_response,
)
from credit_scoring.reasoning.ingestion import inspect_input, load_input
from credit_scoring.reasoning.mapping import BUSINESS_GROUPS, load_feature_mapping
from credit_scoring.reasoning.profiles import build_profile, build_profiles
from credit_scoring.reasoning.pipeline import FPTPipelineResult, run_fpt_pipeline
from credit_scoring.reasoning.rules import evaluate_profile_rules
from credit_scoring.reasoning.validation import validate_frame

__all__ = [
    "BUSINESS_GROUPS",
    "FPTPipelineResult",
    "build_explanation_context",
    "build_explanation_prompt",
    "build_profile",
    "build_profiles",
    "evaluate_profile_rules",
    "inspect_input",
    "load_feature_mapping",
    "load_input",
    "normalize_ai_response",
    "run_fpt_pipeline",
    "validate_frame",
]
