"""Human-review packet creation and read-only E5 historical-quality audit."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .historical_dataset import DATASET_ID, _positive_number
from .historical_quality import tukey_iqr
from .historical_review import PREDICTION_LABELS, load_review_csv
from .national_registry import normalize_admin_name

E4_RULE_VERSION = "E4"
PROPERTY_LABELS = ("DAT_O", "NHA_RIENG", "CHUNG_CU", "OTHER", "UNKNOWN")
E4_ELIGIBLE_TYPES = {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
EXCLUDED_DEDUPE_CLASSES = {"POSSIBLE_DUPLICATE", "NEEDS_REVIEW"}

CLASSIFICATION_PACKET_COLUMNS = (
    "source_row_id",
    "source_row_index",
    "source_shard",
    "target_rank",
    "province_name",
    "district_name",
    "ward_name",
    "title",
    "predicted_classification",
    "e4_rule_version",
    "rule_predicted_label",
    "rule_confidence",
    "rule_confidence_note",
    "source_property_type_name",
    "source_project_name",
    "source_street_name",
    "source_price_present",
    "source_area_present",
    "source_area_basis_present",
    "source_listing_detail_url_present",
    "human_label",
    "reviewer_notes",
    "review_status",
    "sampling_stratum",
    "review_notes",
)

PROPERTY_PACKET_COLUMNS = (
    "candidate_id",
    "source_row_id",
    "source_row_index",
    "source_shard",
    "target_rank",
    "original_ward",
    "original_district",
    "original_province",
    "title",
    "project_name",
    "street_name",
    "property_type_raw",
    "e4_property_type",
    "deal_classification",
    "price_vnd",
    "area_m2",
    "price_per_m2",
    "property_review_reason",
    "evidence_status",
    "dataset_url_not_listing_url",
    "human_property_label",
    "reviewer_notes",
    "review_status",
)

_HOUSE_CUES = ("nha rieng", "nha pho", "nha mat pho", "biet thu", "villa")
_APARTMENT_CUES = ("can ho", "chung cu", "apartment")
_LAND_CUES = ("dat o", "dat tho cu")


def source_row_id(
    revision: str, source_shard: str | None, source_row_index: str | int
) -> str:
    """Build a stable identity from the dataset revision and original row coordinates."""
    shard = str(source_shard or "NO_SHARD")
    return f"{DATASET_ID}@{revision}:{shard}:{source_row_index}"


def _contains_cue(title: str, cues: tuple[str, ...]) -> list[str]:
    normalized_title = normalize_admin_name(title)
    return [cue for cue in cues if normalize_admin_name(cue) in normalized_title]


def _classification_packet_rows(
    source_rows: list[dict[str, str]],
    revision: str,
    source_contexts: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    rows = []
    seen_ids = set()
    for row in source_rows:
        row_id = source_row_id(
            revision, row.get("source_shard"), row.get("source_row_index", "")
        )
        if row_id in seen_ids:
            raise ValueError(f"Repeated source_row_id in classification sample: {row_id}")
        seen_ids.add(row_id)
        prediction = row.get("predicted_classification", "").strip()
        if prediction not in PREDICTION_LABELS:
            raise ValueError(f"Unsupported E4 prediction for source row {row_id}: {prediction!r}")
        human_label = row.get("human_label", "").strip().upper()
        context = (source_contexts or {}).get(
            (str(row.get("source_shard") or ""), str(row.get("source_row_index") or "")),
            {},
        )
        output = dict(row)
        output.update(
            {
                "source_row_id": row_id,
                "e4_rule_version": E4_RULE_VERSION,
                "rule_predicted_label": PREDICTION_LABELS[prediction],
                "rule_confidence": "",
                "rule_confidence_note": "NOT_AVAILABLE: deterministic E4 rules are not calibrated probabilities.",
                "source_property_type_name": str(context.get("property_type_name") or ""),
                "source_project_name": str(context.get("project_name") or ""),
                "source_street_name": str(context.get("street_name") or ""),
                "source_price_present": _field_present(context, "price"),
                "source_area_present": _field_present(context, "area"),
                "source_area_basis_present": _field_present(context, "area_basis"),
                "source_listing_detail_url_present": _has_source_url(context),
                "human_label": human_label,
                "reviewer_notes": row.get("review_notes", ""),
                "review_status": "REVIEWED" if human_label else "NOT_REVIEWED",
                "sampling_stratum": prediction,
            }
        )
        rows.append(output)
    return rows


def _field_present(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    return "true" if value is not None and value != "" else "false"


def _has_source_url(payload: dict[str, Any]) -> str:
    return "true" if _listing_source_url(payload) else "false"


def _source_contexts_read_only(
    pilot_db: Path, revision: str, rows: list[dict[str, str]]
) -> dict[tuple[str, str], dict[str, Any]]:
    coordinates = {
        (str(row.get("source_shard") or ""), str(row.get("source_row_index") or ""))
        for row in rows
    }
    indexes = sorted({int(index) for _shard, index in coordinates if index.isdigit()})
    if not indexes:
        return {}
    connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        contexts = {}
        batch_size = 800
        for start in range(0, len(indexes), batch_size):
            batch = indexes[start : start + batch_size]
            placeholders = ",".join("?" for _ in batch)
            for row in connection.execute(
                f"""SELECT source_row_index,source_shard,raw_payload FROM historical_source_rows
                    WHERE dataset_id=? AND dataset_revision=?
                      AND source_row_index IN ({placeholders})""",
                (DATASET_ID, revision, *batch),
            ):
                try:
                    payload = json.loads(row["raw_payload"] or "{}")
                except json.JSONDecodeError:
                    payload = {}
                key = (str(row["source_shard"] or ""), str(row["source_row_index"]))
                contexts[key] = payload
        return contexts
    finally:
        connection.close()


def _candidate_rows_read_only(pilot_db: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], int]:
    if not pilot_db.is_file():
        raise FileNotFoundError(f"Historical pilot database not found: {pilot_db}")
    connection = sqlite3.connect(f"{pilot_db.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dataset = connection.execute(
            "SELECT * FROM historical_dataset_registry WHERE dataset_id=? "
            "ORDER BY retrieved_at DESC LIMIT 1",
            (DATASET_ID,),
        ).fetchone()
        if dataset is None:
            raise ValueError(f"No {DATASET_ID} dataset is registered in {pilot_db}")
        revision = str(dataset["revision"])
        candidates = [
            dict(row)
            for row in connection.execute(
                """SELECT * FROM historical_candidates
                   WHERE dataset_id=? AND dataset_revision=?
                   ORDER BY target_rank,source_row_index,candidate_id""",
                (DATASET_ID, revision),
            )
        ]
        targets = [
            dict(row)
            for row in connection.execute(
                """SELECT target_rank,original_ward,original_district,original_province
                   FROM historical_target_registry ORDER BY target_rank"""
            )
        ]
        duplicate_pair_count = int(
            connection.execute(
                """SELECT COUNT(*) FROM historical_duplicate_pairs
                   WHERE dataset_id=? AND dataset_revision=?""",
                (DATASET_ID, revision),
            ).fetchone()[0]
        )
        return candidates, dict(dataset), targets, duplicate_pair_count
    finally:
        connection.close()


def _property_review_rows(
    candidates: list[dict[str, Any]], revision: str
) -> list[dict[str, str]]:
    rows = []
    for candidate in candidates:
        mapped_type = candidate.get("property_type") or "UNKNOWN"
        title = str(candidate.get("title") or "")
        reasons = []
        if mapped_type == "DAT_O":
            reasons.append("E4_DAT_O_MAPPING_REVIEW")
        if mapped_type == "UNKNOWN":
            reasons.append("E4_PROPERTY_TYPE_UNKNOWN")

        conflicting_cues: list[str] = []
        if mapped_type == "NHA_RIENG":
            conflicting_cues.extend(_contains_cue(title, _APARTMENT_CUES))
            conflicting_cues.extend(_contains_cue(title, _LAND_CUES))
        elif mapped_type == "CHUNG_CU":
            conflicting_cues.extend(_contains_cue(title, _HOUSE_CUES))
            conflicting_cues.extend(_contains_cue(title, _LAND_CUES))
        if conflicting_cues:
            reasons.append("TITLE_CUE_CONFLICT_WITH_E4_MAPPING:" + "|".join(conflicting_cues))
        if not reasons:
            continue

        try:
            raw = json.loads(candidate.get("raw_payload") or "{}")
        except json.JSONDecodeError:
            raw = {}
        row_id = source_row_id(
            revision,
            candidate.get("source_shard"),
            candidate.get("source_row_index", ""),
        )
        rows.append(
            {
                "candidate_id": str(candidate.get("candidate_id") or ""),
                "source_row_id": row_id,
                "source_row_index": str(candidate.get("source_row_index") or ""),
                "source_shard": str(candidate.get("source_shard") or ""),
                "target_rank": str(candidate.get("target_rank") or ""),
                "original_ward": str(candidate.get("original_ward") or ""),
                "original_district": str(candidate.get("original_district") or ""),
                "original_province": str(candidate.get("original_province") or ""),
                "title": title,
                "project_name": str(raw.get("project_name") or ""),
                "street_name": str(raw.get("street_name") or ""),
                "property_type_raw": str(candidate.get("property_type_raw") or ""),
                "e4_property_type": mapped_type,
                "deal_classification": str(candidate.get("deal_classification") or ""),
                "price_vnd": str(candidate.get("price_vnd") or ""),
                "area_m2": str(candidate.get("area_m2") or ""),
                "price_per_m2": str(candidate.get("price_per_m2") or ""),
                "property_review_reason": ";".join(reasons),
                "evidence_status": str(candidate.get("evidence_status") or ""),
                "dataset_url_not_listing_url": str(candidate.get("source_dataset_url") or ""),
                "human_property_label": "",
                "reviewer_notes": "",
                "review_status": "NOT_REVIEWED",
            }
        )
    return rows


def _is_e4_eligible(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("candidate_status") == "ELIGIBLE_HISTORICAL_SALE"
        and candidate.get("deal_type") == "EXPLICIT_SALE"
        and candidate.get("property_type") in E4_ELIGIBLE_TYPES
        and candidate.get("dedupe_classification") not in EXCLUDED_DEDUPE_CLASSES
    )


def _listing_source_url(raw_payload: dict[str, Any]) -> str:
    for key in ("source_url", "listing_url", "detail_url", "url"):
        value = raw_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _area_basis(raw_payload: dict[str, Any]) -> str:
    value = raw_payload.get("area_basis")
    return str(value).strip() if value is not None else ""


def _target_sample_summary(
    candidates: list[dict[str, Any]], targets: list[dict[str, Any]]
) -> dict[str, Any]:
    counts: Counter[tuple[int, str]] = Counter()
    for candidate in candidates:
        counts[(int(candidate["target_rank"]), str(candidate["property_type"]))] += 1
    target_by_rank = {int(target["target_rank"]): target for target in targets}
    populated_small_groups = []
    wards_with_data = set()
    wards_ge_5: set[int] = set()
    wards_ge_10: set[int] = set()
    for (rank, property_type), count in sorted(counts.items()):
        target = target_by_rank.get(rank, {})
        wards_with_data.add(rank)
        if count >= 5:
            wards_ge_5.add(rank)
        if count >= 10:
            wards_ge_10.add(rank)
        if count < 5:
            populated_small_groups.append(
                {
                    "target_rank": rank,
                    "ward": target.get("original_ward", ""),
                    "property_type": property_type,
                    "sample_count": count,
                }
            )
    all_ranks = set(target_by_rank)
    return {
        "eligible_ward_property_groups": len(counts),
        "populated_groups_below_5": populated_small_groups,
        "wards_with_any_eligible_records": len(wards_with_data),
        "wards_with_at_least_5_records_in_any_property_type": len(wards_ge_5),
        "wards_with_at_least_10_records_in_any_property_type": len(wards_ge_10),
        "wards_with_no_eligible_records": [
            {"target_rank": rank, "ward": target_by_rank[rank].get("original_ward", "")}
            for rank in sorted(all_ranks - wards_with_data)
        ],
    }


def _sensitivity_report(
    candidates: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    duplicate_pair_count: int,
) -> dict[str, Any]:
    eligible = [candidate for candidate in candidates if _is_e4_eligible(candidate)]
    try:
        parsed_payloads = [json.loads(candidate.get("raw_payload") or "{}") for candidate in eligible]
    except json.JSONDecodeError as exc:
        raise ValueError("Pilot database contains invalid candidate raw_payload JSON") from exc
    values = [float(candidate["price_per_m2"]) for candidate in eligible if candidate.get("price_per_m2")]
    tukey = tukey_iqr(values)
    tukey_outlier_ids: set[str] = set()
    if tukey.get("applied"):
        lower = float(tukey["lower_fence"])
        upper = float(tukey["upper_fence"])
        tukey_outlier_ids = {
            str(candidate["candidate_id"])
            for candidate in eligible
            if float(candidate["price_per_m2"]) < lower
            or float(candidate["price_per_m2"]) > upper
        }

    no_title_mapped_land = [
        candidate
        for candidate in eligible
        if "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED"
        not in str(candidate.get("review_reason") or "")
    ]
    source_url_rows = []
    area_basis_rows = []
    for candidate, raw in zip(eligible, parsed_payloads, strict=True):
        if _listing_source_url(raw):
            source_url_rows.append(candidate)
        if _area_basis(raw):
            area_basis_rows.append(candidate)
    source_and_area_rows = [
        candidate
        for candidate, raw in zip(eligible, parsed_payloads, strict=True)
        if _listing_source_url(raw) and _area_basis(raw)
    ]

    type_counts = Counter(str(row.get("property_type") or "UNKNOWN") for row in eligible)
    deal_counts = Counter(str(row.get("deal_classification") or "UNKNOWN") for row in eligible)
    numeric_issues: dict[str, int] = Counter()
    prices: list[float] = []
    areas: list[float] = []
    price_per_area: list[float] = []
    for candidate in eligible:
        for field, values_target in (
            ("price_vnd", prices),
            ("area_m2", areas),
            ("price_per_m2", price_per_area),
        ):
            value = _positive_number(candidate.get(field))
            if value is None or not math.isfinite(value):
                numeric_issues[f"{field}_missing_or_invalid"] += 1
            else:
                values_target.append(value)

    title_price_area_keys = Counter(
        (
            int(candidate["target_rank"]),
            str(candidate["property_type"]),
            normalize_admin_name(candidate.get("title", "")),
            str(candidate.get("price_vnd", "")),
            str(candidate.get("area_m2", "")),
        )
        for candidate in eligible
    )
    duplicate_content_groups = sum(count > 1 for count in title_price_area_keys.values())
    duplicate_content_excess_rows = sum(count - 1 for count in title_price_area_keys.values() if count > 1)

    scenarios = [
        ("E4_BASELINE", eligible),
        ("EXCLUDE_TITLE_DERIVED_DAT_O", no_title_mapped_land),
        (
            "EXCLUDE_GLOBAL_TUKEY_FLAGS_DIAGNOSTIC_ONLY",
            [row for row in eligible if str(row["candidate_id"]) not in tukey_outlier_ids],
        ),
        ("REQUIRE_PER_LISTING_SOURCE_URL", source_url_rows),
        ("REQUIRE_EXPLICIT_AREA_BASIS", area_basis_rows),
        ("REQUIRE_SOURCE_URL_AND_AREA_BASIS", source_and_area_rows),
        ("REQUIRE_INDEPENDENT_HUMAN_SALE_LABEL", []),
    ]
    scenario_reports = []
    for name, selected in scenarios:
        scenario_reports.append(
            {
                "scenario": name,
                "eligible_count": len(selected),
                "lost_vs_e4_baseline": len(eligible) - len(selected),
                "ward_sample_coverage": _target_sample_summary(selected, targets),
                "interpretation": (
                    "Diagnostic sensitivity only; no records were removed from SQLite."
                    if "TUKEY" in name
                    else "Sensitivity only; no records were removed from SQLite."
                ),
            }
        )

    eligible_reason_type_counts = Counter()
    for candidate in eligible:
        if "PROPERTY_TYPE_FROM_TITLE_RESIDENTIAL_LAND_UNVERIFIED" in str(
            candidate.get("review_reason") or ""
        ):
            eligible_reason_type_counts["TITLE_DERIVED_DAT_O"] += 1
        else:
            eligible_reason_type_counts["RAW_CATEGORY_MAPPING"] += 1

    return {
        "eligible_record_audit": {
            "e4_eligible_count": len(eligible),
            "e4_eligible_by_deal_classification": dict(sorted(deal_counts.items())),
            "e4_eligible_by_property_type": dict(sorted(type_counts.items())),
            "all_current_deal_type_values_are_explicit_sale": all(
                row.get("deal_type") == "EXPLICIT_SALE" for row in eligible
            ),
            "sale_evidence_scope": "E4 title rules only; not human-confirmed and not source-verified.",
            "property_mapping_basis_counts": dict(sorted(eligible_reason_type_counts.items())),
            "area_basis_present_count": len(area_basis_rows),
            "per_listing_source_url_present_count": len(source_url_rows),
            "numeric_valid_counts": {
                "price_vnd": len(prices),
                "area_m2": len(areas),
                "price_per_m2": len(price_per_area),
            },
            "numeric_missing_or_invalid_counts": dict(sorted(numeric_issues.items())),
            "price_vnd_min_max_median": _numeric_summary(prices),
            "area_m2_min_max_median": _numeric_summary(areas),
            "price_per_m2_min_max_median": _numeric_summary(price_per_area),
            "global_tukey_1_5_iqr_diagnostic": tukey,
            "tukey_flagged_candidate_count": len(tukey_outlier_ids),
            "tukey_is_diagnostic_only": True,
            "dedupe_audit": {
                "duplicate_pair_rows_in_table": duplicate_pair_count,
                "candidate_rows_flagged_as_duplicate_or_review": sum(
                    candidate.get("dedupe_classification") in EXCLUDED_DEDUPE_CLASSES
                    for candidate in eligible
                ),
                "exact_target_type_title_price_area_duplicate_groups": duplicate_content_groups,
                "excess_rows_in_exact_content_groups": duplicate_content_excess_rows,
                "cross_source_duplicates_ruled_out": False,
            },
            "area_basis_field_available_in_source_rows": bool(area_basis_rows),
            "listing_detail_url_available_in_source_rows": bool(source_url_rows),
            "evidence_status_counts": dict(
                sorted(Counter(str(row.get("evidence_status") or "UNKNOWN") for row in eligible).items())
            ),
        },
        "sensitivity_scenarios": scenario_reports,
        "limitations": [
            "The 473 baseline rows meet E4 deterministic filters; sale intent is title-rule evidence, not independent ground truth.",
            "The source schema has no explicit area_basis or per-listing detail URL for these records; the source dataset page is not a listing citation.",
            "An exact normalized title/price/area match is a duplicate signal, not proof of duplicate identity; different listings may share text.",
            "No outlier or quality scenario deletes or changes a pilot database record.",
            "Historical candidates remain HISTORICAL_DATASET_UNVERIFIED and are not CURRENT_VERIFIED, DAILY_NEW, or production AI context.",
        ],
    }


def _numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _write_csv(path: Path, rows: list[dict[str, str]], columns: tuple[str, ...]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite review data: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing E5 audit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_phase_e5(
    *,
    title_review_csv: Path,
    pilot_db: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create blank review packets and a read-only quality sensitivity report."""
    classification_path = output_dir / "tinix-e5-title-review.csv"
    property_path = output_dir / "tinix-e5-property-review.csv"
    audit_path = output_dir / "tinix-e5-historical-sensitivity.json"
    existing = [path for path in (classification_path, property_path, audit_path) if path.exists()]
    if existing:
        raise FileExistsError(
            "E5 outputs already exist; refusing to overwrite possible human work: "
            + ", ".join(str(path) for path in existing)
        )

    original_rows, _fields = load_review_csv(title_review_csv)
    candidates, dataset, targets, duplicate_pairs = _candidate_rows_read_only(pilot_db)
    source_contexts = _source_contexts_read_only(
        pilot_db, str(dataset["revision"]), original_rows
    )
    classification_rows = _classification_packet_rows(
        original_rows, str(dataset["revision"]), source_contexts
    )
    property_rows = _property_review_rows(candidates, str(dataset["revision"]))
    sensitivity = _sensitivity_report(candidates, targets, duplicate_pairs)
    classification_summary = {
        "row_count": len(classification_rows),
        "prediction_distribution": dict(
            sorted(Counter(row["predicted_classification"] for row in classification_rows).items())
        ),
        "already_human_labeled": sum(bool(row["human_label"]) for row in classification_rows),
        "missing_human_labels": sum(not row["human_label"] for row in classification_rows),
        "rule_confidence_available": False,
        "baseline_version": E4_RULE_VERSION,
        "source_context_rows_found": len(source_contexts),
    }
    property_summary = {
        "row_count": len(property_rows),
        "e4_property_type_distribution": dict(
            sorted(Counter(row["e4_property_type"] for row in property_rows).items())
        ),
        "review_reason_counts": dict(
            sorted(
                Counter(
                    reason
                    for row in property_rows
                    for reason in row["property_review_reason"].split(";")
                ).items()
            )
        ),
        "human_labels_present": 0,
    }
    report = {
        "phase": "E5_PREPARATION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_revision": dataset["revision"],
        "pilot_database": str(pilot_db.resolve()),
        "classification_review_csv": str(classification_path.resolve()),
        "property_review_csv": str(property_path.resolve()),
        "classification_review": classification_summary,
        "property_review": property_summary,
        "historical_quality": sensitivity,
        "safety": {
            "network_attempted": False,
            "production_database_written": False,
            "demo_database_written": False,
            "pilot_database_written": False,
            "human_labels_generated": False,
            "source_verification_performed": False,
        },
        "next_step": "Human reviewer completes the two CSVs; evaluation runs only after labels are returned and validated.",
    }
    _write_csv(classification_path, classification_rows, CLASSIFICATION_PACKET_COLUMNS)
    _write_csv(property_path, property_rows, PROPERTY_PACKET_COLUMNS)
    _write_json(audit_path, report)
    report["audit_json"] = str(audit_path.resolve())
    return report


def validate_property_review_csv(path: Path) -> dict[str, Any]:
    required = {
        "candidate_id",
        "source_row_id",
        "e4_property_type",
        "human_property_label",
        "review_status",
    }
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"Property review CSV is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    seen = set()
    labels = Counter()
    reviewed = 0
    for row_number, row in enumerate(rows, start=2):
        row_id = (row.get("source_row_id") or "").strip()
        if not row_id or row_id in seen:
            raise ValueError(f"Missing or duplicate source_row_id on property CSV row {row_number}")
        seen.add(row_id)
        label = (row.get("human_property_label") or "").strip().upper()
        status = (row.get("review_status") or "").strip().upper()
        if label and label not in PROPERTY_LABELS:
            raise ValueError(
                f"Invalid human_property_label on CSV row {row_number}: {label!r}; "
                f"expected one of {', '.join(PROPERTY_LABELS)}"
            )
        if status not in {"NOT_REVIEWED", "REVIEWED"}:
            raise ValueError(f"Invalid review_status on property CSV row {row_number}: {status!r}")
        if status == "REVIEWED" and not label:
            raise ValueError(f"Property CSV row {row_number} is REVIEWED but has no human label")
        if label and status != "REVIEWED":
            raise ValueError(f"Property CSV row {row_number} has a label but is not marked REVIEWED")
        labels[label] += bool(label)
        reviewed += status == "REVIEWED"
    return {
        "row_count": len(rows),
        "reviewed_count": reviewed,
        "unreviewed_count": len(rows) - reviewed,
        "human_label_distribution": dict(sorted((key, value) for key, value in labels.items() if key)),
        "metrics_available": False,
        "source_verified_count": 0,
    }
