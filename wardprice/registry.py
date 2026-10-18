"""Administrative registry supplied by operator; no guesses or auto-remapping."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ward:
    code: str
    name: str
    province: str
    source: str
    district: str = ""


def load_verified_wards(csv_path: Path) -> tuple[list[Ward], list[str]]:
    wards: list[Ward] = []
    warnings: list[str] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"ward_code", "ward_name", "province", "admin_verified", "admin_source"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"Registry CSV must contain {sorted(required)}")
        seen = set()
        for row_idx, row in enumerate(reader, start=2):
            code, name, province = (
                row.get(k, "").strip() for k in ("ward_code", "ward_name", "province")
            )
            source = (row.get("admin_source") or "").strip()
            verified = (row.get("admin_verified") or "").strip().lower() in {"true", "yes", "1"}
            if not (code and name and province and verified and source.startswith("https://")):
                warnings.append(
                    f"row {row_idx}: not admitted (missing admin evidence or not verified)"
                )
                continue
            if code in seen:
                warnings.append(f"row {row_idx}: duplicate code {code}")
                continue
            seen.add(code)
            district = (row.get("district") or "").strip()
            wards.append(Ward(code, name, province, source, district))
    return wards, warnings


def load_ward_whitelist(csv_path: Path) -> list[Ward]:
    """Read the operator's explicit research whitelist (50–100 is typical; max 100)."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Ward whitelist not found: {csv_path}")
    wards: list[Ward] = []
    seen: set[str] = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ward_code", "ward_name", "province"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"Ward CSV must contain columns: {', '.join(sorted(required))}")
        for row_idx, row in enumerate(reader, start=2):
            code, name, province = (
                (row.get(key) or "").strip()
                for key in ("ward_code", "ward_name", "province")
            )
            if not (code and name and province):
                raise ValueError(f"row {row_idx}: ward_code, ward_name, and province are required")
            if code in seen:
                raise ValueError(f"row {row_idx}: duplicate ward_code {code}")
            seen.add(code)
            source = (row.get("admin_source") or "").strip()
            district = (row.get("district") or "").strip()
            wards.append(Ward(code, name, province, source, district))
            if len(wards) > 100:
                raise ValueError("Ward whitelist cannot exceed 100 wards")
    if not wards:
        raise ValueError("Ward whitelist is empty")
    return wards
