"""Application-level features for Home Credit E01 and E02 experiments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from credit_scoring.numeric import safe_divide

DAYS_EMPLOYED_SENTINEL = 365_243

CONTACT_FLAG_COLUMNS: tuple[str, ...] = (
    "FLAG_MOBIL",
    "FLAG_EMP_PHONE",
    "FLAG_WORK_PHONE",
    "FLAG_CONT_MOBILE",
    "FLAG_PHONE",
    "FLAG_EMAIL",
)

EXT_SOURCE_COLUMNS: tuple[str, ...] = (
    "EXT_SOURCE_1",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
)

# These bases have matching numeric AVG/MODE/MEDI fields in the public data
# dictionary. Categorical MODE-only fields are deliberately excluded.
HOUSING_NUMERIC_BASES: tuple[str, ...] = (
    "APARTMENTS",
    "BASEMENTAREA",
    "YEARS_BEGINEXPLUATATION",
    "YEARS_BUILD",
    "COMMONAREA",
    "ELEVATORS",
    "ENTRANCES",
    "FLOORSMAX",
    "FLOORSMIN",
    "LANDAREA",
    "LIVINGAPARTMENTS",
    "LIVINGAREA",
    "NONLIVINGAPARTMENTS",
    "NONLIVINGAREA",
)

E02_FEATURE_FAMILIES: tuple[str, ...] = (
    "ratios",
    "age_employment",
    "external_sources",
    "application_contact",
    "housing",
)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], family: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{family} requires missing columns: {missing}")


def _float32_series(values: pd.Series) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").astype("float32")
    return result.replace([np.inf, -np.inf], np.nan)


def _legacy_safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Preserve the E01 notebook formula and dtype for locked-baseline replay."""

    result = numerator.divide(denominator.replace(0, np.nan))
    return result.replace([np.inf, -np.inf], np.nan)


def _clean_days_employed(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(result, ["DAYS_EMPLOYED"], "employment cleaning")
    anomaly = result["DAYS_EMPLOYED"].eq(DAYS_EMPLOYED_SENTINEL)
    result["DAYS_EMPLOYED_ANOMALOUS"] = anomaly.astype("int8")
    result.loc[anomaly, "DAYS_EMPLOYED"] = np.nan
    return result.replace([np.inf, -np.inf], np.nan)


def _add_e01_ratio_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    formulas = {
        "CREDIT_INCOME_RATIO": ("AMT_CREDIT", "AMT_INCOME_TOTAL"),
        "ANNUITY_INCOME_RATIO": ("AMT_ANNUITY", "AMT_INCOME_TOTAL"),
        "ANNUITY_CREDIT_RATIO": ("AMT_ANNUITY", "AMT_CREDIT"),
        "GOODS_CREDIT_RATIO": ("AMT_GOODS_PRICE", "AMT_CREDIT"),
        "EMPLOYED_BIRTH_RATIO": ("DAYS_EMPLOYED", "DAYS_BIRTH"),
        "INCOME_PER_PERSON": ("AMT_INCOME_TOTAL", "CNT_FAM_MEMBERS"),
        "CHILDREN_RATIO": ("CNT_CHILDREN", "CNT_FAM_MEMBERS"),
    }
    required = {column for pair in formulas.values() for column in pair}
    required.update({"OWN_CAR_AGE"})
    _require_columns(result, required, "E01 ratios")
    for name, (numerator, denominator) in formulas.items():
        result[name] = _legacy_safe_divide(result[numerator], result[denominator])
    result["CAR_BIRTH_RATIO"] = _legacy_safe_divide(
        result["OWN_CAR_AGE"],
        result["DAYS_BIRTH"].abs(),
    )
    return result


def _add_e01_external_source_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(result, EXT_SOURCE_COLUMNS, "E01 external sources")
    values = result[list(EXT_SOURCE_COLUMNS)]
    result["EXT_SOURCE_MEAN"] = values.mean(axis=1)
    result["EXT_SOURCE_MEDIAN"] = values.median(axis=1)
    result["EXT_SOURCE_MIN"] = values.min(axis=1)
    result["EXT_SOURCE_MAX"] = values.max(axis=1)
    result["EXT_SOURCE_STD"] = values.std(axis=1)
    result["EXT_SOURCE_MISSING_COUNT"] = values.isna().sum(axis=1)
    result["EXT_SOURCE_PRODUCT"] = values.prod(axis=1, min_count=2)
    result["EXT_SOURCE_RANGE"] = result["EXT_SOURCE_MAX"] - result["EXT_SOURCE_MIN"]
    for left_index, left in enumerate(EXT_SOURCE_COLUMNS):
        for right in EXT_SOURCE_COLUMNS[left_index + 1 :]:
            result[f"{left}_MINUS_{right}"] = result[left] - result[right]
            result[f"{left}_DIV_{right}"] = _legacy_safe_divide(result[left], result[right])
            result[f"{right}_DIV_{left}"] = _legacy_safe_divide(result[right], result[left])
    return result


def _add_e01_summary_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    document_columns = [column for column in result if column.startswith("FLAG_DOCUMENT_")]
    contact_columns = [column for column in CONTACT_FLAG_COLUMNS if column in result]
    if not document_columns:
        raise ValueError("E01 summaries require at least one FLAG_DOCUMENT_* column.")
    if not contact_columns:
        raise ValueError("E01 summaries require at least one known contact flag column.")
    result["DOCUMENT_FLAG_COUNT"] = result[document_columns].sum(axis=1)
    result["CONTACT_FLAG_COUNT"] = result[contact_columns].fillna(0).sum(axis=1)
    selected_housing = [
        "APARTMENTS_AVG",
        "BASEMENTAREA_AVG",
        "YEARS_BEGINEXPLUATATION_AVG",
        "ELEVATORS_AVG",
        "WALLSMATERIAL_MODE",
    ]
    numeric_housing = [
        column
        for column in selected_housing
        if column in result.columns and pd.api.types.is_numeric_dtype(result[column])
    ]
    if numeric_housing:
        result["HOUSING_AVG_MEAN"] = result[numeric_housing].mean(axis=1)
    return result


def build_e01_application_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the locked E01 notebook cleaning and feature order."""

    result = _clean_days_employed(frame)
    result = _add_e01_ratio_features(result)
    result = _add_e01_external_source_features(result)
    return _add_e01_summary_features(result)


def _add_e02_ratio_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(
        result,
        [
            "AMT_CREDIT",
            "AMT_INCOME_TOTAL",
            "AMT_ANNUITY",
            "AMT_GOODS_PRICE",
            "CNT_FAM_MEMBERS",
        ],
        "E02 ratios",
    )
    result["CREDIT_INCOME_RATIO"] = safe_divide(
        result["AMT_CREDIT"], result["AMT_INCOME_TOTAL"]
    )
    result["ANNUITY_INCOME_RATIO"] = safe_divide(
        result["AMT_ANNUITY"], result["AMT_INCOME_TOTAL"]
    )
    result["CREDIT_ANNUITY_RATIO"] = safe_divide(
        result["AMT_CREDIT"], result["AMT_ANNUITY"]
    )
    result["GOODS_CREDIT_RATIO"] = safe_divide(
        result["AMT_GOODS_PRICE"], result["AMT_CREDIT"]
    )
    result["CREDIT_GOODS_DIFF"] = _float32_series(
        result["AMT_CREDIT"] - result["AMT_GOODS_PRICE"]
    )
    result["INCOME_PER_PERSON"] = safe_divide(
        result["AMT_INCOME_TOTAL"], result["CNT_FAM_MEMBERS"]
    )
    return result


def _add_e02_age_employment_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(result, ["DAYS_BIRTH", "DAYS_EMPLOYED"], "E02 age/employment")
    result.loc[result["DAYS_EMPLOYED"].eq(DAYS_EMPLOYED_SENTINEL), "DAYS_EMPLOYED"] = np.nan
    result["AGE_YEARS"] = _float32_series(-result["DAYS_BIRTH"] / 365.25)
    result["EMPLOYED_YEARS"] = _float32_series(-result["DAYS_EMPLOYED"] / 365.25)
    result["EMPLOYED_AGE_RATIO"] = safe_divide(
        result["DAYS_EMPLOYED"], result["DAYS_BIRTH"]
    )
    return result


def _add_e02_external_source_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(result, EXT_SOURCE_COLUMNS, "E02 external sources")
    values = result[list(EXT_SOURCE_COLUMNS)].astype("float32")
    result["EXT_SOURCE_MEAN"] = _float32_series(values.mean(axis=1))
    result["EXT_SOURCE_MIN"] = _float32_series(values.min(axis=1))
    result["EXT_SOURCE_MAX"] = _float32_series(values.max(axis=1))
    # ddof=1 preserves the exact E01 definition for overlapping columns.
    result["EXT_SOURCE_STD"] = _float32_series(values.std(axis=1, ddof=1))
    result["EXT_SOURCE_COUNT"] = values.notna().sum(axis=1).astype("int8")
    return result


def _add_e02_application_contact_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _require_columns(
        result,
        ["DAYS_LAST_PHONE_CHANGE", "CNT_CHILDREN", "CNT_FAM_MEMBERS"],
        "E02 application/contact summaries",
    )
    document_columns = [column for column in result if column.startswith("FLAG_DOCUMENT_")]
    contact_columns = [column for column in CONTACT_FLAG_COLUMNS if column in result]
    if not document_columns:
        raise ValueError("E02 summaries require at least one FLAG_DOCUMENT_* column.")
    if not contact_columns:
        raise ValueError("E02 summaries require at least one known contact flag column.")
    result["DOCUMENT_COUNT"] = result[document_columns].sum(axis=1, min_count=1).astype("float32")
    result["CONTACT_COUNT"] = result[contact_columns].sum(axis=1, min_count=1).astype("float32")
    result["PHONE_CHANGE_YEARS"] = _float32_series(-result["DAYS_LAST_PHONE_CHANGE"] / 365.25)
    result["CHILDREN_RATIO"] = safe_divide(
        result["CNT_CHILDREN"], result["CNT_FAM_MEMBERS"]
    )
    return result


def _matched_housing_columns(frame: pd.DataFrame, suffix: str) -> list[str]:
    matched_bases = [
        base
        for base in HOUSING_NUMERIC_BASES
        if all(f"{base}_{candidate}" in frame.columns for candidate in ("AVG", "MODE", "MEDI"))
    ]
    return [f"{base}_{suffix}" for base in matched_bases]


def _add_e02_housing_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for suffix in ("AVG", "MODE", "MEDI"):
        columns = _matched_housing_columns(result, suffix)
        if not columns:
            continue
        values = result[columns].apply(pd.to_numeric, errors="coerce").astype("float32")
        result[f"HOUSING_NUMERIC_{suffix}_MEAN"] = _float32_series(values.mean(axis=1))
        result[f"HOUSING_NUMERIC_{suffix}_MIN"] = _float32_series(values.min(axis=1))
        result[f"HOUSING_NUMERIC_{suffix}_MAX"] = _float32_series(values.max(axis=1))
    return result


E02_FAMILY_BUILDERS = {
    "ratios": _add_e02_ratio_features,
    "age_employment": _add_e02_age_employment_features,
    "external_sources": _add_e02_external_source_features,
    "application_contact": _add_e02_application_contact_features,
    "housing": _add_e02_housing_features,
}


def _normalise_families(families: Sequence[str] | None) -> tuple[str, ...]:
    requested = set(E02_FEATURE_FAMILIES if families is None else families)
    unknown = sorted(requested.difference(E02_FEATURE_FAMILIES))
    if unknown:
        raise ValueError(f"Unknown E02 feature families: {unknown}")
    return tuple(family for family in E02_FEATURE_FAMILIES if family in requested)


def build_e02_application_features(
    frame: pd.DataFrame,
    *,
    families: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Build E01 plus selected E02 application-level feature families."""

    result = build_e01_application_features(frame)
    for family in _normalise_families(families):
        result = E02_FAMILY_BUILDERS[family](result)
    numeric = result.select_dtypes(include="number")
    if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Application features contain infinite numeric values.")
    return result


def build_aligned_application_features(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    *,
    feature_set: str = "e02",
    families: Sequence[str] | None = None,
    target_column: str = "TARGET",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate deterministic train/test application features with one schema."""

    train_columns = [column for column in train_frame.columns if column != target_column]
    test_columns = list(test_frame.columns)
    if set(train_columns) != set(test_columns):
        train_only = sorted(set(train_columns).difference(test_columns))
        test_only = sorted(set(test_columns).difference(train_columns))
        raise ValueError(
            "Train/test application schemas differ: "
            f"train_only={train_only}, test_only={test_only}"
        )
    train_predictors = train_frame[train_columns].copy()
    test_predictors = test_frame[train_columns].copy()
    if feature_set == "e01":
        train_features = build_e01_application_features(train_predictors)
        test_features = build_e01_application_features(test_predictors)
    elif feature_set == "e02":
        train_features = build_e02_application_features(train_predictors, families=families)
        test_features = build_e02_application_features(test_predictors, families=families)
    else:
        raise ValueError(f"Unknown application feature set: {feature_set}")
    if list(train_features.columns) != list(test_features.columns):
        raise ValueError("Generated train/test feature columns differ in name or order.")
    return train_features, test_features
