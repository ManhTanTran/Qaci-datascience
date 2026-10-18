"""Review or evaluate the 100-title manual classification CSV without AI labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wardprice.historical_review import label_unreviewed_rows, review_summary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_CSV = (
    PROJECT_ROOT
    / "outputs"
    / "historical_quality"
    / "tinix-e3-10000-ca3fedcbb089_title_review.csv"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_REVIEW_CSV)
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt a human to label currently blank rows; existing labels are preserved.",
    )
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"Review CSV not found: {args.csv}")
    try:
        result = (
            label_unreviewed_rows(args.csv)
            if args.interactive
            else review_summary(args.csv)
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
