"""Generate privacy-safe DC5 demo files for the local UI."""

from __future__ import annotations

import argparse

from credit_scoring.dc5.synthetic import (
    build_demo_frame,
    write_demo_parquet,
    write_demo_workbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic DC5 demo data.")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument(
        "--parquet",
        default="data_extracted/model_df_extracted.parquet",
    )
    parser.add_argument("--xlsx", default="artifacts/dc5_demo_100k.xlsx")
    args = parser.parse_args()
    frame = build_demo_frame(n_rows=args.rows, seed=args.seed)
    parquet_path = write_demo_parquet(frame, args.parquet)
    workbook_path = write_demo_workbook(frame, args.xlsx)
    print(f"rows={len(frame):,}")
    print(f"parquet={parquet_path}")
    print(f"xlsx={workbook_path}")


if __name__ == "__main__":
    main()
