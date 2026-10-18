"""Write an offline E4 audit from the existing sample and before/after pilot databases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wardprice.config import PROJECT_ROOT
from wardprice.historical_quality import build_historical_e4_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=PROJECT_ROOT / "data" / "historical_pilot" / "tinix_sample_10000.jsonl",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=PROJECT_ROOT / "data" / "historical_pilot" / "tinix_sample_10000.metadata.json",
    )
    parser.add_argument("--before-db", type=Path, required=True)
    parser.add_argument(
        "--after-db",
        type=Path,
        default=PROJECT_ROOT / "state" / "ward_prices.historical_pilot.sqlite3",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "historical_quality" / "tinix-e4-quality-audit.json",
    )
    args = parser.parse_args()
    try:
        result = build_historical_e4_audit(
            args.sample,
            args.metadata,
            args.before_db,
            args.after_db,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps({"report_path": str(args.output), **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
