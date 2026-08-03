from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from credit_scoring.experiments.home_credit_application import (
    prepare_application_data,
    resolve_e02_ablation_experiments,
)
from credit_scoring.features.home_credit_application import (
    build_aligned_application_features,
    build_e02_application_features,
    safe_divide,
)


def _application_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2, 3],
            "TARGET": [0, 1, 0],
            "AMT_CREDIT": [100.0, 100.0, 90.0],
            "AMT_INCOME_TOTAL": [50.0, 0.0, np.nan],
            "AMT_ANNUITY": [10.0, 0.0, np.nan],
            "AMT_GOODS_PRICE": [80.0, np.nan, 100.0],
            "CNT_FAM_MEMBERS": [2.0, 0.0, np.nan],
            "CNT_CHILDREN": [1.0, 0.0, 2.0],
            "OWN_CAR_AGE": [5.0, np.nan, 1.0],
            "DAYS_BIRTH": [-3652.5, -7305.0, -365.25],
            "DAYS_EMPLOYED": [-730.5, 365243.0, np.nan],
            "DAYS_LAST_PHONE_CHANGE": [-365.25, 0.0, np.nan],
            "EXT_SOURCE_1": [0.2, np.nan, np.nan],
            "EXT_SOURCE_2": [0.4, np.nan, 0.6],
            "EXT_SOURCE_3": [np.nan, np.nan, 0.3],
            "FLAG_DOCUMENT_2": [1.0, np.nan, 0.0],
            "FLAG_DOCUMENT_3": [0.0, np.nan, 1.0],
            "FLAG_MOBIL": [1.0, np.nan, 1.0],
            "FLAG_PHONE": [0.0, np.nan, 1.0],
            "APARTMENTS_AVG": [0.2, 0.4, np.nan],
            "APARTMENTS_MODE": [0.1, 0.5, np.nan],
            "APARTMENTS_MEDI": [0.3, 0.6, np.nan],
            "BASEMENTAREA_AVG": [0.8, 0.2, np.nan],
            "BASEMENTAREA_MODE": [0.7, 0.3, np.nan],
            "BASEMENTAREA_MEDI": [0.9, 0.4, np.nan],
            "WALLSMATERIAL_MODE": ["Stone", "Panel", None],
        }
    )


def test_e02_formulas_and_missing_information() -> None:
    featured = build_e02_application_features(_application_frame().drop(columns="TARGET"))
    row = featured.iloc[0]

    assert row["CREDIT_INCOME_RATIO"] == pytest.approx(2.0)
    assert row["ANNUITY_INCOME_RATIO"] == pytest.approx(0.2)
    assert row["CREDIT_ANNUITY_RATIO"] == pytest.approx(10.0)
    assert row["GOODS_CREDIT_RATIO"] == pytest.approx(0.8)
    assert row["CREDIT_GOODS_DIFF"] == pytest.approx(20.0)
    assert row["INCOME_PER_PERSON"] == pytest.approx(25.0)
    assert row["AGE_YEARS"] == pytest.approx(10.0)
    assert row["EMPLOYED_YEARS"] == pytest.approx(2.0)
    assert row["EMPLOYED_AGE_RATIO"] == pytest.approx(0.2)
    assert row["EXT_SOURCE_MEAN"] == pytest.approx(0.3)
    assert row["EXT_SOURCE_MIN"] == pytest.approx(0.2)
    assert row["EXT_SOURCE_MAX"] == pytest.approx(0.4)
    assert row["EXT_SOURCE_STD"] == pytest.approx(np.sqrt(0.02))
    assert row["EXT_SOURCE_COUNT"] == 2
    assert row["DOCUMENT_COUNT"] == 1
    assert row["CONTACT_COUNT"] == 1
    assert row["PHONE_CHANGE_YEARS"] == pytest.approx(1.0)
    assert row["CHILDREN_RATIO"] == pytest.approx(0.5)

    all_missing_ext = featured.iloc[1]
    assert all_missing_ext["EXT_SOURCE_COUNT"] == 0
    assert pd.isna(all_missing_ext["EXT_SOURCE_MEAN"])
    assert pd.isna(all_missing_ext["DOCUMENT_COUNT"])
    assert pd.isna(all_missing_ext["CONTACT_COUNT"])


def test_safe_division_zero_missing_and_infinity_policy() -> None:
    result = safe_divide(
        pd.Series([1.0, 1.0, np.inf, 4.0]),
        pd.Series([0.0, np.nan, 2.0, 2.0]),
    )
    assert result.dtype == "float32"
    assert result.iloc[:3].isna().all()
    assert result.iloc[3] == pytest.approx(2.0)
    assert not np.isinf(result.to_numpy()).any()

    featured = build_e02_application_features(_application_frame().drop(columns="TARGET"))
    assert pd.isna(featured.loc[1, "CREDIT_INCOME_RATIO"])
    assert pd.isna(featured.loc[1, "CREDIT_ANNUITY_RATIO"])
    assert pd.isna(featured.loc[2, "INCOME_PER_PERSON"])
    assert not np.isinf(
        featured.select_dtypes(include="number").to_numpy(dtype=float, na_value=np.nan)
    ).any()


def test_days_employed_sentinel_is_missing_before_derivation() -> None:
    featured = build_e02_application_features(_application_frame().drop(columns="TARGET"))
    assert featured.loc[1, "DAYS_EMPLOYED_ANOMALOUS"] == 1
    assert pd.isna(featured.loc[1, "DAYS_EMPLOYED"])
    assert pd.isna(featured.loc[1, "EMPLOYED_YEARS"])
    assert pd.isna(featured.loc[1, "EMPLOYED_AGE_RATIO"])


def test_housing_summaries_use_only_unambiguous_matched_groups() -> None:
    featured = build_e02_application_features(_application_frame().drop(columns="TARGET"))
    assert featured.loc[0, "HOUSING_NUMERIC_AVG_MEAN"] == pytest.approx(0.5)
    assert featured.loc[0, "HOUSING_NUMERIC_MODE_MIN"] == pytest.approx(0.1)
    assert featured.loc[0, "HOUSING_NUMERIC_MEDI_MAX"] == pytest.approx(0.9)
    assert "HOUSING_NUMERIC_WALLSMATERIAL_MEAN" not in featured.columns


def test_train_test_generation_has_identical_order_and_category_encoding() -> None:
    train = _application_frame()
    test = train.drop(columns="TARGET").iloc[:2].copy()
    test = test[list(reversed(test.columns))]
    train_features, test_features = build_aligned_application_features(train, test)

    assert list(train_features.columns) == list(test_features.columns)
    assert "TARGET" not in train_features
    prepared = prepare_application_data(train, test, feature_set="e02")
    assert list(prepared.train_features.columns) == list(prepared.test_features.columns)
    assert str(prepared.train_features["WALLSMATERIAL_MODE"].dtype) == "category"
    assert list(prepared.train_features["WALLSMATERIAL_MODE"].cat.categories) == list(
        prepared.test_features["WALLSMATERIAL_MODE"].cat.categories
    )


def test_schema_mismatch_and_unknown_family_are_rejected() -> None:
    train = _application_frame()
    test = train.drop(columns=["TARGET", "AMT_CREDIT"])
    with pytest.raises(ValueError, match="schemas differ"):
        build_aligned_application_features(train, test)
    with pytest.raises(ValueError, match="Unknown E02 feature families"):
        build_e02_application_features(train.drop(columns="TARGET"), families=["unknown"])


def test_e02_ablation_manifest_is_ordered_and_requires_locked_baseline() -> None:
    experiments = resolve_e02_ablation_experiments()

    assert list(experiments) == [
        "E01_locked",
        "E02-A_credit_amount",
        "E02-B_age_employment",
        "E02-C_external_sources",
        "E02-D_application_contact",
        "E02-E_housing",
        "E02-ALL",
    ]
    assert experiments["E01_locked"] == ()
    assert experiments["E02-E_housing"] == ("housing",)

    with pytest.raises(ValueError, match="requires E01_locked"):
        resolve_e02_ablation_experiments(["E02-E_housing"])
    with pytest.raises(ValueError, match="Unknown E02 ablation"):
        resolve_e02_ablation_experiments(["E01_locked", "E02-Z_unknown"])
