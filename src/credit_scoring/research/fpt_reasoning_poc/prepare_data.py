from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from .common import RAW_DIR, ensure_directories

REQUIRED_FILES = {
    "FPT_credit_scoring_synthetic_10_cases.xlsx",
    "feature_definitions.csv",
}


def prepare(zip_path: Path) -> list[Path]:
    ensure_directories()
    if not zip_path.exists():
        raise FileNotFoundError(f"Không tìm thấy ZIP: {zip_path}")

    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        missing = REQUIRED_FILES - names
        if missing:
            raise ValueError(f"ZIP thiếu file bắt buộc: {sorted(missing)}")
        for name in sorted(REQUIRED_FILES):
            target = RAW_DIR / Path(name).name
            with archive.open(name) as source, target.open("wb") as destination:
                destination.write(source.read())
            extracted.append(target)
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Giải nén dữ liệu cần thiết từ simulate_v3.zip")
    parser.add_argument("--zip", required=True, type=Path)
    args = parser.parse_args()
    for path in prepare(args.zip):
        print(f"Đã chuẩn bị: {path}")


if __name__ == "__main__":
    main()

