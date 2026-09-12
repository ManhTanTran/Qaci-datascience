import pandas as pd
from fastapi.testclient import TestClient

from credit_scoring.dc5.api import _admin_payload, app
from credit_scoring.dc5.pipeline import PipelineRun


def test_admin_report_only_returns_validation_error_without_artifact(tmp_path) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/admin/runs",
        json={"mode": "report-only", "output_dir": str(tmp_path / "missing")},
    )
    assert response.status_code == 422
    assert "No previous DC5 run" in response.json()["detail"]


def test_admin_payload_contains_dashboard_pages(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "report.html").write_text("report", encoding="utf-8")
    pd.DataFrame([{"feature": "age", "missing_pct": 2.0}]).to_csv(
        run_dir / "feature_missingness.csv", index=False
    )
    pd.DataFrame([{"domain": "telco", "coverage_pct": 90.0}]).to_csv(
        run_dir / "domain_coverage.csv", index=False
    )
    payload = _admin_payload(
        PipelineRun(
            report_path=run_dir / "report.html",
            run_dir=run_dir,
            metrics=pd.DataFrame([{"model": "M0", "roc_auc": 0.5}]),
            cached=True,
        )
    )
    assert payload["missingness"][0]["feature"] == "age"
    assert payload["domain_coverage"][0]["domain"] == "telco"
    assert payload["cluster_sizes"] == []
    assert payload["model_catalog"][1]["parent"] == "M0"
