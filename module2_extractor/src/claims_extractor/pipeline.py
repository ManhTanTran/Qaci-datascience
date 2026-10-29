"""Module 2 batch processing: claim answers from the queue, extract, verify, store.

`process_pending` is the interface the runner calls (code_plan.md §9). `run_pipeline` keeps the
simple "one file in, claims out" behaviour used by the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .extract import Extractor
from .ingest import IngestResult, ingest_file
from .models import ExtractionOutput
from .store import ClaimStore, utcnow


@dataclass
class RunSummary:
    processed: int = 0
    skipped: int = 0
    ok: int = 0
    empty: int = 0
    failed: int = 0
    claims: int = 0
    rejected: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_missing_calls: int = 0
    stopped: bool = False
    registered: int = 0
    invalid_lines: int = 0
    invalid_inputs: list[str] = field(default_factory=list)

    def add(self, output: ExtractionOutput) -> None:
        self.processed += 1
        self.claims += len(output.claims)
        self.rejected += len(output.rejected)
        self.llm_calls += output.llm_calls
        self.prompt_tokens += output.prompt_tokens
        self.completion_tokens += output.completion_tokens
        self.usage_missing_calls += output.usage_missing_calls
        setattr(self, output.extract_status, getattr(self, output.extract_status) + 1)


def process_pending(
    store: ClaimStore,
    extractor: Extractor,
    *,
    limit: int | None = None,
    batch_size: int = 20,
    max_attempts: int = 3,
    retry_failed: bool = True,
    retry_backoff_s: float = 0.0,
    should_stop: Callable[[], bool] | None = None,
    on_result: Callable[[ExtractionOutput], None] | None = None,
    on_batch: Callable[[RunSummary], None] | None = None,
) -> RunSummary:
    """Work through the queue sequentially, `batch_size` answers at a time.

    Each answer is saved in its own transaction, so stopping anywhere loses at most the answer
    in flight (it is returned to `pending` by `recover_interrupted`). `limit` caps answers
    handled in this call; `should_stop` is checked between answers (graceful stop).

    Answers that fail in this call are not re-claimed within the same call; they wait for the
    next call, so a flaky endpoint cannot spin on one answer.
    """
    summary = RunSummary()
    run_started = utcnow()
    retry_cutoff = (
        (datetime.now(timezone.utc) - timedelta(seconds=retry_backoff_s)).isoformat(timespec="microseconds")
        if retry_backoff_s > 0 else None
    )
    while limit is None or summary.processed < limit:
        if should_stop and should_stop():
            summary.stopped = True
            break
        take = batch_size if limit is None else min(batch_size, limit - summary.processed)
        batch = store.claim_batch(take, max_attempts=max_attempts, retry_failed=retry_failed,
                                  not_tried_since=run_started,
                                  retry_not_before=retry_cutoff)
        if not batch:
            break
        for index, answer in enumerate(batch):
            if should_stop and should_stop():
                summary.stopped = True
                _release(store, batch[index:])
                break
            output = extractor.extract(answer)
            store.save(answer, output)
            summary.add(output)
            if on_result:
                on_result(output)
        if on_batch:
            on_batch(summary)
        if summary.stopped:
            break
    return summary


def _release(store: ClaimStore, answers) -> None:
    """Give claimed-but-untouched answers back (graceful stop); the attempt is not consumed."""
    ids = [a.answer_id for a in answers]
    if ids:
        store.unclaim(ids)


def run_pipeline(
    input_path: str | Path,
    store: ClaimStore,
    extractor: Extractor,
    *,
    force: bool = False,
    limit: int | None = None,
    on_result: Callable[[ExtractionOutput], None] | None = None,
) -> RunSummary:
    """Ingest the file, then process what is pending. `force` re-queues everything first."""
    ingest: IngestResult = ingest_file(store, input_path)
    if force:
        store.mark_pending(statuses=("ok", "empty", "failed"))
    summary = process_pending(store, extractor, limit=limit, on_result=on_result)
    summary.registered = ingest.registered
    summary.skipped = ingest.duplicates
    summary.invalid_lines = ingest.invalid
    return summary
