"""The data contract between module 1 and module 2 (one JSON object per line).

`AnswerRecord` is defined once, in module 2, and re-exported here so the runner/UI and the
tests share one definition. `compute_observation_answer_id` documents the id rule module 1
uses (module1_crawler/wardprice/research_answers.py::make_answer_id); a test keeps them equal.
"""

from __future__ import annotations

import hashlib

from claims_extractor.models import AnswerRecord, compute_answer_id  # noqa: F401  (re-export)

REQUIRED_FIELDS = ("crawled_at", "chatbot", "answer_text")
OPTIONAL_FIELDS = ("answer_id", "crawl_run_id", "target_month", "model_name", "query_text")


def compute_observation_answer_id(
    crawl_run_id: str, target_month: str, administrative_code: str, administrative_version: str
) -> str:
    """Id of one observation: same area, other month or other crawl run => different id."""
    digest = hashlib.sha256()
    for part in (crawl_run_id, target_month, administrative_code, administrative_version):
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:32]
