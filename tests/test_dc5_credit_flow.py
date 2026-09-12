from credit_scoring.dc5.credit_flow import _draft_rules, _pattern_payload
from credit_scoring.dc5.model_evidence import FeatureEvidence, ModelEvidence


def test_model_pattern_maps_only_declared_reasoning_features() -> None:
    evidence = ModelEvidence(
        run_id="run-1",
        backend="catboost",
        model_name="M4",
        setting="telco",
        model_description="test",
        target_definition="research target",
        roc_auc=0.7,
        pr_auc=0.3,
        positive_rate=0.2,
        top_features=(
            FeatureEvidence("active_domain_count_ord", 1.0),
            FeatureEvidence("telco_inbound_count_180d_ord", 0.9),
        ),
        inference_available=False,
        limitation="research only",
    )

    pattern = _pattern_payload(evidence)

    assert pattern["reasoning_feature_refs"] == ["active_domain_count"]


def test_llm_candidate_outside_registry_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "credit_scoring.dc5.credit_flow._call_rule_llm",
        lambda prompt: (
            {
                "rules": [
                    {
                        "title": "Unsupported feature draft",
                        "rule": "Review the observed signal before interpretation.",
                        "feature_refs": ["feature_outside_registry"],
                        "domains": ["engagement"],
                        "evidence_basis": "Aggregate research evidence.",
                        "limitation": "Candidate only; requires human review.",
                        "confidence": "low",
                    }
                ]
            },
            "openrouter",
            "test-model",
        ),
    )

    result = _draft_rules(
        {"status": "available", "reasoning_feature_refs": ["known_feature"]},
        known_features={"known_feature": {"domain": "engagement"}},
        use_llm=True,
    )

    assert result["status"] == "rejected_unknown_features"
    assert result["rules"] == []
    assert "feature_outside_registry" in result["note"]
