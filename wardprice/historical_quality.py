"""Offline diagnostics for the bounded TiniX historical pilot sample."""

from __future__ import annotations

import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .historical_dataset import (
    DATASET_ID,
    _positive_number,
    _quantile,
    _sample_quality_level,
    load_metadata,
    load_sample,
)

MIN_TUKEY_GROUP_SIZE = 10
MIN_MAD_GROUP_SIZE = 30


def tukey_iqr(
    values: list[float], *, min_sample_count: int = MIN_TUKEY_GROUP_SIZE
) -> dict[str, Any]:
    if len(values) < min_sample_count:
        return {"sample_count": len(values), "applied": False, "reason": "INSUFFICIENT_SAMPLE"}
    p25 = _quantile(values, 0.25)
    p75 = _quantile(values, 0.75)
    iqr = p75 - p25
    lower = p25 - 1.5 * iqr
    upper = p75 + 1.5 * iqr
    return {
        "sample_count": len(values),
        "applied": True,
        "p25_price_per_m2": p25,
        "p75_price_per_m2": p75,
        "lower_fence": lower,
        "upper_fence": upper,
        "flagged_count": sum(value < lower or value > upper for value in values),
        "method": "TUKEY_1_5_IQR_DIAGNOSTIC_ONLY",
    }


def robust_mad(values: list[float], *, min_sample_count: int = MIN_MAD_GROUP_SIZE) -> dict[str, Any]:
    if len(values) < min_sample_count:
        return {"sample_count": len(values), "applied": False, "reason": "INSUFFICIENT_SAMPLE"}
    median = statistics.median(values)
    mad = statistics.median(abs(value - median) for value in values)
    if mad == 0:
        return {"sample_count": len(values), "applied": False, "reason": "ZERO_MAD"}
    modified_z_cutoff = 3.5
    scaled_mad_cutoff = modified_z_cutoff * 1.4826 * mad
    return {
        "sample_count": len(values),
        "applied": True,
        "median_price_per_m2": median,
        "median_absolute_deviation": mad,
        "modified_z_cutoff": modified_z_cutoff,
        "flagged_count": sum(abs(value - median) > scaled_mad_cutoff for value in values),
        "method": "MODIFIED_Z_SCORE_MAD_DIAGNOSTIC_ONLY_N_GE_30",
    }


def _numeric_issue_counts(rows: list[dict[str, Any]], column: str) -> dict[str, int]:
    missing = invalid = valid = 0
    for row in rows:
        value = row.get(column)
        if value is None or value == "":
            missing += 1
        elif _positive_number(value) is None:
            invalid += 1
        else:
            valid += 1
    return {"valid": valid, "missing": missing, "invalid": invalid}


def _db_candidate_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dataset = connection.execute(
            "SELECT dataset_id,revision FROM historical_dataset_registry "
            "WHERE dataset_id=? ORDER BY retrieved_at DESC LIMIT 1",
            (DATASET_ID,),
        ).fetchone()
        if dataset is None:
            raise ValueError(f"No {DATASET_ID} dataset is registered in {path}")
        revision = str(dataset["revision"])
        candidates = [
            dict(row)
            for row in connection.execute(
                """SELECT candidate_id,target_rank,property_type_raw,property_type,title,
                          deal_type,deal_classification,dedupe_classification,candidate_status,
                          published_date,price_vnd,area_m2,price_per_m2,review_reason,evidence_status
                   FROM historical_candidates WHERE dataset_id=? AND dataset_revision=?""",
                (dataset["dataset_id"], revision),
            )
        ]
        summary = {
            "dataset_id": dataset["dataset_id"],
            "revision": revision,
            "source_rows": int(
                connection.execute(
                    """SELECT COUNT(*) FROM historical_source_rows
                       WHERE dataset_id=? AND dataset_revision=?""",
                    (dataset["dataset_id"], revision),
                ).fetchone()[0]
            ),
            "candidate_count": len(candidates),
            "covered_targets": int(
                connection.execute(
                    """SELECT COUNT(DISTINCT target_rank) FROM historical_candidates
                       WHERE dataset_id=? AND dataset_revision=?""",
                    (dataset["dataset_id"], revision),
                ).fetchone()[0]
            ),
            "monthly_groups": int(
                connection.execute(
                    """SELECT COUNT(*) FROM historical_monthly_statistics
                       WHERE dataset_id=? AND dataset_revision=?""",
                    (dataset["dataset_id"], revision),
                ).fetchone()[0]
            ),
            "statistics_eligible_count": int(
                connection.execute(
                    """SELECT COUNT(*) FROM historical_candidates
                       WHERE dataset_id=? AND dataset_revision=?
                         AND candidate_status='ELIGIBLE_HISTORICAL_SALE'
                         AND deal_type='EXPLICIT_SALE'
                         AND property_type IN ('DAT_O','NHA_RIENG','CHUNG_CU')
                         AND dedupe_classification NOT IN ('POSSIBLE_DUPLICATE','NEEDS_REVIEW')""",
                    (dataset["dataset_id"], revision),
                ).fetchone()[0]
            ),
        }
        return candidates, summary
    finally:
        connection.close()


def _candidate_quality(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    property_type_counts: Counter[str] = Counter()
    eligible_count = 0
    monthly_groups: dict[tuple[int, str, str], int] = defaultdict(int)
    sale_rent = Counter()
    global_values = []
    by_raw_type: dict[str, list[float]] = defaultdict(list)
    by_mapped_type: dict[str, list[float]] = defaultdict(list)
    target_type: dict[tuple[int, str], int] = defaultdict(int)
    mapped_from_title = 0

    for row in candidates:
        property_type = row["property_type"]
        property_type_counts[str(property_type or "UNKNOWN")] += 1
        if "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED" in str(
            row["review_reason"] or ""
        ):
            mapped_from_title += 1
        sale_rent[str(row["deal_classification"])] += 1
        eligible = (
            row["candidate_status"] == "ELIGIBLE_HISTORICAL_SALE"
            and row["deal_type"] == "EXPLICIT_SALE"
            and property_type in {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
            and row["dedupe_classification"] not in {"POSSIBLE_DUPLICATE", "NEEDS_REVIEW"}
        )
        eligible_count += int(eligible)
        month = str(row["published_date"])[:7]
        if eligible:
            monthly_groups[(int(row["target_rank"]), str(property_type), month)] += 1
            target_type[(int(row["target_rank"]), str(property_type))] += 1
        value = _positive_number(row["price_per_m2"])
        if eligible and value is not None:
            global_values.append(value)
            by_raw_type[str(row["property_type_raw"] or "<NULL>")].append(value)
            by_mapped_type[str(property_type)].append(value)

    def sample_grades(groups: dict[tuple[int, str, str], int]) -> dict[str, int]:
        return dict(Counter(_sample_quality_level(count) for count in groups.values()))

    ward_type_grade_counts = Counter(
        _sample_quality_level(count) for count in target_type.values()
    )
    ward_counts_by_floor = {
        str(floor): len(
            {
                rank
                for (rank, _property_type), count in target_type.items()
                if count >= floor
            }
        )
        for floor in (5, 10)
    }
    return {
        "mapping": {
            "candidate_count": len(candidates),
            "property_type_counts": dict(sorted(property_type_counts.items())),
            "unknown_count": property_type_counts.get("UNKNOWN", 0),
            "title_based_residential_land_mappings_present": mapped_from_title,
            "rule": "Map raw category Đất to DAT_O only when title contains the exact token phrase đất ở or đất thổ cư and has no agricultural, garden, mixed-area or negation cue; retain unverified evidence status.",
            "no_rule_added_for": ["Biệt thự/Nhà liền kề", "Shophouse", "generic Đất"],
        },
        "deal_classification": {
            "counts_before": dict(sorted(sale_rent.items())),
            "counts_after": dict(sorted(sale_rent.items())),
            "human_labeled_titles": 0,
            "evaluation_metrics_available": False,
        },
        "statistics": {
            "eligible_candidates": eligible_count,
            "monthly_groups": len(monthly_groups),
            "monthly_quality_levels": sample_grades(monthly_groups),
            "ward_property_groups": len(target_type),
            "ward_property_quality_levels_after": dict(sorted(ward_type_grade_counts.items())),
            "wards_with_at_least_5_candidates_in_any_property_type": ward_counts_by_floor["5"],
            "wards_with_at_least_10_candidates_in_any_property_type": ward_counts_by_floor["10"],
            "sample_quality_levels_are_descriptive_only": True,
            "historical_sources_promoted_to_current_verified": 0,
            "historical_sources_promoted_to_daily_new": 0,
        },
        "outliers": {
            "eligible_pilot_candidates": len(global_values),
            "global_tukey": tukey_iqr(global_values),
            "by_source_property_type_tukey": {
                key: tukey_iqr(values) for key, values in sorted(by_raw_type.items())
            },
            "by_mapped_property_type_tukey": {
                key: tukey_iqr(values) for key, values in sorted(by_mapped_type.items())
            },
            "by_mapped_property_type_robust_mad": {
                key: robust_mad(values) for key, values in sorted(by_mapped_type.items())
            },
            "rows_deleted_or_excluded_by_outlier_rules": 0,
        },
    }


def build_historical_e4_audit(
    sample_path: Path,
    metadata_path: Path,
    before_pilot_db: Path,
    after_pilot_db: Path,
) -> dict[str, Any]:
    rows = load_sample(sample_path)
    metadata = load_metadata(metadata_path)
    candidates_before, before_summary = _db_candidate_rows(before_pilot_db)
    candidates_after, after_summary = _db_candidate_rows(after_pilot_db)

    values_by_source_type: dict[str, list[float]] = defaultdict(list)
    values_by_province_type: dict[tuple[str, str], list[float]] = defaultdict(list)
    valid_ratios: list[float] = []
    prices: list[float] = []
    areas: list[float] = []
    for row in rows:
        price = _positive_number(row.get("price"))
        area = _positive_number(row.get("area"))
        if price is None or area is None:
            continue
        ratio = price / area
        if not math.isfinite(ratio):
            continue
        valid_ratios.append(ratio)
        prices.append(price)
        areas.append(area)
        raw_type = str(row.get("property_type_name") or "<NULL>")
        province = str(row.get("province_name") or "<NULL>")
        values_by_source_type[raw_type].append(ratio)
        values_by_province_type[(province, raw_type)].append(ratio)

    review_path = (
        sample_path.parent.parent.parent
        / "outputs"
        / "historical_quality"
        / f"tinix-e3-10000-{str(metadata['revision'])[:12]}_title_review.csv"
    )
    classification_review = None
    if review_path.is_file():
        from .historical_review import review_summary

        classification_review = review_summary(review_path)

    def descriptive_values(values: list[float]) -> dict[str, float | int]:
        return {
            "sample_count": len(values),
            "median_price_per_m2": statistics.median(values),
        }

    quality = {
        "price": _numeric_issue_counts(rows, "price"),
        "area": _numeric_issue_counts(rows, "area"),
        "valid_price_area_rows": len(valid_ratios),
        "price_vnd_review_buckets": {
            "below_100_million": sum(value < 100_000_000 for value in prices),
            "100_million_to_1_billion": sum(100_000_000 <= value < 1_000_000_000 for value in prices),
            "1_billion_to_1_trillion": sum(1_000_000_000 <= value <= 1_000_000_000_000 for value in prices),
            "above_1_trillion": sum(value > 1_000_000_000_000 for value in prices),
        },
        "area_m2_review_buckets": {
            "below_10_m2": sum(value < 10 for value in areas),
            "10_to_1000_m2": sum(10 <= value <= 1000 for value in areas),
            "above_1000_m2": sum(value > 1000 for value in areas),
            "above_10000_m2": sum(value > 10000 for value in areas),
        },
        "units_and_basis": {
            "source_schema_price_dtype": "float64",
            "source_schema_area_dtype": "float64",
            "documented_price_unit": "VND",
            "documented_area_unit": "m²",
            "price_text_unit_conversion_performed": False,
            "price_field_scale_conversion_performed": False,
            "area_basis_column_present": "area_basis" in {
                str(field.get("name")) for field in metadata.get("schema", [])
            },
            "description_column_in_bounded_sample": "description" in rows[0] if rows else False,
            "per_listing_source_url_available": bool(metadata.get("listing_detail_url_field_present")),
            "interpretation": "Numeric range buckets are review signals only; no automatic unit correction or record deletion was applied.",
        },
    }
    report = {
        "phase": "E4",
        "dataset_id": metadata["dataset_id"],
        "revision": metadata["revision"],
        "sample_row_count": len(rows),
        "sample_sha256": metadata.get("sample_sha256"),
        "source_provenance": {
            "additional_source_rows_downloaded": 0,
            "network_attempted": False,
            "production_database_written": False,
            "demo_database_written": False,
        },
        "numeric_validation": quality,
        "global_tukey_1_5_iqr": tukey_iqr(valid_ratios),
        "by_source_property_type_tukey": {
            key: tukey_iqr(values) for key, values in sorted(values_by_source_type.items())
        },
        "by_source_property_type_mad": {
            key: robust_mad(values) for key, values in sorted(values_by_source_type.items())
        },
        "province_property_type_medians_n_ge_30": [
            {
                "province": province,
                "property_type_raw": property_type,
                **descriptive_values(values),
            }
            for (province, property_type), values in sorted(values_by_province_type.items())
            if len(values) >= 30
        ],
        "pilot_before": before_summary,
        "pilot_after": after_summary,
        "pilot_quality_before_after": {
            "before": _candidate_quality(candidates_before),
            "after": _candidate_quality(candidates_after),
        },
        "classification_review_csv": {
            "path": str(review_path),
            "summary": classification_review,
        },
        "limitations": [
            "The bounded sample is non-probability and does not establish national or current-market representativeness.",
            "The source has no per-listing URL, transaction-type field, or area-basis field; land area and floor area cannot be distinguished reliably.",
            "Outlier flags are review signals only. Tukey and MAD never remove rows or establish that a source value is wrong.",
            "No human title labels exist yet; precision, recall, F1, coverage and abstention evaluation are unavailable.",
            "Historical rows remain HISTORICAL_DATASET_UNVERIFIED and are excluded from CURRENT_VERIFIED, DAILY_NEW and AI context.",
        ],
    }
    return report
