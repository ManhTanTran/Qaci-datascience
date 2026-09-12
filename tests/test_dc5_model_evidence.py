from __future__ import annotations

import json

import pandas as pd

from credit_scoring.dc5.model_evidence import load_latest_model_evidence


def test_load_latest_model_evidence_selects_best_result_without_customer_rows(tmp_path) -> None:
    output_dir = tmp_path / "artifacts"
    run_dir = output_dir / "runs" / "run-123"
    run_dir.mkdir(parents=True)
    (output_dir / "latest.json").write_text(
        json.dumps({"run_dir": str(run_dir), "report_path": str(run_dir / "report.html")}),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": "run-123",
                "config": {"model": {"backend": "catboost"}},
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "setting": "With City",
                "model": "M1",
                "roc_auc": 0.68,
                "pr_auc": 0.32,
                "positive_rate": 0.18,
            },
            {
                "setting": "No City",
                "model": "M4",
                "roc_auc": 0.69,
                "pr_auc": 0.33,
                "positive_rate": 0.18,
            },
        ]
    ).to_csv(run_dir / "metrics.csv", index=False)
    pd.DataFrame(
        [
            {"setting": "No City", "model": "M4", "feature": "telco_a", "importance": 60},
            {"setting": "No City", "model": "M4", "feature": "telco_b", "importance": 40},
            {"setting": "With City", "model": "M1", "feature": "city", "importance": 100},
        ]
    ).to_csv(run_dir / "feature_importance.csv", index=False)

    evidence = load_latest_model_evidence(output_dir)

    assert evidence is not None
    assert evidence.backend == "catboost"
    assert evidence.model_name == "M4"
    assert evidence.setting == "No City"
    assert evidence.roc_auc == 0.69
    assert [item.feature for item in evidence.top_features] == ["telco_a", "telco_b"]
    assert evidence.inference_available is False
    assert "user" not in str(evidence.to_dict()).lower()


def test_load_latest_model_evidence_returns_none_without_run(tmp_path) -> None:
    assert load_latest_model_evidence(tmp_path / "missing") is None
