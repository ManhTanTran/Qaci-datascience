"""Domain-agnostic data models: phase-1 input record and phase-2 output record."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def compute_answer_id(
    chatbot: str,
    query_text: str,
    answer_text: str,
    crawl_run_id: str | None = None,
    target_month: str | None = None,
) -> str:
    """Fallback id for rows that arrive without `answer_id`.

    Content alone is NOT a safe key across months (the same question and answer repeated in a
    later month would look "already done"), so the run and the month are mixed in when known.
    Module 1 normally supplies its own `answer_id`; this is only the safety net.
    """
    digest = hashlib.sha256()
    parts = [chatbot, query_text, answer_text]
    if crawl_run_id or target_month:
        parts += [crawl_run_id or "", target_month or ""]
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:32]


class AnswerRecord(BaseModel):
    """One crawled chatbot answer (`llm_answers`, written by phase 1)."""

    model_config = ConfigDict(extra="ignore")

    answer_id: str = ""
    crawl_run_id: str | None = None  # groups answers of one crawl run
    target_month: str | None = None  # period the query asked about (YYYY-MM); NOT crawled_at
    crawled_at: datetime
    chatbot: str
    model_name: str | None = None
    query_text: str = ""
    answer_text: str = Field(min_length=1)

    @field_validator("answer_id", "query_text", mode="before")
    @classmethod
    def _null_means_empty(cls, value: Any) -> Any:
        return "" if value is None else value

    @model_validator(mode="after")
    def _check_and_fill(self) -> "AnswerRecord":
        if self.target_month is not None:
            self.target_month = self.target_month.strip() or None
        if self.target_month is not None and not _MONTH.fullmatch(self.target_month):
            raise ValueError("target_month must look like YYYY-MM")
        if not self.answer_id:
            self.answer_id = compute_answer_id(
                self.chatbot, self.query_text, self.answer_text,
                self.crawl_run_id, self.target_month,
            )
        return self


ExtractStatus = Literal["ok", "empty", "failed"]
# Lifecycle of a row in the store: pending -> processing -> ok | empty | failed
AnswerStatus = Literal["pending", "processing", "ok", "empty", "failed"]


class ExtractionOutput(BaseModel):
    """Phase-2 file content for one answer. Claims are plain dicts so any domain fits."""

    answer_id: str
    crawl_run_id: str | None = None
    target_month: str | None = None
    crawled_at: datetime
    chatbot: str
    model_name: str | None = None
    query_text: str = ""
    domain: str
    extract_status: ExtractStatus
    extractor_model: str
    prompt_hash: str
    extractor_version: str = ""
    extracted_at: datetime
    duration_ms: int | None = None
    llm_calls: int = 0  # complete() calls spent on this answer (a repair retry counts again)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_missing_calls: int = 0  # calls whose endpoint reported no token usage
    error: str | None = None
    note: str | None = None  # e.g. "no_result_declared": answered without calling the LLM
    claims: list[dict[str, Any]] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
