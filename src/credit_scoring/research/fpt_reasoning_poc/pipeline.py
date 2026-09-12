from __future__ import annotations

from .build_profiles import build
from .common import OUTPUT_DIR, PROCESSED_DIR
from .create_test_cases import create
from .rule_engine import run as run_rules
from .validate_data import run as validate_source


def main() -> None:
    frame, report = validate_source()
    if not report["valid_for_profile_build"]:
        raise SystemExit(
            "Dữ liệu nguồn không hợp lệ; xem "
            "data/processed/research/fpt_reasoning_poc/validation_report.json"
        )
    profiles = build(frame)
    rule_results = run_rules(PROCESSED_DIR / "profiles.jsonl", OUTPUT_DIR / "rule_results.jsonl")
    cases = create(PROCESSED_DIR / "profiles.jsonl")
    print(f"Hoàn tất: {len(profiles)} profiles, {len(rule_results)} rule results, {len(cases)} test cases")
    print(f"Cảnh báo dữ liệu: {len(report['warnings'])}")


if __name__ == "__main__":
    main()
