"""Reproducible experiment entry points."""

from credit_scoring.experiments.ablation import (
    AblationResult,
    PreparedDataset,
    run_ablation,
)
from credit_scoring.experiments.home_credit_application import (
    E01_REFERENCE_OOF_AUC,
    E02_ABLATION_EXPERIMENTS,
    E02Comparison,
    PreparedApplicationData,
    prepare_application_data,
    resolve_e02_ablation_experiments,
    run_e01_e02_comparison,
)
from credit_scoring.experiments.home_credit_credit_amount_factorial import (
    E02FinalSelection,
    compare_e01_to_current_e02_a,
    nrd_reproduces_current_e02_a,
    prepare_credit_amount_factorial_data,
    resolve_credit_amount_factorial_experiments,
    select_e02_final,
)

__all__ = [
    "E01_REFERENCE_OOF_AUC",
    "E02_ABLATION_EXPERIMENTS",
    "AblationResult",
    "E02Comparison",
    "E02FinalSelection",
    "PreparedApplicationData",
    "PreparedDataset",
    "compare_e01_to_current_e02_a",
    "nrd_reproduces_current_e02_a",
    "prepare_application_data",
    "prepare_credit_amount_factorial_data",
    "resolve_credit_amount_factorial_experiments",
    "resolve_e02_ablation_experiments",
    "run_ablation",
    "run_e01_e02_comparison",
    "select_e02_final",
]
