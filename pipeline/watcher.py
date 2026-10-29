"""Detect that the input file changed AND has stopped changing.

The watcher only answers "is it a good moment to wake the runner?". It never reads records:
a single write can produce many file-system events, and a file that is still growing must not
be read mid-write. Plain polling (size + mtime) is used because it behaves the same on Windows,
network drives and Docker volumes.
"""

from __future__ import annotations

from pathlib import Path


class InputWatcher:
    def __init__(self, path: Path, stable_checks: int = 2) -> None:
        self.path = Path(path)
        self.stable_checks = max(1, stable_checks)
        self._seen: tuple[int, int] | None = None   # signature of the last scan that was handed out
        self._candidate: tuple[int, int] | None = None
        self._streak = 0

    def _signature(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_size, stat.st_mtime_ns

    def poll(self) -> bool:
        """Call once per poll interval. True when the file differs from the last handled
        version and has kept the same signature for `stable_checks` consecutive polls."""
        signature = self._signature()
        if signature is None or signature == self._seen:
            self._candidate, self._streak = None, 0
            return False
        if signature == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = signature, 1
        return self._streak >= self.stable_checks

    def mark_handled(self) -> None:
        """Record the current version as processed (call after a scan)."""
        self._seen = self._signature()
        self._candidate, self._streak = None, 0
