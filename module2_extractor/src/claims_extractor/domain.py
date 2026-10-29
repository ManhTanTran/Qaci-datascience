"""Contract a domain (real estate, later others) must fulfil to plug into the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import AnswerRecord


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of processing one raw claim emitted by the LLM."""

    stored: dict[str, Any] | None = None
    rejected: dict[str, Any] | None = None


# (raw LLM claim, source answer, normalized answer text) -> ClaimResult
ClaimProcessor = Callable[[dict[str, Any], AnswerRecord, str], ClaimResult]


# answer text -> reason string when the answer needs no LLM call (e.g. "no result found")
Precheck = Callable[[str], "str | None"]
# raw answer text -> text sent to the LLM and used for quote checks
Preprocess = Callable[[str], str]


@dataclass(frozen=True)
class Domain:
    name: str
    system_prompt: str
    process_claim: ClaimProcessor
    csv_columns: list[str] = field(default_factory=list)
    version: str = "1"  # bump by hand when verification logic changes (prompt edits are hashed)
    precheck: Precheck | None = None
    preprocess: Preprocess | None = None
