"""Aggregate EDA tables safe for DC5 reports."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from credit_scoring.dc5.data import TARGET_COLUMN


@dataclass(frozen=True)
class EDAResult:
    """Aggregate-only EDA outputs; never contains a customer identifier."""

    domain_coverage: pd.DataFrame
    missingness: pd.DataFrame
    target_distribution: pd.DataFrame


def build_eda(
    prepared_frame: pd.DataFrame,
    population: pd.DataFrame,
    *,
    model_features: tuple[str, ...],
) -> EDAResult:
    """Summarize coverage, missingness and the modeled target."""

    domain_columns = [
        column
        for column in ("has_telco", "has_pharmacy", "has_retail", "has_app", "has_loyalty")
        if column in prepared_frame.columns
    ]
    coverage = (
        prepared_frame[domain_columns]
        .mean()
        .mul(100)
        .rename("coverage_pct")
        .rename_axis("domain")
        .reset_index()
        .sort_values("coverage_pct", ascending=False)
        .reset_index(drop=True)
    )
    selected = list(dict.fromkeys(model_features))
    missingness = (
        population[selected]
        .isna()
        .mean()
        .mul(100)
        .rename("missing_pct")
        .rename_axis("feature")
        .reset_index()
        .sort_values("missing_pct", ascending=False)
        .reset_index(drop=True)
    )
    target_distribution = (
        population[TARGET_COLUMN]
        .value_counts()
        .sort_index()
        .rename("count")
        .rename_axis("target")
        .reset_index()
    )
    target_distribution["share_pct"] = (
        target_distribution["count"] / len(population) * 100
    )
    return EDAResult(
        domain_coverage=coverage,
        missingness=missingness,
        target_distribution=target_distribution,
    )
