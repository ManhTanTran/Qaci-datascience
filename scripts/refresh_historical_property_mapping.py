"""Safely apply the current evidence-based property mapping rules to the pilot DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wardprice.config import PROJECT_ROOT
from wardprice.historical_dataset import refresh_title_supported_property_mappings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pilot-db",
        type=Path,
        default=PROJECT_ROOT / "state" / "ward_prices.historical_pilot.sqlite3",
    )
    args = parser.parse_args()
    try:
        result = refresh_title_supported_property_mappings(args.pilot_db)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
