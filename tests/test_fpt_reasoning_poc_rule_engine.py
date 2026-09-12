from __future__ import annotations

import unittest

from credit_scoring.research.fpt_reasoning_poc.rule_engine import (
    FAIL,
    PASS,
    UNKNOWN,
    compare_age,
    evaluate_profile,
    load_rules,
)


class AgeRuleTests(unittest.TestCase):
    def test_exact_age_above_threshold_passes(self) -> None:
        self.assertEqual(compare_age({"exact": 24, "min": 24, "max": 24}, 23), PASS)

    def test_exact_age_at_threshold_fails(self) -> None:
        self.assertEqual(compare_age({"exact": 23, "min": 23, "max": 23}, 23), FAIL)

    def test_range_entirely_below_or_equal_fails(self) -> None:
        self.assertEqual(compare_age({"exact": None, "min": 18, "max": 23}, 23), FAIL)

    def test_range_crossing_threshold_is_unknown(self) -> None:
        self.assertEqual(compare_age({"exact": None, "min": 23, "max": 30}, 23), UNKNOWN)

    def test_range_entirely_above_passes(self) -> None:
        self.assertEqual(compare_age({"exact": None, "min": 31, "max": 40}, 23), PASS)


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_rules()

    def profile(self, age: dict, observed=12, late=0, max_late=0) -> dict:
        return {
            "user_id": "test",
            "age": age,
            "payment_history_12m": {
                "observed_months": observed,
                "late_months": late,
                "max_late_days": max_late,
            },
        }

    def test_under_23_good_finance_still_fails_hard_rule(self) -> None:
        result = evaluate_profile(self.profile({"exact": 21, "min": 21, "max": 21}), self.rules)
        self.assertEqual(result["decision"], "NOT_ELIGIBLE")

    def test_unknown_age_routes_to_manual_review(self) -> None:
        result = evaluate_profile(self.profile({"exact": None, "min": 23, "max": 30}), self.rules)
        self.assertEqual(result["decision"], "MANUAL_REVIEW")

    def test_over_23_bad_payment_does_not_break_hard_rule_result(self) -> None:
        result = evaluate_profile(self.profile({"exact": 30, "min": 30, "max": 30}, late=5, max_late=45), self.rules)
        self.assertEqual(result["decision"], "ELIGIBLE")
        payment_rule = next(item for item in result["rules"] if item["rule_id"] == "PAYMENT_HISTORY_POSITIVE")
        self.assertEqual(payment_rule["outcome"], FAIL)


if __name__ == "__main__":
    unittest.main()
