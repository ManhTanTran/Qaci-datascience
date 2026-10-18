"""Prepare blank Phase E5 human-review CSVs and a read-only sensitivity audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from wardprice.historical_review_e5 import prepare_phase_e5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--title-csv",
        type=Path,
        default=PROJECT_ROOT
        / "outputs"
        / "historical_quality"
        / "tinix-e3-10000-ca3fedcbb089_title_review.csv",
    )
    parser.add_argument(
        "--pilot-db",
        type=Path,
        default=PROJECT_ROOT / "state" / "ward_prices.historical_pilot.sqlite3",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "historical_quality",
    )
    args = parser.parse_args()
    try:
        result = prepare_phase_e5(
            title_review_csv=args.title_csv,
            pilot_db=args.pilot_db,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sensitivity = result["historical_quality"]
    print(
        json.dumps(
            {
                "phase": result["phase"],
                "classification_review_csv": result["classification_review_csv"],
                "classification_review": result["classification_review"],
                "property_review_csv": result["property_review_csv"],
                "property_review": result["property_review"],
                "historical_sensitivity_json": result["audit_json"],
                "scenarios": [
                    {
                        "scenario": item["scenario"],
                        "eligible_count": item["eligible_count"],
                        "lost_vs_e4_baseline": item["lost_vs_e4_baseline"],
                        "wards_ge_5": item["ward_sample_coverage"][
                            "wards_with_at_least_5_records_in_any_property_type"
                        ],
                        "wards_ge_10": item["ward_sample_coverage"][
                            "wards_with_at_least_10_records_in_any_property_type"
                        ],
                    }
                    for item in sensitivity["sensitivity_scenarios"]
                ],
                "safety": result["safety"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
