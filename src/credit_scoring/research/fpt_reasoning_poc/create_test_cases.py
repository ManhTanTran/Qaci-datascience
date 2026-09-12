from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .common import PROCESSED_DIR, TEST_DIR, read_jsonl, write_jsonl
from .rule_engine import evaluate_profile, load_rules


def with_age(profile: dict[str, Any], exact: int | None = None, group: str | None = None, minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    result = deepcopy(profile)
    result["age"] = {
        "exact": exact,
        "group": group,
        "min": exact if exact is not None else minimum,
        "max": exact if exact is not None else maximum,
        "source_type": "synthetic_test",
    }
    return result


def with_payment(profile: dict[str, Any], observed: int | None, late: int | None, max_late_days: int | None) -> dict[str, Any]:
    result = deepcopy(profile)
    result["payment_history_12m"].update({
        "observed_months": observed,
        "late_months": late,
        "max_late_days": max_late_days,
        "field_status": {
            "observed_months": "available" if observed is not None else "missing",
            "late_months": "available" if late is not None else "missing",
            "max_late_days": "available" if max_late_days is not None else "missing",
        },
    })
    return result


def create(profiles_path: Path = PROCESSED_DIR / "profiles.jsonl") -> list[dict[str, Any]]:
    profiles = read_jsonl(profiles_path)
    if not profiles:
        raise ValueError("Không có profile để tạo test case")
    base = profiles[1] if len(profiles) > 1 else profiles[0]
    rules = load_rules()

    definitions = [
        ("A_OVER23_GOOD", with_payment(with_age(base, exact=30), 12, 0, 0), False, []),
        ("B_UNDER23_GOOD", with_payment(with_age(base, exact=21), 12, 0, 0), True, []),
        ("C_OVER23_BAD", with_payment(with_age(base, exact=30), 12, 5, 45), False, []),
        ("D_UNDER23_BAD", with_payment(with_age(base, exact=21), 12, 5, 45), False, []),
        ("E_AGE_BOUNDARY_UNKNOWN", with_payment(with_age(base, group="23-30", minimum=23, maximum=30), 12, 0, 0), False, []),
        ("F_OVER23_PAYMENT_MISSING", with_payment(with_age(base, exact=30), None, None, None), False, ["payment_history_12m"]),
        ("G_LOCAL_INCOME_PROXY_ONLY", with_payment(with_age(base, exact=30), None, None, None), False, ["individual_income", "payment_history_12m"]),
        ("H_UNDER23_GOOD_INSTALLMENT", with_payment(with_age(base, exact=21), 12, 0, 0), True, []),
    ]

    cases: list[dict[str, Any]] = []
    for case_id, profile, conflict_expected, missing in definitions:
        profile = deepcopy(profile)
        profile["user_id"] = case_id
        if case_id == "H_UNDER23_GOOD_INSTALLMENT":
            profile["shopping_installment"].update({
                "installment_history": {"contracts_24m": 1, "late_contracts_24m": 0, "status": "completed"},
                "status": "available",
                "missing_fields": [],
            })
        rule_result = evaluate_profile(profile, rules)
        cases.append({
            "case_id": case_id,
            "profile": profile,
            "expected_rule_result": rule_result["decision"],
            "expected_recommendation": rule_result["recommendation"],
            "expected_conflict": conflict_expected,
            "expected_missing_fields": missing,
            "forbidden_claims": [
                "thu nhập cá nhân bằng thu nhập bình quân địa phương",
                "có dữ liệu giáo dục FPT" if profile["fpt_education"]["status"] == "missing" else "",
            ],
        })
    for case in cases:
        case["forbidden_claims"] = [text for text in case["forbidden_claims"] if text]
    write_jsonl(TEST_DIR / "test_cases.jsonl", cases)
    return cases


def main() -> None:
    cases = create()
    print(f"Đã tạo {len(cases)} test case tại {TEST_DIR / 'test_cases.jsonl'}")


if __name__ == "__main__":
    main()

