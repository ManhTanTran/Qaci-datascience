"""Operations facade used by the UI and the CLI: status, quality, actions.

Long actions (a run) execute on a background thread so the UI stays responsive; progress is
read from `Runner.state`. All durable facts come from SQLite, so a UI opened in another process
still shows the truth (including a run started by `python -m pipeline watch`).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claims_extractor import stats
from claims_extractor.export import export_csv, export_jsonl
from claims_extractor.ingest import ingest_file  # noqa: F401  (re-exported for tests)
from common.config import Config

from .runner import Runner, WorkerBusy

log = logging.getLogger("pipeline.service")


class OpsService:
    def __init__(self, config: Config, runner: Runner | None = None) -> None:
        self.config = config
        self.runner = runner or Runner(config)
        self._auto_thread: threading.Thread | None = None
        self._auto_stop = threading.Event()
        self._run_thread: threading.Thread | None = None
        self._auto_requested = config.auto

    # ---- lifecycle ----------------------------------------------------------------

    def start(self) -> None:
        if self.config.auto:
            self.set_auto(True)

    def shutdown(self) -> None:
        self._auto_stop.set()
        self.runner.state.request_stop()

    # ---- actions ------------------------------------------------------------------

    def run_async(self, trigger: str = "ui", *, limit: int | None = None, rescan: bool = False) -> dict:
        """Start a run on a background thread. Raises WorkerBusy if one is active anywhere."""
        with self.runner.open_store() as store:
            info = store.lock_info()
        if self.runner.state.progress.running or (self._run_thread and self._run_thread.is_alive()):
            raise WorkerBusy("Đang có một lượt xử lý chạy.")
        if info and not _is_ours(info, self.runner):
            raise WorkerBusy(f"Tiến trình khác đang xử lý (pid {info.get('pid')}).")

        self.runner.state.begin(trigger)  # visible to the UI immediately, before the thread starts

        def target() -> None:
            try:
                self.runner.run_once(trigger, limit=limit, rescan=rescan)
            except WorkerBusy as busy:
                log.info("run skipped: %s", busy)
                self.runner.state.end("skipped", str(busy))
            except Exception as exc:  # noqa: BLE001
                log.exception("background run crashed")
                self.runner.state.end("failed", f"{type(exc).__name__}")

        self._run_thread = threading.Thread(target=target, name="pipeline-run", daemon=True)
        self._run_thread.start()
        return {"started": True, "limit": limit}

    def stop_run(self) -> dict:
        self.runner.state.request_stop()
        return {"stop_requested": True}

    def retry_failed(self, *, run: bool = True) -> dict:
        with self.runner.open_store() as store:
            n = store.mark_pending(statuses=["failed"], reset_attempts=True)
        return {"requeued": n, "started": self._try_start("ui-retry") if run and n else False}

    def reprocess(self, *, statuses: list[str] | None = None, answer_ids: list[str] | None = None,
                  target_month: str | None = None, crawl_run_id: str | None = None,
                  stale: bool = False, run: bool = True) -> dict:
        if not any([statuses, answer_ids, target_month, crawl_run_id, stale]):
            raise ValueError("Chọn ít nhất một điều kiện để xử lý lại (trạng thái, mã, tháng, lượt crawl hoặc bản cũ).")
        with self.runner.open_store() as store:
            n = store.mark_pending(
                statuses=statuses or (), answer_ids=answer_ids or (), target_month=target_month,
                crawl_run_id=crawl_run_id,
                stale_version=self.runner.extractor_version() if stale else None)
        return {"requeued": n, "started": self._try_start("ui-reprocess") if run and n else False}

    def _try_start(self, trigger: str) -> bool:
        """Start a run if the worker is free; otherwise the active run picks the queue up."""
        try:
            self.run_async(trigger)
            return True
        except WorkerBusy:
            return False

    def set_auto(self, enabled: bool) -> dict:
        if enabled and not (self._auto_thread and self._auto_thread.is_alive()):
            self._auto_stop = threading.Event()
            self._auto_thread = threading.Thread(
                target=self.runner.watch, args=(self._auto_stop,), name="pipeline-watch", daemon=True)
            self._auto_thread.start()
        elif not enabled:
            self._auto_stop.set()
        self._auto_requested = enabled
        return {"auto": self.auto_running()}

    def auto_running(self) -> bool:
        return bool(self._auto_thread and self._auto_thread.is_alive() and not self._auto_stop.is_set())

    def export(self, fmt: str, target_month: str | None = None) -> Path:
        if fmt not in {"csv", "jsonl"}:
            raise ValueError("Định dạng phải là csv hoặc jsonl.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"claims_{target_month or 'all'}_{stamp}.{fmt}"
        out = self.config.export_dir / name
        with self.runner.open_store() as store:
            writer = export_csv if fmt == "csv" else export_jsonl
            # month filter: iterate through a thin wrapper store view
            if target_month:
                writer(_MonthView(store, target_month), self.runner.domain, out)
            else:
                writer(store, self.runner.domain, out)
        return out

    # ---- reads --------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        cfg = self.config
        path = cfg.input_file
        with self.runner.open_store() as store:
            state = store.get_ingest_state(str(path))
            lock = store.lock_info()
            ov = stats.overview(store, max_attempts=cfg.processing.max_retries)
            last_runs = stats.list_runs(store, 1)
        file_info: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
        if path.is_file():
            st = path.stat()
            offset = state["byte_offset"] if state and path.suffix.lower() == ".jsonl" else None
            file_info.update(
                size=st.st_size,
                modified_at=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                scanned_bytes=offset,
                unscanned_bytes=(st.st_size - offset) if offset is not None else None,
            )
        owned = bool(lock and _is_ours(lock, self.runner))
        return {
            "mode": cfg.mode,
            "auto_running": self.auto_running(),
            "allow_mode_switch": cfg.ui.allow_mode_switch,
            "input_file": file_info,
            "database_file": str(cfg.database_file),
            "worker": {
                "lock": lock, "ours": owned,
                "busy_elsewhere": bool(lock and not owned),
                "progress": self.runner.state.progress.snapshot(),
            },
            "extractor": {"model": cfg.llm.model, "version": self.runner.extractor_version()},
            "overview": ov,
            "last_run": last_runs[0] if last_runs else None,
            "processing": {
                "batch_size": cfg.processing.batch_size, "max_retries": cfg.processing.max_retries,
                "retry_failed": cfg.processing.retry_failed,
            },
        }

    def quality(self) -> dict[str, Any]:
        q = self.config.quality
        with self.runner.open_store() as store:
            return stats.quality(
                store, current_version=self.runner.extractor_version(),
                max_attempts=self.config.processing.max_retries,
                thresholds=stats.Thresholds(q.failed_rate, q.rejected_rate, q.flagged_rate,
                                            q.empty_rate, q.min_sample))


    def usage(self) -> dict[str, Any]:
        """Module 2 token usage and (if prices are configured) cost."""
        price = self.config.cost.module2
        with self.runner.open_store() as store:
            report = stats.usage_report(store, input_per_1m=price.input_per_1m,
                                        output_per_1m=price.output_per_1m)
        report["currency"] = self.config.cost.currency
        report["model"] = self.config.llm.model
        return report

    def module1_usage(self, period: str | None = None) -> dict[str, Any]:
        """Module 1 usage (Tavily searches + summary-model tokens) with configured prices."""
        from wardprice.research_answers import usage_summary

        price = self.config.cost.module1

        def priced(row: dict[str, Any]) -> dict[str, Any]:
            model = stats.cost_of(row.get("prompt_tokens", 0), row.get("completion_tokens", 0),
                                  price.model_input_per_1m, price.model_output_per_1m)
            search = (row.get("search_calls", 0) * price.search_per_call
                      if price.search_per_call is not None else None)
            parts = [v for v in (model, search) if v is not None]
            return {**row, "model_cost": model, "search_cost": search,
                    "cost": round(sum(parts), 6) if parts else None,
                    "cost_complete": model is not None and search is not None}

        data = usage_summary(period=period)
        return {
            "period": period, "currency": self.config.cost.currency,
            "total": priced(data["total"]),
            "by_period": [priced(r) for r in data["by_period"]],
            "by_run": [priced(r) for r in data["by_run"]],
            "prices_configured": any(v is not None for v in vars(price).values()),
        }


class _MonthView:
    """Minimal store view that filters `iter_claims` by month (for exports)."""

    def __init__(self, store, month: str) -> None:
        self._store, self._month = store, month

    def iter_claims(self, domain=None):
        return self._store.iter_claims(domain, target_month=self._month)


def _is_ours(lock: dict, runner: Runner) -> bool:
    return lock.get("owner") == runner._owner
