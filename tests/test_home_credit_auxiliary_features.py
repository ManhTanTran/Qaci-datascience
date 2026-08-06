"""Synthetic fixtures for the Home Credit auxiliary-table feature modules.

The fixtures are deliberately tiny and hand-checked so the expected values can be
derived by reading them, and every builder is exercised twice on different client
subsets to prove the output schema comes from the code rather than the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from credit_scoring.features.home_credit_bureau import (
    build_bureau_balance_features,
    build_bureau_features,
)
from credit_scoring.features.home_credit_credit_card import build_credit_card_features
from credit_scoring.features.home_credit_installments import build_installments_features
from credit_scoring.features.home_credit_pos_cash import build_pos_cash_features
from credit_scoring.features.home_credit_previous_application import (
    build_previous_application_features,
)

KEY = "SK_ID_CURR"


def make_bureau() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2, 3],
            "SK_ID_BUREAU": [10, 11, 12, 13],
            "CREDIT_ACTIVE": ["Active", "Closed", "Active", "Closed"],
            "CREDIT_TYPE": ["Credit card", "Car loan", "Mortgage", "Consumer credit"],
            "DAYS_CREDIT": [-100, -900, -30, -400],
            "DAYS_CREDIT_ENDDATE": [200.0, -700.0, 100.0, -300.0],
            "CREDIT_DAY_OVERDUE": [0, 12, 0, 0],
            "AMT_CREDIT_SUM": [1000.0, 2000.0, 5000.0, 800.0],
            # Client 3 has no observed debt at all.
            "AMT_CREDIT_SUM_DEBT": [400.0, 100.0, 2500.0, np.nan],
            "AMT_CREDIT_SUM_OVERDUE": [0.0, 50.0, 0.0, np.nan],
            "AMT_CREDIT_SUM_LIMIT": [0.0, 0.0, 1000.0, np.nan],
            "AMT_CREDIT_MAX_OVERDUE": [0.0, 75.0, np.nan, np.nan],
            "AMT_ANNUITY": [np.nan, np.nan, 300.0, np.nan],
            "CNT_CREDIT_PROLONG": [0, 1, 0, 0],
        }
    )


def make_bureau_balance() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_BUREAU": [10] * 5 + [11] * 4,
            "MONTHS_BALANCE": [-1, -2, -3, -4, -5, -1, -2, -3, -4],
            "STATUS": ["0", "1", "1", "0", "X", "C", "2", "3", "X"],
        }
    )


def make_previous_application() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_PREV": [100, 101, 102],
            "NAME_CONTRACT_STATUS": ["Approved", "Refused", "Approved"],
            "NAME_CONTRACT_TYPE": ["Cash loans", "Consumer loans", "Revolving loans"],
            "NAME_YIELD_GROUP": ["high", "middle", "XNA"],
            "AMT_CREDIT": [1000.0, 0.0, 3000.0],
            "AMT_APPLICATION": [1200.0, 2000.0, 3000.0],
            "AMT_ANNUITY": [100.0, np.nan, 250.0],
            "AMT_DOWN_PAYMENT": [100.0, 0.0, np.nan],
            "AMT_GOODS_PRICE": [1200.0, 0.0, 3000.0],
            "RATE_DOWN_PAYMENT": [0.08, 0.0, np.nan],
            "DAYS_DECISION": [-100, -50, -800],
            "CNT_PAYMENT": [12.0, 0.0, 24.0],
        }
    )


def make_pos_cash() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1] * 4 + [2] * 2,
            "SK_ID_PREV": [200] * 4 + [201] * 2,
            "MONTHS_BALANCE": [-4, -3, -2, -1, -2, -1],
            "NAME_CONTRACT_STATUS": [
                "Active", "Active", "Active", "Completed", "Active", "Active",
            ],
            "CNT_INSTALMENT": [12.0, 12.0, 12.0, 12.0, 6.0, 6.0],
            "CNT_INSTALMENT_FUTURE": [4.0, 3.0, 2.0, 0.0, 3.0, 2.0],
            "SK_DPD": [0, 5, 9, 0, 0, 0],
            "SK_DPD_DEF": [0, 0, 3, 0, 0, 0],
        }
    )


def make_credit_card() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1] * 3 + [2],
            "SK_ID_PREV": [300] * 3 + [301],
            "MONTHS_BALANCE": [-3, -2, -1, -1],
            "NAME_CONTRACT_STATUS": ["Active", "Active", "Active", "Completed"],
            "AMT_BALANCE": [500.0, 900.0, 950.0, 0.0],
            "AMT_CREDIT_LIMIT_ACTUAL": [1000.0, 1000.0, 1000.0, 2000.0],
            "AMT_PAYMENT_TOTAL_CURRENT": [200.0, 100.0, 50.0, 0.0],
            "AMT_INST_MIN_REGULARITY": [100.0, 100.0, 100.0, 0.0],
            "AMT_DRAWINGS_CURRENT": [0.0, 400.0, 100.0, 0.0],
            "SK_DPD": [0, 0, 7, 0],
            "SK_DPD_DEF": [0, 0, 7, 0],
        }
    )


def make_installments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1] * 4 + [2] * 2,
            "SK_ID_PREV": [400] * 4 + [401] * 2,
            "NUM_INSTALMENT_NUMBER": [1, 2, 3, 4, 1, 2],
            "DAYS_INSTALMENT": [-400.0, -300.0, -200.0, -30.0, -500.0, -100.0],
            "DAYS_ENTRY_PAYMENT": [-405.0, -290.0, -150.0, -20.0, -500.0, -100.0],
            "AMT_INSTALMENT": [100.0, 100.0, 100.0, 100.0, 50.0, 50.0],
            "AMT_PAYMENT": [100.0, 100.0, 60.0, 100.0, 50.0, 50.0],
        }
    )


BUILDERS = [
    ("bureau", lambda: build_bureau_features(make_bureau(), make_bureau_balance())),
    ("previous_application", lambda: build_previous_application_features(make_previous_application())),
    ("pos_cash", lambda: build_pos_cash_features(make_pos_cash())),
    ("credit_card", lambda: build_credit_card_features(make_credit_card())),
    ("installments", lambda: build_installments_features(make_installments())),
]

SUBSET_BUILDERS = [
    (
        "bureau",
        lambda ids: build_bureau_features(
            make_bureau()[make_bureau()[KEY].isin(ids)],
            make_bureau_balance(),
        ),
    ),
    (
        "previous_application",
        lambda ids: build_previous_application_features(
            make_previous_application()[make_previous_application()[KEY].isin(ids)]
        ),
    ),
    ("pos_cash", lambda ids: build_pos_cash_features(make_pos_cash()[make_pos_cash()[KEY].isin(ids)])),
    (
        "credit_card",
        lambda ids: build_credit_card_features(make_credit_card()[make_credit_card()[KEY].isin(ids)]),
    ),
    (
        "installments",
        lambda ids: build_installments_features(
            make_installments()[make_installments()[KEY].isin(ids)]
        ),
    ),
]


@pytest.mark.parametrize(("name", "builder"), BUILDERS, ids=[n for n, _ in BUILDERS])
def test_output_is_keyed_one_row_per_client(name, builder) -> None:
    frame, _ = builder()

    assert KEY in frame.columns
    assert frame[KEY].is_unique
    assert not frame[KEY].isna().any()


@pytest.mark.parametrize(("name", "builder"), BUILDERS, ids=[n for n, _ in BUILDERS])
def test_every_feature_carries_a_family(name, builder) -> None:
    frame, families = builder()
    unlabelled = sorted(set(frame.columns).difference(families).difference({KEY}))

    assert not unlabelled, f"{name}: features without a family: {unlabelled}"
    assert set(families).issubset(frame.columns)


@pytest.mark.parametrize(("name", "builder"), BUILDERS, ids=[n for n, _ in BUILDERS])
def test_feature_names_are_lightgbm_safe(name, builder) -> None:
    frame, _ = builder()
    unsafe = [column for column in frame.columns if set(column) & set('"\\[]{}:,')]

    assert not unsafe, f"{name}: LightGBM-unsafe feature names: {unsafe}"


@pytest.mark.parametrize(("name", "builder"), SUBSET_BUILDERS, ids=[n for n, _ in SUBSET_BUILDERS])
def test_schema_does_not_depend_on_which_clients_are_present(name, builder) -> None:
    """A block written from a sample must be joinable with one written from all rows."""

    full, full_families = builder([1, 2, 3])
    subset, subset_families = builder([1])

    assert list(full.columns) == list(subset.columns), f"{name}: schema drifted with the data"
    assert full_families == subset_families


def test_bureau_balance_treats_unreported_months_as_unobserved() -> None:
    balance = build_bureau_balance_features(make_bureau_balance()).set_index("SK_ID_BUREAU")

    # Loan 10: statuses 0,1,1,0,X -> four observed months, two of them delinquent.
    assert balance.loc[10, "BB_MONTHS_COUNT"] == 5
    assert balance.loc[10, "BB_OBSERVED_MONTH_SUM"] == 4
    assert balance.loc[10, "BB_DPD_MONTH_SUM"] == 2
    assert balance.loc[10, "BB_DPD_MONTH_SHARE"] == pytest.approx(0.5)
    # Sorted oldest-first the flags are X,0,1,1,0, so the streak is two months.
    assert balance.loc[10, "BB_LONGEST_DPD_STREAK"] == 2
    assert balance.loc[10, "BB_DPD_EPISODES"] == 1


def test_bureau_keeps_missing_debt_distinct_from_zero_debt() -> None:
    frame, _ = build_bureau_features(make_bureau(), make_bureau_balance())
    values = frame.set_index(KEY)

    # Client 3's only loan has no reported debt: every debt statistic stays unknown.
    assert np.isnan(values.loc[3, "BUREAU_AMT_CREDIT_SUM_DEBT_SUM"])
    assert np.isnan(values.loc[3, "BUREAU_AMT_CREDIT_SUM_DEBT_MEAN"])
    # Client 1 has two loans with observed debt.
    assert values.loc[1, "BUREAU_AMT_CREDIT_SUM_DEBT_SUM"] == pytest.approx(500.0)


def test_bureau_counts_are_zero_filled_but_amounts_are_not() -> None:
    frame, _ = build_bureau_features(make_bureau(), make_bureau_balance())
    values = frame.set_index(KEY)

    # Client 3's only loan is Closed, so it has no active loans at all.
    assert values.loc[3, "BUREAU_ACTIVE_LOAN_COUNT"] == 0
    assert np.isnan(values.loc[3, "BUREAU_ACTIVE_DEBT_SUM"])
    assert values.loc[1, "BUREAU_ACTIVE_LOAN_COUNT"] == 1


def test_bureau_credit_type_counts_use_declared_categories() -> None:
    frame, families = build_bureau_features(make_bureau(), make_bureau_balance())
    values = frame.set_index(KEY)

    assert values.loc[1, "BUREAU_CTYPE_Credit card_COUNT"] == 1
    assert values.loc[1, "BUREAU_CTYPE_Car loan_COUNT"] == 1
    # Mortgage is declared, so client 2 lands in its own column rather than OTHER.
    assert values.loc[2, "BUREAU_CTYPE_Mortgage_COUNT"] == 1
    assert families["BUREAU_CTYPE_OTHER_COUNT"] == "counts"


def test_bureau_features_work_without_bureau_balance() -> None:
    frame, _ = build_bureau_features(make_bureau(), None)

    assert frame[KEY].is_unique
    assert frame["BUREAU_BB_STATUS_MEAN_MEAN"].isna().all()


def test_previous_application_recent_refusal_window() -> None:
    frame, _ = build_previous_application_features(make_previous_application())
    values = frame.set_index(KEY)

    # Client 1 was refused 50 days ago; client 2 was never refused.
    assert values.loc[1, "PREV_RECENT_REFUSAL_COUNT"] == 1
    assert values.loc[1, "PREV_HAS_RECENT_REFUSAL"] == 1
    assert values.loc[2, "PREV_RECENT_REFUSAL_COUNT"] == 0
    assert values.loc[2, "PREV_HAS_RECENT_REFUSAL"] == 0


def test_previous_application_trend_is_positive_when_requests_grow_over_time() -> None:
    frame, _ = build_previous_application_features(make_previous_application())
    values = frame.set_index(KEY)

    # Client 1 asked for 1200 at -100 days and 2000 at -50 days: rising over time.
    assert values.loc[1, "PREV_AMT_APPLICATION_TREND"] > 0


def test_installments_dpd_only_counts_late_payments() -> None:
    frame, _ = build_installments_features(make_installments())
    values = frame.set_index(KEY)

    # Client 1: paid 5 days early, 10 late, 50 late, 10 late -> max DPD is 50.
    assert values.loc[1, "INST_DPD_WORST_MAX"] == pytest.approx(50.0)
    assert values.loc[1, "INST_LATE_SUM"] == 3
    # Client 2 always paid exactly on time.
    assert values.loc[2, "INST_DPD_WORST_MAX"] == pytest.approx(0.0)
    assert values.loc[2, "INST_LATE_SUM"] == 0
    assert values.loc[2, "INST_LOANS_WITH_LATE_COUNT"] == 0


def test_installments_underpayment_is_positive_only_when_short() -> None:
    frame, _ = build_installments_features(make_installments())
    values = frame.set_index(KEY)

    # Client 1 paid 60 of a 100 installment once.
    assert values.loc[1, "INST_UNDERPAYMENT_SUM"] == pytest.approx(40.0)
    assert values.loc[2, "INST_UNDERPAYMENT_SUM"] == pytest.approx(0.0)


def test_credit_card_portfolio_utilization_uses_latest_snapshot() -> None:
    frame, _ = build_credit_card_features(make_credit_card())
    values = frame.set_index(KEY)

    # Client 1's card ends at 950 balance against a 1000 limit.
    assert values.loc[1, "CC_PORTFOLIO_UTILIZATION"] == pytest.approx(0.95)
    # Client 2 carries no balance.
    assert values.loc[2, "CC_PORTFOLIO_UTILIZATION"] == pytest.approx(0.0)


def test_pos_cash_delinquency_rolls_up_through_the_contract_level() -> None:
    frame, _ = build_pos_cash_features(make_pos_cash())
    values = frame.set_index(KEY)

    # Client 1's single contract was delinquent in 2 of its 4 months.
    assert values.loc[1, "POS_POS_CONTRACT_COUNT"] == 1
    assert values.loc[1, "POS_POS_DPD_MONTH_SUM"] == 2
    assert values.loc[1, "POS_POS_DPD_RATE_MEAN"] == pytest.approx(0.5)
    assert values.loc[1, "POS_CONTRACTS_WITH_DPD_COUNT"] == 1
    assert values.loc[2, "POS_CONTRACTS_WITH_DPD_COUNT"] == 0
