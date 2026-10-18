"""Validate and summarize human property-type labels without source verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from wardprice.historical_review_e5 import validate_property_review_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=PROJECT_ROOT
        / "outputs"
        / "historical_quality"
        / "tinix-e5-property-review.csv",
    )
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"Property review CSV not found: {args.csv}")
    try:
        result = validate_property_review_csv(args.csv)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
