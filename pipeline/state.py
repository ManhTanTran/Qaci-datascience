"""In-process run state: stop request + live progress shown by the UI.

Durable state (checkpoint offset, answer status, attempts, run history, the cross-process worker
lock) lives in SQLite — see claims_extractor.store. This object only covers the current process.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field


@dataclass
class Progress:
    running: bool = False
    trigger: str = ""
    phase: str = "idle"  # idle | scanning | extracting | finishing
    started_at: float | None = None
    target: int = 0  # answers this run intends to process (queue size when it started)
    processed: int = 0
    ok: int = 0
    empty: int = 0
    failed: int = 0
    claims: int = 0
    rejected: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    last_error: str | None = None
    last_finished_at: float | None = None
    last_status: str | None = None

    def snapshot(self) -> dict:
        data = asdict(self)
        data["elapsed_s"] = round(time.time() - self.started_at, 1) if self.running and self.started_at else None
        return data


@dataclass
class RunState:
    progress: Progress = field(default_factory=Progress)
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def request_stop(self) -> None:
        self._stop.set()

    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def begin(self, trigger: str) -> None:
        with self._lock:
            self._stop.clear()
            self.progress = Progress(running=True, trigger=trigger, phase="scanning",
                                     started_at=time.time())

    def end(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self.progress.running = False
            self.progress.phase = "idle"
            self.progress.last_status = status
            self.progress.last_error = error
            self.progress.last_finished_at = time.time()
