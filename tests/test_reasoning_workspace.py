from __future__ import annotations

import json
import zipfile

import pytest

from credit_scoring.reasoning.workspace import (
    assess_customer,
    load_reference_evaluations,
    load_workspace_catalog,
)


def test_workspace_catalog_exposes_real_registry_kb_and_three_cases() -> None:
    catalog = load_workspace_catalog()

    assert catalog["counts"]["features"] == len(catalog["features"])
    assert catalog["counts"]["rules"] == len(catalog["rules"])
    assert catalog["counts"]["scenarios"] == 3
    assert catalog["counts"]["rule_statuses"]["candidate"] == len(catalog["rules"])


def test_assessment_runs_detection_and_retrieval_without_llm() -> None:
    result = assess_customer(scenario_id="conflicting_signals", use_llm=False)

    assert result["llm_called"] is False
    assert result["output"] is None
    assert "payment" in result["detected_domains"]
    assert result["retrieved_rules"][0]["id"] == "RULE_PAY_001"


def test_assessment_requires_exactly_one_input() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        assess_customer(use_llm=False)


def test_reference_evaluation_reads_real_archive_text(tmp_path) -> None:
    archive_path = tmp_path / "simulate.zip"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "test-v1",
                "metrics_policy": "descriptive only",
                "scenarios": [],
                "runs": [
                    {
                        "run_id": "run-1",
                        "model": "GPT",
                        "turn": "one_shot",
                        "prompt_variant": "guided",
                        "response_file": "response.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "response.txt",
            "Customer 1 — **Mixed**\nCustomer 2 — **Potentially risky**\n"
            "Customer 3 — **Relatively stable**",
        )

    result = load_reference_evaluations(archive_path, manifest_path=manifest_path)

    assert result["runs"][0]["available"] is True
    assert result["runs"][0]["checks"]["coverage_complete"] is True
