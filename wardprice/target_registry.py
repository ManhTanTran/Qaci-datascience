"""Import and validate the legacy Top 50 ward target registry."""

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile

TOP50_CSV_MEMBER = "top50_targets_with_mapping_review.csv"
REQUIRED_COLUMNS = {
    "rank",
    "old_province",
    "old_district",
    "old_ward",
    "category",
    "n_customers",
    "pct",
    "batch",
    "current_province",
    "current_ward",
    "current_ward_code",
    "status",
    "mapping_note",
    "source_url",
}


@dataclass(frozen=True)
class LegacyWardTarget:
    rank: int
    old_province: str
    old_district: str
    old_ward: str
    category: str
    n_customers: int
    pct: float
    batch: int
    current_province: str
    current_ward: str
    current_ward_code: str | None
    status: str
    mapping_note: str
    source_url: str


def _read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".zip":
        try:
            with ZipFile(path) as archive:
                members = [
                    name for name in archive.namelist()
                    if Path(name).name == TOP50_CSV_MEMBER
                ]
                if len(members) != 1:
                    raise ValueError(
                        f"ZIP must contain exactly one {TOP50_CSV_MEMBER} member"
                    )
                with archive.open(members[0]) as binary:
                    import io

                    text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                    return list(csv.DictReader(text))
        except BadZipFile as exc:
            raise ValueError("Input file is not a valid ZIP archive") from exc

    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_legacy_targets(path: Path) -> list[LegacyWardTarget]:
    """Load 50 ranked targets from CSV or directly from the supplied Top50 ZIP.

    ZIP contents are read in place and never extracted. Customer counts remain
    local to the target registry and are not part of the Gemini prompt API.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Top 50 target file not found: {path}")
    rows = _read_rows(path)
    if not rows:
        raise ValueError("Top 50 target file is empty")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"Top 50 target file is missing columns: {', '.join(sorted(missing))}")

    targets: list[LegacyWardTarget] = []
    seen_ranks: set[int] = set()
    seen_locations: set[tuple[str, str, str]] = set()
    for row_idx, row in enumerate(rows, start=2):
        try:
            rank = int((row.get("rank") or "").strip())
            n_customers = int((row.get("n_customers") or "").strip())
            pct = float((row.get("pct") or "").strip())
            batch = int((row.get("batch") or "").strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"row {row_idx}: rank/count/pct/batch must be numeric") from exc

        old_province, old_district, old_ward = (
            (row.get(key) or "").strip()
            for key in ("old_province", "old_district", "old_ward")
        )
        category = (row.get("category") or "").strip().upper()
        if rank < 1 or rank > 50:
            raise ValueError(f"row {row_idx}: rank must be between 1 and 50")
        if rank in seen_ranks:
            raise ValueError(f"row {row_idx}: duplicate target rank {rank}")
        if not (old_province and old_district and old_ward):
            raise ValueError(f"row {row_idx}: original administrative names are required")
        if category not in {"PHƯỜNG", "XÃ"}:
            raise ValueError(f"row {row_idx}: category must be PHƯỜNG or XÃ")
        if n_customers < 0 or not math.isfinite(pct) or pct < 0:
            raise ValueError(f"row {row_idx}: customer count and pct must be nonnegative")
        if batch < 1 or batch > 10:
            raise ValueError(f"row {row_idx}: batch must be between 1 and 10")
        if batch != (rank - 1) // 5 + 1:
            raise ValueError(f"row {row_idx}: batch does not match the rank's five-target slot")

        location_key = (old_province.casefold(), old_district.casefold(), old_ward.casefold())
        if location_key in seen_locations:
            raise ValueError(f"row {row_idx}: duplicate original target location")
        seen_ranks.add(rank)
        seen_locations.add(location_key)

        current_ward_code = (row.get("current_ward_code") or "").strip() or None
        status = (row.get("status") or "").strip().upper()
        if status not in {"REVIEWED_RESOLUTION", "PENDING_ADMIN_MAPPING"}:
            raise ValueError(f"row {row_idx}: unsupported administrative mapping status")
        source_url = (row.get("source_url") or "").strip()
        if source_url:
            parsed = urlparse(source_url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError(f"row {row_idx}: mapping source_url must be HTTPS")

        targets.append(
            LegacyWardTarget(
                rank=rank,
                old_province=old_province,
                old_district=old_district,
                old_ward=old_ward,
                category=category,
                n_customers=n_customers,
                pct=pct,
                batch=batch,
                current_province=(row.get("current_province") or "").strip(),
                current_ward=(row.get("current_ward") or "").strip(),
                current_ward_code=current_ward_code,
                status=status,
                mapping_note=(row.get("mapping_note") or "").strip(),
                source_url=source_url,
            )
        )

    if seen_ranks != set(range(1, 51)):
        raise ValueError("Top 50 target ranks must contain each rank from 1 through 50 exactly once")
    return sorted(targets, key=lambda target: target.rank)


def target_summary(targets: list[LegacyWardTarget]) -> dict:
    """Return aggregate counts only; never include customer-count fields."""
    category_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    batch_counts: dict[str, int] = {}
    for target in targets:
        category_counts[target.category] = category_counts.get(target.category, 0) + 1
        status_counts[target.status] = status_counts.get(target.status, 0) + 1
        key = str(target.batch)
        batch_counts[key] = batch_counts.get(key, 0) + 1
    return {
        "target_count": len(targets),
        "category_counts": category_counts,
        "mapping_status_counts": status_counts,
        "batch_counts": batch_counts,
    }
