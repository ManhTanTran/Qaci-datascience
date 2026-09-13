"""Safely prepare only the research workbook from a supplied ZIP archive."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from credit_scoring.research.fpt_reasoning_poc.common import RAW_DIR

WORKBOOK_NAME = "FPT_credit_scoring_synthetic_10_cases.xlsx"


def prepare(zip_path: str | Path, *, output_dir: str | Path = RAW_DIR) -> Path:
    archive_path = Path(zip_path)
    if not archive_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ZIP: {archive_path}")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        if WORKBOOK_NAME not in archive.namelist():
            raise ValueError(f"ZIP thiếu workbook bắt buộc: {WORKBOOK_NAME}")
        target = destination / WORKBOOK_NAME
        with archive.open(WORKBOOK_NAME) as source, target.open("wb") as output:
            output.write(source.read())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Chuẩn bị workbook FPT reasoning research.")
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    print(f"Đã chuẩn bị: {prepare(args.zip, output_dir=args.output_dir)}")


if __name__ == "__main__":
    main()
