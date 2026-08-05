"""Reusable feature engineering for public credit-scoring datasets."""

from credit_scoring.features.home_credit_application import (
    E02_FEATURE_FAMILIES,
    build_aligned_application_features,
    build_e01_application_features,
    build_e02_application_features,
)
from credit_scoring.features.home_credit_credit_amount_factorial import (
    CREDIT_AMOUNT_FACTOR_ORDER,
    CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS,
    build_aligned_credit_amount_factorial_features,
    build_credit_amount_factorial_features,
    describe_credit_amount_factors,
    summarize_feature_matrix_differences,
)
from credit_scoring.numeric import safe_divide

__all__ = [
    "CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS",
    "CREDIT_AMOUNT_FACTOR_ORDER",
    "E02_FEATURE_FAMILIES",
    "build_aligned_application_features",
    "build_aligned_credit_amount_factorial_features",
    "build_credit_amount_factorial_features",
    "build_e01_application_features",
    "build_e02_application_features",
    "describe_credit_amount_factors",
    "safe_divide",
    "summarize_feature_matrix_differences",
]
