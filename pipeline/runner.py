"""The runner: the only place that reads the input file and drives module 2.

One run = scan the file (complete lines only) -> queue new answers -> process the queue in
batches -> write run log. At most one run executes at a time, across threads AND processes
(the lock row lives in SQLite), so the UI and `python -m pipeline watch` cannot collide.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from claims_extractor.domains import get_domain
from claims_extractor.extract import Extractor
from claims_extractor.ingest import ingest_file
from claims_extractor.llm import LLMClient, OpenAICompatibleClient
from claims_extractor.pipeline import RunSummary, process_pending
from claims_extractor.store import ClaimStore
from common.config import Config

from .state import RunState
from .watcher import InputWatcher

log = logging.getLogger("pipeline")

LOCK_STALE_SECONDS = 300  # > LLM timeout; a dead process's lock is taken over after this


class WorkerBusy(RuntimeError):
    """Another run (this process or another one) holds the single-worker lock."""


def build_llm(config: Config) -> LLMClient:
    """Create the extraction LLM from config + environment (keys are read from env only)."""
    if config.llm.provider != "openai":
        raise ValueError(f"unsupported llm.provider: {config.llm.provider!r}")
    api_key = os.environ.get(config.llm.api_key_env)
    base_url = os.environ.get(config.llm.base_url_env)
    if not api_key and config.llm.api_key_env != "OPENAI_API_KEY":
        # Single-provider setups: reuse the shared OPENAI_* pair when no dedicated key is set.
        api_key, base_url = os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_BASE_URL")
    if not api_key:
        raise RuntimeError(
            f"Thiếu API key: đặt {config.llm.api_key_env} (hoặc OPENAI_API_KEY) trong file .env."
        )
    return OpenAICompatibleClient(
        config.llm.model, api_key=api_key,
        base_url=base_url or None,
        temperature=config.llm.temperature, timeout=config.llm.timeout_seconds,
    )


class Runner:
    def __init__(self, config: Config, llm_factory: Callable[[Config], LLMClient] = build_llm) -> None:
        self.config = config
        self._llm_factory = llm_factory
        self.state = RunState()
        self._guard = threading.Lock()  # in-process: avoids two threads opening runs at once
        self._owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.domain = get_domain(config.domain)

    # ---- helpers ------------------------------------------------------------------

    def open_store(self) -> ClaimStore:
        return ClaimStore(self.config.database_file)

    def extractor_version(self) -> str:
        return Extractor(_NullLLM(), self.domain).version

    # ---- one run ------------------------------------------------------------------

    def run_once(
        self, trigger: str = "manual", *, limit: int | None = None, rescan: bool = False,
        retry_backoff: bool = False,
    ) -> dict:
        """Scan + process. Raises WorkerBusy if a run is already active anywhere."""
        if not self._guard.acquire(blocking=False):
            raise WorkerBusy("Đang có một lượt xử lý chạy trong tiến trình này.")
        store = self.open_store()
        try:
            if not store.acquire_lock(self._owner, stale_after_s=LOCK_STALE_SECONDS,
                                      activity=f"{trigger}: bắt đầu"):
                info = store.lock_info() or {}
                raise WorkerBusy(f"Tiến trình khác đang xử lý (pid {info.get('pid')}, {info.get('owner')}).")
            try:
                return self._run_locked(store, trigger, limit, rescan, retry_backoff)
            finally:
                store.release_lock(self._owner)
        finally:
            store.close()
            self._guard.release()

    def _run_locked(self, store: ClaimStore, trigger: str, limit: int | None, rescan: bool,
                    retry_backoff: bool) -> dict:
        cfg, started = self.config, time.monotonic()
        self.state.begin(trigger)
        progress = self.state.progress
        recovered = store.recover_interrupted()   # we hold the lock, so nothing is truly in flight
        store.close_dangling_runs()
        extractor_version = self.extractor_version()
        run_id = store.start_run(trigger, cfg.mode, str(cfg.input_file), extractor_version)
        counts = {"registered": 0, "invalid_lines": 0}
        summary = RunSummary()
        status, error = "completed", None
        try:
            ingest = ingest_file(store, cfg.input_file, rescan=rescan)
            counts = {"registered": ingest.registered, "invalid_lines": ingest.invalid}
            log.info("scan %s: new=%d dup=%d invalid=%d waiting_bytes=%d recovered=%d",
                     cfg.input_file.name, ingest.registered, ingest.duplicates, ingest.invalid,
                     ingest.waiting_bytes, recovered)
            if ingest.file_missing:
                log.warning("input file not found: %s", cfg.input_file)

            backoff = cfg.processing.retry_backoff_seconds if retry_backoff else 0.0
            workable = store.count_workable(
                max_attempts=cfg.processing.max_retries,
                retry_failed=cfg.processing.retry_failed)
            progress.target = workable if limit is None else min(workable, limit)
            if workable:
                progress.phase = "extracting"
                extractor = Extractor(self._llm_factory(cfg), self.domain)

                def on_result(output) -> None:
                    progress.processed += 1
                    progress.claims += len(output.claims)
                    progress.rejected += len(output.rejected)
                    progress.prompt_tokens += output.prompt_tokens
                    progress.completion_tokens += output.completion_tokens
                    setattr(progress, output.extract_status, getattr(progress, output.extract_status) + 1)
                    store.heartbeat(self._owner, f"{trigger}: {progress.processed}/{progress.target}")

                summary = process_pending(
                    store, extractor, limit=limit, batch_size=cfg.processing.batch_size,
                    max_attempts=cfg.processing.max_retries,
                    retry_failed=cfg.processing.retry_failed, retry_backoff_s=backoff,
                    should_stop=self.state.stop_requested, on_result=on_result,
                )
                log.info("processed=%d ok=%d empty=%d failed=%d claims=%d rejected=%d llm_calls=%d",
                         summary.processed, summary.ok, summary.empty, summary.failed,
                         summary.claims, summary.rejected, summary.llm_calls)
            status = "stopped" if summary.stopped else (
                "completed_with_errors" if summary.failed else "completed")
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            status, error = "failed", f"{type(exc).__name__}: {_redact(str(exc))}"
            log.error("run failed: %s", error)
        finally:
            store.finish_run(
                run_id, status, int((time.monotonic() - started) * 1000), error,
                processed=summary.processed, ok=summary.ok, empty=summary.empty,
                failed=summary.failed, claims=summary.claims, rejected=summary.rejected,
                llm_calls=summary.llm_calls, prompt_tokens=summary.prompt_tokens,
                completion_tokens=summary.completion_tokens,
                usage_missing_calls=summary.usage_missing_calls, **counts,
            )
            self.state.end(status, error)
        return {"run_id": run_id, "status": status, "error": error, **counts,
                "processed": summary.processed, "ok": summary.ok, "empty": summary.empty,
                "failed": summary.failed, "claims": summary.claims, "rejected": summary.rejected,
                "llm_calls": summary.llm_calls, "prompt_tokens": summary.prompt_tokens,
                "completion_tokens": summary.completion_tokens, "stopped": summary.stopped}

    # ---- auto mode ----------------------------------------------------------------

    def watch(self, stop: threading.Event) -> None:
        """Loop until `stop` is set: when the input file changed and is stable (or retryable
        work exists), run once. The watcher only wakes the runner; it never reads data."""
        cfg = self.config.processing
        watcher = InputWatcher(self.config.input_file, cfg.stable_file_checks)
        log.info("auto watcher started: %s (poll %.1fs, stable x%d)", self.config.input_file,
                 cfg.poll_interval_seconds, cfg.stable_file_checks)
        first = True
        cool_until = 0.0  # after a failed run (e.g. missing API key) wait before trying again
        while not stop.is_set():
            try:
                if time.monotonic() < cool_until:
                    stop.wait(cfg.poll_interval_seconds)
                    continue
                with self.open_store_ctx() as store:
                    backoff_due = _backoff_cutoff(cfg.retry_backoff_seconds)
                    retryable = store.count_workable(
                        max_attempts=cfg.max_retries, retry_failed=cfg.retry_failed,
                        retry_not_before=backoff_due)
                if first or watcher.poll() or retryable:
                    first = False
                    watcher.mark_handled()
                    try:
                        result = self.run_once("auto", retry_backoff=True)
                        if result["status"] == "failed":
                            cool_until = time.monotonic() + max(cfg.retry_backoff_seconds, 1)
                    except WorkerBusy as busy:
                        log.info("skipped: %s", busy)
                        watcher._seen = None  # try again next poll
            except Exception:  # noqa: BLE001 - the loop must survive anything
                log.exception("watch cycle failed")
            stop.wait(cfg.poll_interval_seconds)
        log.info("auto watcher stopped")

    def open_store_ctx(self) -> ClaimStore:
        return ClaimStore(self.config.database_file)


class _NullLLM:
    name = "null"

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - never called
        raise RuntimeError("not available")


def _backoff_cutoff(seconds: float) -> str | None:
    from datetime import datetime, timedelta, timezone
    if seconds <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def _redact(message: str) -> str:
    for name in ("EXTRACTOR_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, "[đã ẩn]")
    return message[:1000]


def setup_logging(config: Config) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if config.log_file:
        Path(config.log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(config.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers, force=True,
    )
