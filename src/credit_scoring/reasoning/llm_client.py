"""Provider adapters for structured alternative-data reasoning."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from credit_scoring.reasoning.schemas import CLASSIFICATIONS, CONFIDENCES

REASONING_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": list(CLASSIFICATIONS)},
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
        "positive_evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
        "negative_evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
        "conflicts": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
        "rules_used": {"type": "array", "items": {"type": "string"}},
        "unsupported_information": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "classification",
        "confidence",
        "positive_evidence",
        "negative_evidence",
        "conflicts",
        "rules_used",
        "unsupported_information",
        "missing_information",
        "reasoning_summary",
    ],
    "$defs": {
        "evidence": {
            "type": "object",
            "properties": {"feature": {"type": "string"}, "value": {}},
            "required": ["feature", "value"],
            "additionalProperties": False,
        }
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LLMClientConfig:
    provider: str
    model: str
    api_key_env: str


class StructuredLLMReasoner:
    """Small adapter around OpenAI-compatible clients.

    `openrouter` can route to GPT, Claude or Gemini models. Native Gemini API is
    deliberately not claimed here; use an OpenRouter Gemini model until a
    separately approved SDK adapter is added.
    """

    def __init__(self, config: LLMClientConfig, *, client: Any) -> None:
        self.config = config
        self.client = client

    def complete(self, prompt: str) -> Mapping[str, Any]:
        system = (
            "Bạn là trợ lý reasoning tín dụng thận trọng và phải viết nội dung diễn giải "
            "bằng tiếng Việt. Chỉ trả về object JSON được yêu cầu và chỉ sử dụng feature "
            "cùng rule ID đã cung cấp. Phân biệt hành vi thanh toán với kết quả tín dụng "
            "chính thức, giữ nguyên thông tin thiếu, không bịa ngưỡng hoặc quan hệ nhân quả. "
            "Các giá trị enum classification và confidence phải giữ đúng schema tiếng Anh."
        )
        if self.config.provider == "openrouter":
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "alternative_data_reasoning",
                        "strict": True,
                        "schema": REASONING_OUTPUT_JSON_SCHEMA,
                    },
                },
                extra_body={"provider": {"require_parameters": True}},
            )
            content = response.choices[0].message.content
        elif self.config.provider == "openai":
            response = self.client.responses.create(
                model=self.config.model,
                store=False,
                instructions=system,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "alternative_data_reasoning",
                        "strict": True,
                        "schema": REASONING_OUTPUT_JSON_SCHEMA,
                    }
                },
            )
            content = response.output_text
        else:
            raise ValueError(f"Unsupported reasoning LLM provider: {self.config.provider}")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned an empty reasoning response.")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned invalid JSON despite structured output mode.") from exc
        if not isinstance(payload, Mapping):
            raise TypeError("LLM reasoning response must be a JSON object.")
        return payload


def create_reasoner_from_environment(
    *,
    client: Any | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> StructuredLLMReasoner | None:
    """Create an adapter from environment variables without exposing secrets.

    Configuration:
    - `REASONING_LLM_PROVIDER=openai` with `OPENAI_API_KEY`;
    - `REASONING_LLM_PROVIDER=openrouter` with `OPENROUTER_API_KEY`;
    - `REASONING_LLM_MODEL` overrides the provider default.
    """

    resolved_provider = (provider or os.getenv("REASONING_LLM_PROVIDER", "")).strip().lower()
    if not resolved_provider:
        resolved_provider = "openrouter" if os.getenv("OPENROUTER_API_KEY") else "openai"
    if resolved_provider == "openrouter":
        api_key_env = "OPENROUTER_API_KEY"
        resolved_model = model or os.getenv(
            "REASONING_LLM_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        )
    elif resolved_provider == "openai":
        api_key_env = "OPENAI_API_KEY"
        resolved_model = model or os.getenv(
            "REASONING_LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")
        )
    else:
        raise ValueError("REASONING_LLM_PROVIDER must be openai or openrouter.")
    if not os.getenv(api_key_env):
        return None
    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError('Install the web extra: pip install -e ".[web]"') from exc
        client = (
            OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ[api_key_env],
                default_headers={"X-OpenRouter-Title": "Alternative Data Reasoning"},
            )
            if resolved_provider == "openrouter"
            else OpenAI(api_key=os.environ[api_key_env])
        )
    return StructuredLLMReasoner(
        LLMClientConfig(provider=resolved_provider, model=resolved_model, api_key_env=api_key_env),
        client=client,
    )
