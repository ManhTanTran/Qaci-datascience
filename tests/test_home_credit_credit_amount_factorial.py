from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from credit_scoring.experiments.home_credit_credit_amount_factorial import (
    nrd_reproduces_current_e02_a,
    prepare_credit_amount_factorial_data,
    resolve_credit_amount_factorial_experiments,
    select_e02_final,
)
from credit_scoring.features.home_credit_credit_amount_factorial import (
    CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS,
    NORMALIZED_RATIO_COLUMNS,
    build_credit_amount_factorial_features,
    describe_credit_amount_factors,
    summarize_feature_matrix_differences,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2, 3, 4],
            "TARGET": [0, 1, 0, 1],
            "AMT_CREDIT": [100.0, 120.0, 90.0, np.nan],
            "AMT_INCOME_TOTAL": [50.0, 0.0, np.nan, 30.0],
            "AMT_ANNUITY": [10.0, 0.0, np.nan, 5.0],
            "AMT_GOODS_PRICE": [80.0, np.nan, 100.0, 20.0],
            "CNT_FAM_MEMBERS": [2.0, 0.0, np.nan, 1.0],
            "CNT_CHILDREN": [1.0, 0.0, 2.0, 0.0],
            "OWN_CAR_AGE": [5.0, np.nan, 1.0, 2.0],
            "DAYS_BIRTH": [-3652.5, -7305.0, -365.25, -10957.5],
            "DAYS_EMPLOYED": [-730.5, 365243.0, np.nan, -365.25],
            "DAYS_LAST_PHONE_CHANGE": [-365.25, 0.0, np.nan, -10.0],
            "EXT_SOURCE_1": [0.2, np.nan, np.nan, 0.1],
            "EXT_SOURCE_2": [0.4, np.nan, 0.6, 0.2],
            "EXT_SOURCE_3": [np.nan, np.nan, 0.3, 0.3],
            "FLAG_DOCUMENT_2": [1.0, np.nan, 0.0, 1.0],
            "FLAG_MOBIL": [1.0, np.nan, 1.0, 1.0],
            "FLAG_PHONE": [0.0, np.nan, 1.0, 0.0],
            "APARTMENTS_AVG": [0.2, 0.4, np.nan, 0.5],
            "WALLSMATERIAL_MODE": ["Stone", "Panel", None, "Block"],
        }
    )


@pytest.mark.parametrize(
    ("experiment", "expected_added", "expected_overwritten"),
    [
        ("E01_LOCKED", (), ()),
        ("E02-N", (), NORMALIZED_RATIO_COLUMNS),
        ("E02-R", ("CREDIT_ANNUITY_RATIO",), ()),
        ("E02-D", ("CREDIT_GOODS_DIFF",), ()),
        ("E02-RD", ("CREDIT_ANNUITY_RATIO", "CREDIT_GOODS_DIFF"), ()),
        ("E02-NR", ("CREDIT_ANNUITY_RATIO",), NORMALIZED_RATIO_COLUMNS),
        ("E02-ND", ("CREDIT_GOODS_DIFF",), NORMALIZED_RATIO_COLUMNS),
        (
            "E02-NRD",
            ("CREDIT_ANNUITY_RATIO", "CREDIT_GOODS_DIFF"),
            NORMALIZED_RATIO_COLUMNS,
        ),
    ],
)
def test_all_factor_combinations_are_explicit_and_ordered(
    experiment: str,
    expected_added: tuple[str, ...],
    expected_overwritten: tuple[str, ...],
) -> None:
    predictors = _frame().drop(columns="TARGET")
    e01 = build_credit_amount_factorial_features(predictors, factors=())
    factors = CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS[experiment]
    candidate = build_credit_amount_factorial_features(predictors, factors=factors)
    spec = describe_credit_amount_factors(factors)

    assert spec.added_columns == expected_added
    assert spec.overwritten_columns == expected_overwritten
    assert list(candidate.columns[: len(e01.columns)]) == list(e01.columns)
    assert tuple(candidate.columns[len(e01.columns) :]) == expected_added
    if "N" not in factors:
        pd.testing.assert_frame_equal(candidate[e01.columns], e01, check_exact=True)
    else:
        assert all(candidate[column].dtype == "float32" for column in NORMALIZED_RATIO_COLUMNS)


def test_factor_formulas_missing_values_and_no_infinity() -> None:
    result = build_credit_amount_factorial_features(
        _frame().drop(columns="TARGET"),
        factors=("N", "R", "D"),
    )
    assert result.loc[0, "CREDIT_INCOME_RATIO"] == pytest.approx(2.0)
    assert result.loc[0, "ANNUITY_INCOME_RATIO"] == pytest.approx(0.2)
    assert result.loc[0, "GOODS_CREDIT_RATIO"] == pytest.approx(0.8)
    assert result.loc[0, "INCOME_PER_PERSON"] == pytest.approx(25.0)
    assert result.loc[0, "CREDIT_ANNUITY_RATIO"] == pytest.approx(10.0)
    assert result.loc[0, "CREDIT_GOODS_DIFF"] == pytest.approx(20.0)
    assert pd.isna(result.loc[1, "CREDIT_INCOME_RATIO"])
    assert pd.isna(result.loc[1, "CREDIT_ANNUITY_RATIO"])
    assert pd.isna(result.loc[2, "INCOME_PER_PERSON"])
    assert not np.isinf(
        result.select_dtypes(include="number").to_numpy(dtype=float, na_value=np.nan)
    ).any()


def test_nrd_exactly_reproduces_current_e02_a() -> None:
    assert nrd_reproduces_current_e02_a(_frame().drop(columns="TARGET"))


def test_difference_report_and_silent_overwrite_guard() -> None:
    predictors = _frame().drop(columns="TARGET")
    e01 = build_credit_amount_factorial_features(predictors, factors=())
    nrd = build_credit_amount_factorial_features(predictors, factors=("N", "R", "D"))
    report = summarize_feature_matrix_differences(
        e01,
        nrd,
        explicitly_overwritten=NORMALIZED_RATIO_COLUMNS,
    )
    assert report.loc[report["change_type"].eq("overwritten"), "feature"].tolist() == list(
        NORMALIZED_RATIO_COLUMNS
    )
    assert report.loc[report["change_type"].eq("added"), "feature"].tolist() == [
        "CREDIT_ANNUITY_RATIO",
        "CREDIT_GOODS_DIFF",
    ]

    silently_changed = e01.copy()
    silently_changed["AMT_CREDIT"] = silently_changed["AMT_CREDIT"] + 1
    with pytest.raises(ValueError, match="silently changed"):
        summarize_feature_matrix_differences(e01, silently_changed)


def test_factorial_train_test_schema_and_category_alignment() -> None:
    train = _frame()
    test = train.drop(columns="TARGET").iloc[:2].copy()
    test = test[list(reversed(test.columns))]
    prepared = prepare_credit_amount_factorial_data(train, test, factors=("N", "R", "D"))

    assert list(prepared.train_features.columns) == list(prepared.test_features.columns)
    assert str(prepared.train_features["WALLSMATERIAL_MODE"].dtype) == "category"
    assert list(prepared.train_features["WALLSMATERIAL_MODE"].cat.categories) == list(
        prepared.test_features["WALLSMATERIAL_MODE"].cat.categories
    )


def test_manifest_and_final_selection_rules() -> None:
    assert list(resolve_credit_amount_factorial_experiments()) == list(
        CREDIT_AMOUNT_FACTORIAL_EXPERIMENTS
    )
    with pytest.raises(ValueError, match="requires E01_LOCKED"):
        resolve_credit_amount_factorial_experiments(["E02-R"])

    summary = pd.DataFrame(
        [
            {
                "experiment": "E01_LOCKED",
                "oof_auc": 0.7000,
                "std_fold_auc": 0.0100,
                "positive_fold_count_vs_e01": 0,
                "n_features": 10,
                "n_overwritten_features": 0,
            },
            {
                "experiment": "E02-NR",
                "oof_auc": 0.710005,
                "std_fold_auc": 0.0101,
                "positive_fold_count_vs_e01": 5,
                "n_features": 11,
                "n_overwritten_features": 4,
            },
            {
                "experiment": "E02-RD",
                "oof_auc": 0.710000,
                "std_fold_auc": 0.0101,
                "positive_fold_count_vs_e01": 4,
                "n_features": 12,
                "n_overwritten_features": 0,
            },
        ]
    )
    selected = select_e02_final(summary, n_splits=5)
    assert selected is not None
    assert selected.name == "E02-FINAL"
    assert selected.source_experiment == "E02-NR"
    assert selected.factors == ("N", "R")
