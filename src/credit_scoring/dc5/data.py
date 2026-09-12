"""Data contracts and population preparation for the DC5 research pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

TARGET_SOURCE = "telco_monetary_group_ord"
TARGET_COLUMN = "target_high_telco_monetary"

M0_FEATURES = (
    "age_group_ord",
    "gender",
    "household_type",
    "city",
)

RELATIONSHIP_FEATURES = (
    "active_domain_count_ord",
    "has_retail",
    "has_pharmacy",
    "has_app",
    "has_loyalty",
    "tenure_group_ord",
    "recency_group_ord",
    "app_count_group_ord",
    "app_tenure_group_ord",
    "app_recency_days_ord",
    "loyalty_points_ord",
    "loyalty_tier_ord",
)

PHARMACY_FEATURES = (
    "healthcare_last_order_date_ord",
    "healthcare_order_count_6m_ord",
    "healthcare_spend_6m_ord",
    "healthcare_aov_6m_ord",
    "healthcare_repeat_purchase_rate_6m_ord",
    "healthcare_vaccine_visit_count_12m_ord",
)

RETAIL_FEATURES = (
    "retail_last_order_date_ord",
    "retail_order_count_12m_ord",
    "retail_gmv_12m_ord",
    "retail_aov_12m_ord",
    "retail_max_device_product_price_segment_24m_ord",
    "retail_tradein_count_24m_ord",
    "retail_is_apple",
    "retail_has_phone_purchase",
    "retail_has_tradein",
    "retail_product_group",
)

TELCO_BEHAVIOR_FEATURES = (
    "telco_inbound_count_180d_ord",
    "telco_outbound_count_180d_ord",
    "telco_ticket_count_180d_ord",
    "telco_internet_usage_group_ord",
    "telco_internet_trend_group_ord",
)

MODEL_PARENTS: dict[str, str | None] = {
    "M0": None,
    "M1": "M0",
    "M2": "M1",
    "M3": "M1",
    "M4": "M1",
}

MODEL_DESCRIPTIONS = {
    "M0": "Baseline nhân khẩu học và loại hình hộ gia đình.",
    "M1": "M0 cộng mức độ quan hệ/engagement trên các domain và ứng dụng.",
    "M2": "M1 cộng hành vi mua sắm và sử dụng dịch vụ Pharmacy/Healthcare.",
    "M3": "M1 cộng hành vi mua sắm Retail, thiết bị và trade-in.",
    "M4": "M1 cộng hành vi sử dụng và tương tác dịch vụ Telco trong 180 ngày.",
}


def model_catalog(*, include_city: bool = True) -> list[dict[str, Any]]:
    """Describe the declared model ladder and its incremental feature groups."""

    schemas = feature_sets(include_city=include_city)
    rows = []
    for model, features in schemas.items():
        parent = MODEL_PARENTS[model]
        parent_features = set(schemas[parent]) if parent is not None else set()
        rows.append(
            {
                "model": model,
                "parent": parent,
                "description": MODEL_DESCRIPTIONS[model],
                "n_features": len(features),
                "added_features": [feature for feature in features if feature not in parent_features],
            }
        )
    return rows


def feature_sets(*, include_city: bool = True) -> dict[str, tuple[str, ...]]:
    """Return declared schemas for M0-M4; schemas never depend on observed data."""

    base = M0_FEATURES if include_city else tuple(col for col in M0_FEATURES if col != "city")
    relationship = base + RELATIONSHIP_FEATURES
    return {
        "M0": base,
        "M1": relationship,
        "M2": relationship + PHARMACY_FEATURES,
        "M3": relationship + RETAIL_FEATURES,
        "M4": relationship + TELCO_BEHAVIOR_FEATURES,
    }


def load_prepared_frame(data_path: str | Path) -> pd.DataFrame:
    """Load the prepared feature matrix from Parquet."""

    path = Path(data_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Prepared dataset not found: {path.resolve()}. "
            "Create model_df_extracted.parquet before running this pipeline."
        )
    frame = pd.read_parquet(path)
    if frame.empty:
        raise ValueError("Prepared dataset is empty.")
    return frame


def validate_prepared_schema(
    frame: pd.DataFrame,
    *,
    requested_models: tuple[str, ...],
    include_city_comparison: bool,
) -> None:
    """Validate keys, target source, filters and every requested feature schema."""

    required = {"user_id", "has_telco", "household_type", TARGET_SOURCE}
    for name in requested_models:
        required.update(feature_sets(include_city=True)[name])
        if include_city_comparison:
            required.update(feature_sets(include_city=False)[name])
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Prepared dataset is missing required columns: {missing}")
    if frame["user_id"].isna().any():
        raise ValueError("Prepared dataset contains missing user_id values.")
    if frame["user_id"].duplicated().any():
        raise ValueError("Prepared dataset must contain one row per unique user_id.")


def prepare_population(
    frame: pd.DataFrame,
    *,
    individual_customers_only: bool = True,
) -> pd.DataFrame:
    """Create the notebook-compatible high Telco monetary research population."""

    mask = frame["has_telco"].eq(1) & frame[TARGET_SOURCE].notna()
    population = frame.loc[mask].copy()
    if individual_customers_only:
        population = population.loc[
            ~population["household_type"].isin(("Công ty", "Cơ quan nhà nước"))
        ].copy()
    population[TARGET_COLUMN] = population[TARGET_SOURCE].eq(4).astype("int8")
    if population.empty:
        raise ValueError("No rows remain after applying the Telco population filters.")
    counts = population[TARGET_COLUMN].value_counts()
    if set(counts.index) != {0, 1}:
        raise ValueError("Target must contain both classes after population filtering.")
    return population


def summarize_population(population: pd.DataFrame) -> dict[str, Any]:
    """Return aggregate-only diagnostics safe for reports."""

    target = population[TARGET_COLUMN]
    return {
        "n_rows": len(population),
        "n_features_available": int(population.shape[1] - 2),
        "n_positive": int(target.sum()),
        "n_negative": int((1 - target).sum()),
        "positive_rate": float(target.mean()),
        "unique_users": int(population["user_id"].nunique()),
    }
