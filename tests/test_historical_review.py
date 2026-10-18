import csv

import pytest

from wardprice.historical_review import (
    evaluate_review_rows,
    label_unreviewed_rows,
    review_summary,
)


def _write_review(path, rows):
    fields = [
        "source_row_index",
        "target_rank",
        "title",
        "predicted_classification",
        "human_label",
        "review_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_blank_human_labels_do_not_produce_classifier_metrics(tmp_path):
    path = tmp_path / "review.csv"
    _write_review(
        path,
        [
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "human_label": "",
                "review_notes": "",
            },
            {
                "source_row_index": "2",
                "target_rank": "1",
                "title": "Cho thuê căn hộ",
                "predicted_classification": "RENT_CONFIRMED_BY_TEXT",
                "human_label": "",
                "review_notes": "",
            },
        ],
    )

    result = review_summary(path)

    assert result["review_row_count"] == 2
    assert result["human_labeled_count"] == 0
    assert result["unlabeled_count"] == 2
    assert result["metrics_available"] is False
    assert result["confusion_matrix"] is None
    assert result["macro_f1"] is None
    assert result["coverage"] is None
    assert result["abstention_rate"] is None


def test_metrics_use_only_human_labeled_rows_and_report_abstention():
    result = evaluate_review_rows(
        [
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "human_label": "SALE",
            },
            {
                "source_row_index": "2",
                "target_rank": "1",
                "title": "Chờ bán hoặc cho thuê",
                "predicted_classification": "CONFLICT",
                "human_label": "SALE",
            },
            {
                "source_row_index": "3",
                "target_rank": "1",
                "title": "Cần tìm nhà",
                "predicted_classification": "AMBIGUOUS",
                "human_label": "INSUFFICIENT_INFORMATION",
            },
            {
                "source_row_index": "4",
                "target_rank": "1",
                "title": "Bỏ trống",
                "predicted_classification": "RENT_CONFIRMED_BY_TEXT",
                "human_label": "",
            },
        ]
    )

    assert result["human_labeled_count"] == 3
    assert result["unlabeled_count"] == 1
    assert result["metrics_available"] is True
    assert result["confusion_matrix"]["SALE"]["SALE"] == 1
    assert result["confusion_matrix"]["SALE"]["CONFLICT"] == 1
    assert result["coverage"] == pytest.approx(1 / 3)
    assert result["abstention_rate"] == pytest.approx(2 / 3)
    assert len(result["misclassified_records"]) == 2


def test_interactive_labeling_only_fills_blank_rows_and_preserves_existing_labels(tmp_path):
    path = tmp_path / "review.csv"
    _write_review(
        path,
        [
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "human_label": "RENT",
                "review_notes": "Đã gắn nhãn trước đó",
            },
            {
                "source_row_index": "2",
                "target_rank": "1",
                "title": "Cho thuê căn hộ",
                "predicted_classification": "RENT_CONFIRMED_BY_TEXT",
                "human_label": "",
                "review_notes": "",
            },
        ],
    )
    answers = iter(["2"])

    result = label_unreviewed_rows(path, input_fn=lambda _prompt: next(answers), output_fn=lambda _text: None)

    assert result["human_labels_added"] == 1
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["human_label"] == "RENT"
    assert rows[0]["review_notes"] == "Đã gắn nhãn trước đó"
    assert rows[1]["human_label"] == "RENT"


def test_invalid_human_label_is_rejected(tmp_path):
    path = tmp_path / "review.csv"
    _write_review(
        path,
        [
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "human_label": "AI_SAYS_SALE",
                "review_notes": "",
            }
        ],
    )
    with pytest.raises(ValueError, match="Invalid human_label"):
        review_summary(path)


def test_e5_template_requires_review_status_and_keeps_population_claim_off(tmp_path):
    path = tmp_path / "e5-review.csv"
    fields = [
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
        "human_label",
        "reviewer_notes",
        "review_status",
        "sampling_stratum",
        "review_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "source_row_index": "7",
                "source_shard": "0000.parquet",
                "target_rank": "11",
                "title": "Bán hoặc cho thuê căn hộ",
                "predicted_classification": "CONFLICT",
                "e4_rule_version": "E4",
                "rule_predicted_label": "CONFLICT",
                "human_label": "",
                "review_status": "NOT_REVIEWED",
            }
        )

    result = review_summary(path)

    assert result["human_labeled_count"] == 0
    assert result["metrics_available"] is False
    assert result["macro_f1"] is None
    assert result["sampling_strategy"] == "REVIEW_SET_ONLY_SAMPLING_DESIGN_NOT_ESTABLISHED"
    assert result["representative_of_full_candidate_population"] is False
    assert result["weighted_metrics_available"] is False
    assert result["confidence_intervals"] is None


def test_e5_rejects_mutated_frozen_prediction_and_inconsistent_status(tmp_path):
    path = tmp_path / "e5-review.csv"
    fields = [
        "source_row_index",
        "target_rank",
        "title",
        "predicted_classification",
        "rule_predicted_label",
        "human_label",
        "review_status",
        "review_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "rule_predicted_label": "RENT",
                "human_label": "",
                "review_status": "NOT_REVIEWED",
                "review_notes": "",
            }
        )
    with pytest.raises(ValueError, match="Frozen E4 prediction mismatch"):
        review_summary(path)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "source_row_index": "1",
                "target_rank": "1",
                "title": "Bán nhà",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "rule_predicted_label": "SALE",
                "human_label": "SALE",
                "review_status": "NOT_REVIEWED",
                "review_notes": "",
            }
        )
    with pytest.raises(ValueError, match="has a human_label"):
        review_summary(path)


def test_e5_error_analysis_only_uses_reviewed_rows_and_keeps_sample_scope():
    result = evaluate_review_rows(
        [
            {
                "source_row_index": "8",
                "target_rank": "11",
                "title": "Cần bán hoặc cho thuê căn hộ, ví dụ giả định",
                "predicted_classification": "SALE_CONFIRMED_BY_TEXT",
                "rule_predicted_label": "SALE",
                "e4_rule_version": "E4",
                "human_label": "RENT",
                "review_status": "REVIEWED",
                "source_property_type_name": "Nhà",
                "source_project_name": "Dự án giả định",
                "source_price_present": "true",
            },
            {
                "source_row_index": "9",
                "target_rank": "11",
                "title": "Căn hộ 60 m²",
                "predicted_classification": "RENT_CONFIRMED_BY_TEXT",
                "rule_predicted_label": "RENT",
                "e4_rule_version": "E4",
                "human_label": "",
                "review_status": "NOT_REVIEWED",
            },
        ]
    )

    assert result["human_labeled_count"] == 1
    assert result["macro_f1"] is not None
    assert result["baseline_version"] == "E4"
    assert result["population_accuracy_estimate_available"] is False
    assert result["error_analysis"]["sale_predicted_as_rent"] == 1
    assert result["error_analysis"]["mistakes_with_both_sale_and_rent_title_cues"] == 1
    assert result["error_analysis"]["mistakes_with_price_field_but_no_transaction_title_cue"] == 0
    assert result["error_analysis"]["mistakes_with_property_type_cue_conflict"] == 1
    assert result["misclassified_records"][0]["source_project_name"] == "Dự án giả định"
