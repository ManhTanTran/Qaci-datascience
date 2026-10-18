"""Manual review and evaluation helpers for the historical title classifier."""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .national_registry import normalize_admin_name

HUMAN_LABELS = (
    "SALE",
    "RENT",
    "AMBIGUOUS",
    "CONFLICT",
    "INSUFFICIENT_INFORMATION",
)
PREDICTION_LABELS = {
    "SALE_CONFIRMED_BY_TEXT": "SALE",
    "RENT_CONFIRMED_BY_TEXT": "RENT",
    "AMBIGUOUS": "AMBIGUOUS",
    "CONFLICT": "CONFLICT",
}
REQUIRED_COLUMNS = {
    "source_row_index",
    "target_rank",
    "title",
    "predicted_classification",
    "human_label",
    "review_notes",
}
REVIEW_STATUSES = {"NOT_REVIEWED", "REVIEWED"}
BASELINE_CLASS_LABELS = {"SALE", "RENT", "AMBIGUOUS", "CONFLICT"}
E4_SALE_CUES = (
    "can ban",
    "chinh chu ban",
    "ban gap",
    "ban nha",
    "ban dat",
    "ban can ho",
    "ban chung cu",
    "ban biet thu",
    "ban shophouse",
    "chuyen nhuong",
    "sang nhuong",
)
E4_RENT_CUES = (
    "cho thue",
    "can thue",
    "chinh chu cho thue",
    "thue mat bang",
    "thue nha",
    "thue can ho",
)


def load_review_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - set(fields)
        if missing:
            raise ValueError(f"Review CSV is missing required columns: {', '.join(sorted(missing))}")
        rows = [dict(row) for row in reader]
    for row_number, row in enumerate(rows, start=2):
        label = (row.get("human_label") or "").strip().upper()
        if label and label not in HUMAN_LABELS:
            raise ValueError(
                f"Invalid human_label on CSV row {row_number}: {label!r}; "
                f"expected one of {', '.join(HUMAN_LABELS)}"
            )
        prediction = (row.get("predicted_classification") or "").strip()
        if prediction not in PREDICTION_LABELS:
            raise ValueError(f"Unsupported predicted_classification on CSV row {row_number}: {prediction!r}")
        baseline = (row.get("rule_predicted_label") or "").strip().upper()
        if baseline:
            if baseline not in BASELINE_CLASS_LABELS:
                raise ValueError(f"Unsupported rule_predicted_label on CSV row {row_number}: {baseline!r}")
            if baseline != PREDICTION_LABELS[prediction]:
                raise ValueError(
                    f"Frozen E4 prediction mismatch on CSV row {row_number}: "
                    f"rule_predicted_label={baseline!r}, predicted_classification={prediction!r}"
                )
        status = (row.get("review_status") or "").strip().upper()
        if status and status not in REVIEW_STATUSES:
            raise ValueError(
                f"Invalid review_status on CSV row {row_number}: {status!r}; "
                f"expected one of {', '.join(sorted(REVIEW_STATUSES))}"
            )
        if status == "REVIEWED" and not label:
            raise ValueError(f"CSV row {row_number} is REVIEWED but has no human_label")
        if label and status and status != "REVIEWED":
            raise ValueError(
                f"CSV row {row_number} has a human_label but review_status is {status!r}"
            )
        row["human_label"] = label
        row["review_status"] = status or ("REVIEWED" if label else "NOT_REVIEWED")
    return rows, fields


def _predicted_label(row: dict[str, str]) -> str:
    baseline = (row.get("rule_predicted_label") or "").strip().upper()
    if baseline:
        return baseline
    return PREDICTION_LABELS[row["predicted_classification"]]


def _title_cue_flags(title: str) -> dict[str, bool]:
    normalized = normalize_admin_name(title)
    has_sale = any(normalize_admin_name(cue) in normalized for cue in E4_SALE_CUES)
    has_rent = any(normalize_admin_name(cue) in normalized for cue in E4_RENT_CUES)
    return {
        "title_has_sale_cue": has_sale,
        "title_has_rent_cue": has_rent,
        "title_has_both_sale_and_rent_cues": has_sale and has_rent,
        "title_has_no_transaction_cue": not has_sale and not has_rent,
    }


def _title_property_cue_conflict(title: str, source_property_type: str) -> bool:
    normalized_title = normalize_admin_name(title)
    normalized_type = normalize_admin_name(source_property_type)
    has_apartment_cue = any(
        normalize_admin_name(cue) in normalized_title
        for cue in ("căn hộ", "chung cư", "apartment")
    )
    has_house_or_land_cue = any(
        normalize_admin_name(cue) in normalized_title
        for cue in ("nhà riêng", "nhà phố", "nhà mặt phố", "đất ở", "đất thổ cư")
    )
    return (
        normalized_type == normalize_admin_name("Nhà") and has_apartment_cue
    ) or (
        normalized_type == normalize_admin_name("Căn hộ chung cư") and has_house_or_land_cue
    )


def evaluate_review_rows(rows: list[dict[str, str]]) -> dict:
    predicted_counts = Counter(row["predicted_classification"] for row in rows)
    labeled = [
        row
        for row in rows
        if row.get("human_label", "").strip()
        and row.get("review_status", "REVIEWED").strip().upper() == "REVIEWED"
    ]
    human_counts = Counter(row["human_label"].strip().upper() for row in labeled)
    strata_counts = dict(sorted(predicted_counts.items()))
    balanced_e4_sample = len(rows) == 100 and all(
        predicted_counts.get(label, 0) == 25
        for label in PREDICTION_LABELS
    )
    result = {
        "review_row_count": len(rows),
        "prediction_distribution": dict(sorted(predicted_counts.items())),
        "sampling_strategy": (
            "BALANCED_BY_E4_PREDICTION_CLASS_25_PER_CLASS"
            if balanced_e4_sample
            else "REVIEW_SET_ONLY_SAMPLING_DESIGN_NOT_ESTABLISHED"
        ),
        "sampling_strata": strata_counts,
        "representative_of_full_candidate_population": False,
        "weighted_metrics_available": False,
        "population_accuracy_estimate_available": False,
        "baseline_version": "E4" if any(row.get("e4_rule_version") == "E4" for row in rows) else None,
        "human_label_distribution": dict(sorted(human_counts.items())),
        "human_labeled_count": len(labeled),
        "unlabeled_count": len(rows) - len(labeled),
        "metrics_available": bool(labeled),
        "confusion_matrix": None,
        "per_class": None,
        "macro_f1": None,
        "coverage": None,
        "abstention_rate": None,
        "misclassified_records": None,
        "error_analysis": None,
        "confidence_intervals": None,
        "confidence_interval_note": (
            "Not calculated: there are no independent human labels. The balanced review sample "
            "is not a probability sample of the full candidate population."
        ),
    }
    if not labeled:
        return result

    confusion = {actual: {predicted: 0 for predicted in HUMAN_LABELS} for actual in HUMAN_LABELS}
    mistakes = []
    covered = 0
    for row in labeled:
        actual = row["human_label"].strip().upper()
        predicted = _predicted_label(row)
        confusion[actual][predicted] += 1
        covered += predicted in {"SALE", "RENT"}
        if actual != predicted:
            mistakes.append(
                {
                    "source_row_index": row.get("source_row_index", ""),
                    "target_rank": row.get("target_rank", ""),
                    "title": row.get("title", ""),
                    "human_label": actual,
                    "predicted_label": predicted,
                    "title_cue_flags": _title_cue_flags(row.get("title", "")),
                    "title_type_cue_conflict": _title_property_cue_conflict(
                        row.get("title", ""), row.get("source_property_type_name", "")
                    ),
                    "source_property_type_name": row.get("source_property_type_name", ""),
                    "source_project_name": row.get("source_project_name", ""),
                    "source_street_name": row.get("source_street_name", ""),
                    "source_price_present": row.get("source_price_present", ""),
                    "source_area_present": row.get("source_area_present", ""),
                }
            )

    per_class = {}
    f1_values = []
    for label in HUMAN_LABELS:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[actual][label] for actual in HUMAN_LABELS if actual != label)
        false_negative = sum(confusion[label][predicted] for predicted in HUMAN_LABELS if predicted != label)
        support = true_positive + false_negative
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else None
        recall = true_positive / support if support else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else 0.0 if support else None
        )
        per_class[label] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        if support:
            f1_values.append(float(f1))

    abstentions = sum(
        PREDICTION_LABELS[row["predicted_classification"]] in {"AMBIGUOUS", "CONFLICT"}
        for row in labeled
    )
    result.update(
        {
            "confusion_matrix": confusion,
            "per_class": per_class,
            "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
            "coverage": covered / len(labeled),
            "abstention_rate": abstentions / len(labeled),
            "misclassified_records": mistakes,
            "error_analysis": {
                "sale_predicted_as_rent": sum(
                    item["human_label"] == "RENT" and item["predicted_label"] == "SALE"
                    for item in mistakes
                ),
                "rent_predicted_as_sale": sum(
                    item["human_label"] == "SALE" and item["predicted_label"] == "RENT"
                    for item in mistakes
                ),
                "mistakes_with_both_sale_and_rent_title_cues": sum(
                    item["title_cue_flags"]["title_has_both_sale_and_rent_cues"]
                    for item in mistakes
                ),
                "mistakes_with_no_transaction_title_cue": sum(
                    item["title_cue_flags"]["title_has_no_transaction_cue"]
                    for item in mistakes
                ),
                "mistakes_with_price_field_but_no_transaction_title_cue": sum(
                    item["source_price_present"] == "true"
                    and item["title_cue_flags"]["title_has_no_transaction_cue"]
                    for item in mistakes
                ),
                "mistakes_with_property_type_cue_conflict": sum(
                    item["title_type_cue_conflict"] for item in mistakes
                ),
                "reviewed_mistakes_only": True,
            },
            "confidence_interval_note": (
                "Not calculated: the selection is balanced by prediction class and is not a "
                "probability sample; any interval would not estimate full-population performance."
            ),
        }
    )
    return result


def review_summary(path: Path) -> dict:
    rows, _fields = load_review_csv(path)
    return evaluate_review_rows(rows)


def _write_review_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def label_unreviewed_rows(
    path: Path,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> dict:
    """Interactively label blank rows only; existing human labels are preserved."""
    rows, fields = load_review_csv(path)
    label_choices = {str(index): label for index, label in enumerate(HUMAN_LABELS, start=1)}
    changed = 0
    for row in rows:
        if row["human_label"]:
            continue
        output_fn(
            f"\n#{row.get('target_rank', '')} · row {row.get('source_row_index', '')}: "
            f"{row.get('title', '')}\n"
            "1 SALE | 2 RENT | 3 AMBIGUOUS | 4 CONFLICT | "
            "5 INSUFFICIENT_INFORMATION | Enter bỏ qua"
        )
        answer = input_fn("Nhãn: ").strip()
        if not answer:
            continue
        if answer not in label_choices:
            output_fn("Lựa chọn không hợp lệ; giữ nhãn trống để rà soát sau.")
            continue
        row["human_label"] = label_choices[answer]
        if "review_status" in row:
            row["review_status"] = "REVIEWED"
        changed += 1
        _write_review_csv(path, rows, fields)
    return {"human_labels_added": changed, **evaluate_review_rows(rows)}
