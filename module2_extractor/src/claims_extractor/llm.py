"""LLM access behind a tiny interface, so the pipeline never depends on a vendor SDK."""

from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    name: str
    # Optional: after each `complete`, clients may set `last_usage` = {"prompt_tokens": int,
    # "completion_tokens": int} (None when the endpoint reports nothing). Used for cost logging.
    last_usage: dict[str, int] | None

    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text reply (expected to be a JSON object)."""
        ...


class OpenAICompatibleClient:
    """Works with OpenAI and any OpenAI-compatible endpoint (set OPENAI_BASE_URL)."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the LLM extra: pip install 'claims-extractor[openai]'") from exc
        self.name = model
        self.last_usage: dict[str, int] | None = None
        self._temperature = temperature
        self._client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=timeout,
        )

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.name,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = getattr(response, "usage", None)
        self.last_usage = (
            {"prompt_tokens": int(usage.prompt_tokens or 0),
             "completion_tokens": int(usage.completion_tokens or 0)}
            if usage is not None else None
        )
        return response.choices[0].message.content or ""
