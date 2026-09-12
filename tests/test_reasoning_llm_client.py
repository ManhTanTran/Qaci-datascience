from __future__ import annotations

import json

import pytest

from credit_scoring.reasoning.llm_client import (
    LLMClientConfig,
    StructuredLLMReasoner,
    create_reasoner_from_environment,
)

VALID_OUTPUT = {
    "classification": "Mixed",
    "confidence": "Medium",
    "positive_evidence": [],
    "negative_evidence": [],
    "conflicts": [],
    "rules_used": [],
    "unsupported_information": [],
    "missing_information": [],
    "reasoning_summary": "Insufficient evidence for a stronger conclusion.",
}


class FakeChatCompletions:
    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return type(
            "Response",
            (),
            {"choices": [type("Choice", (), {"message": type("Message", (), {"content": json.dumps(VALID_OUTPUT)})()})()]},
        )()


class FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()


def test_openrouter_adapter_requests_strict_json_schema() -> None:
    client = FakeClient()
    reasoner = StructuredLLMReasoner(
        LLMClientConfig("openrouter", "google/gemini-2.5-flash", "OPENROUTER_API_KEY"),
        client=client,
    )
    assert reasoner.complete("payload") == VALID_OUTPUT
    assert client.chat.completions.kwargs["response_format"]["type"] == "json_schema"


def test_environment_factory_returns_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("REASONING_LLM_PROVIDER", raising=False)
    assert create_reasoner_from_environment() is None


def test_environment_factory_supports_injected_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONING_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-secret")
    reasoner = create_reasoner_from_environment(client=object())
    assert reasoner is not None
    assert reasoner.config.provider == "openai"


def test_environment_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONING_LLM_PROVIDER", "gemini-native")
    with pytest.raises(ValueError, match="openai or openrouter"):
        create_reasoner_from_environment()
