"""SQLite store: the single system of record for answers, claims and processing state.

Tables
- answers        : one row per received answer; raw text kept for traceability and re-extraction.
                   `status` is the work queue: pending -> processing -> ok | empty | failed
- claims         : verified claims; domain-specific fields live in the `data` JSON column
- rejected       : claims the LLM produced but code refused (audit of prompt quality)
- claims_history : claims replaced by a later re-extraction (nothing is silently lost)
- input_errors   : input lines that could not be read (bad JSON, bad schema, id conflicts)
- ingest_state   : per input file checkpoint (byte offset of the last complete line)
- worker_lock    : one row; the single-worker guarantee, shared across processes
- run_log        : one row per processing run, for monitoring

SQLite fits one sequential writer, which is exactly what the runner provides.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import AnswerRecord, ExtractionOutput

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    answer_id         TEXT PRIMARY KEY,
    crawl_run_id      TEXT,
    target_month      TEXT,
    crawled_at        TEXT NOT NULL,
    chatbot           TEXT NOT NULL,
    model_name        TEXT,
    query_text        TEXT NOT NULL,
    answer_text       TEXT NOT NULL,
    source_file       TEXT,
    domain            TEXT,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'processing', 'ok', 'empty', 'failed')),
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    note              TEXT,
    extractor_model   TEXT,
    prompt_hash       TEXT,
    extractor_version TEXT,
    duration_ms       INTEGER,
    reprocess_count   INTEGER NOT NULL DEFAULT 0,
    llm_calls         INTEGER NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    usage_missing_calls INTEGER NOT NULL DEFAULT 0,
    registered_at     TEXT NOT NULL,
    started_at        TEXT,
    processed_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_answers_status ON answers(status, attempt_count);
CREATE INDEX IF NOT EXISTS idx_answers_month ON answers(target_month);
CREATE TABLE IF NOT EXISTS claims (
    claim_id        TEXT PRIMARY KEY,
    answer_id       TEXT NOT NULL REFERENCES answers(answer_id),
    domain          TEXT NOT NULL,
    target_month    TEXT,
    confidence_flag TEXT,
    data            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_answer ON claims(answer_id);
CREATE INDEX IF NOT EXISTS idx_claims_month ON claims(target_month);
CREATE TABLE IF NOT EXISTS rejected (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id TEXT NOT NULL REFERENCES answers(answer_id),
    reason    TEXT NOT NULL,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejected_answer ON rejected(answer_id);
CREATE TABLE IF NOT EXISTS claims_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id         TEXT NOT NULL,
    claim_id          TEXT NOT NULL,
    extractor_version TEXT,
    superseded_at     TEXT NOT NULL,
    data              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_history_answer ON claims_history(answer_id);
CREATE TABLE IF NOT EXISTS input_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    position    INTEGER,
    reason      TEXT NOT NULL,
    snippet     TEXT,
    seen_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_state (
    source_file TEXT PRIMARY KEY,
    byte_offset INTEGER NOT NULL DEFAULT 0,
    size        INTEGER NOT NULL DEFAULT 0,
    mtime_ns    INTEGER NOT NULL DEFAULT 0,
    head_hash   TEXT,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worker_lock (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    owner        TEXT NOT NULL,
    pid          INTEGER,
    host         TEXT,
    acquired_at  TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    activity     TEXT
);
CREATE TABLE IF NOT EXISTS run_log (
    run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger           TEXT NOT NULL,
    mode              TEXT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT NOT NULL,
    input_file        TEXT,
    registered        INTEGER NOT NULL DEFAULT 0,
    invalid_lines     INTEGER NOT NULL DEFAULT 0,
    processed         INTEGER NOT NULL DEFAULT 0,
    ok                INTEGER NOT NULL DEFAULT 0,
    empty             INTEGER NOT NULL DEFAULT 0,
    failed            INTEGER NOT NULL DEFAULT 0,
    claims            INTEGER NOT NULL DEFAULT 0,
    rejected          INTEGER NOT NULL DEFAULT 0,
    llm_calls         INTEGER NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    usage_missing_calls INTEGER NOT NULL DEFAULT 0,
    duration_ms       INTEGER,
    extractor_version TEXT,
    error             TEXT
);
"""

_DONE_STATUSES = ("ok", "empty")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _usage(output: ExtractionOutput) -> tuple[int, int, int, int]:
    return (output.llm_calls, output.prompt_tokens, output.completion_tokens,
            output.usage_missing_calls)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class ClaimStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: we manage transactions explicitly (BEGIN IMMEDIATE ... COMMIT)
        self._conn = sqlite3.connect(self.path, timeout=30, isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate_v1()
        self._conn.executescript(_SCHEMA)
        self._ensure_usage_columns()
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ---- housekeeping --------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ClaimStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def _ensure_usage_columns(self) -> None:
        """Databases created before cost logging get the token columns added in place."""
        for table in ("answers", "run_log"):
            have = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            for column in ("llm_calls", "prompt_tokens", "completion_tokens", "usage_missing_calls"):
                if column not in have:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")

    def _migrate_v1(self) -> None:
        """v1 had `extract_status` and no queue columns; rebuild `answers` once, keep the data.

        Follows SQLite's documented table-rebuild procedure (foreign keys off while swapping).
        """
        columns = [r[1] for r in self._conn.execute("PRAGMA table_info(answers)")]
        if not columns or "extract_status" not in columns:
            return
        answers_ddl = _SCHEMA.split("CREATE INDEX IF NOT EXISTS idx_answers_status")[0]
        answers_ddl = answers_ddl.replace(
            "CREATE TABLE IF NOT EXISTS answers (", "CREATE TABLE answers_v2 (", 1
        )
        self._conn.execute("PRAGMA foreign_keys = OFF")
        try:
            with self._tx() as conn:
                conn.execute(answers_ddl.strip().rstrip(";"))
                conn.execute(
                    """INSERT INTO answers_v2 (answer_id, crawled_at, chatbot, model_name,
                           query_text, answer_text, domain, status, extractor_model, prompt_hash,
                           last_error, registered_at, processed_at)
                       SELECT answer_id, crawled_at, chatbot, model_name, query_text, answer_text,
                              domain, extract_status, extractor_model, prompt_hash, error,
                              extracted_at, extracted_at FROM answers"""
                )
                conn.execute("DROP TABLE answers")
                conn.execute("ALTER TABLE answers_v2 RENAME TO answers")
        finally:
            self._conn.execute("PRAGMA foreign_keys = ON")
        if "target_month" not in [r[1] for r in self._conn.execute("PRAGMA table_info(claims)")]:
            self._conn.execute("ALTER TABLE claims ADD COLUMN target_month TEXT")

    # ---- ingest ----------------------------------------------------------------------

    def register_batch(
        self,
        answers: Iterable[AnswerRecord],
        source_file: str,
        *,
        errors: Iterable[tuple[int | None, str, str]] = (),
        checkpoint: dict[str, Any] | None = None,
    ) -> tuple[int, int]:
        """Insert unseen answers as `pending`, log input errors and move the checkpoint.

        One transaction: either the rows AND the new offset are saved, or neither, so a crash
        can never skip lines. Returns (newly_registered, already_known).
        """
        now = utcnow()
        rows = list(answers)
        with self._tx() as conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO answers
                   (answer_id, crawl_run_id, target_month, crawled_at, chatbot, model_name,
                    query_text, answer_text, source_file, status, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                [
                    (a.answer_id, a.crawl_run_id, a.target_month, a.crawled_at.isoformat(),
                     a.chatbot, a.model_name, a.query_text, a.answer_text, source_file, now)
                    for a in rows
                ],
            )
            new = conn.total_changes - before
            # same id arriving again with different text is a contract violation worth surfacing
            conflicts = self._id_conflicts(conn, rows)
            conn.executemany(
                "INSERT INTO input_errors (source_file, position, reason, snippet, seen_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(source_file, pos, reason, snippet[:300], now) for pos, reason, snippet in errors]
                + [(source_file, None, "answer_id_conflict", a_id, now) for a_id in conflicts],
            )
            if checkpoint is not None:
                conn.execute(
                    """INSERT INTO ingest_state (source_file, byte_offset, size, mtime_ns,
                                                 head_hash, updated_at)
                       VALUES (:source_file, :byte_offset, :size, :mtime_ns, :head_hash, :now)
                       ON CONFLICT(source_file) DO UPDATE SET byte_offset = :byte_offset,
                           size = :size, mtime_ns = :mtime_ns, head_hash = :head_hash,
                           updated_at = :now""",
                    {"source_file": source_file, "now": now, "head_hash": None,
                     "mtime_ns": 0, **checkpoint},
                )
        return new, len(rows) - new

    @staticmethod
    def _id_conflicts(conn: sqlite3.Connection, rows: list[AnswerRecord]) -> list[str]:
        out: list[str] = []
        for a in rows:
            row = conn.execute(
                "SELECT answer_text FROM answers WHERE answer_id = ?", (a.answer_id,)
            ).fetchone()
            if row is not None and row[0] != a.answer_text:
                out.append(a.answer_id)
        return out

    def get_ingest_state(self, source_file: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM ingest_state WHERE source_file = ?", (source_file,)
        ).fetchone()
        return dict(row) if row else None

    def clear_ingest_state(self, source_file: str | None = None) -> None:
        with self._tx() as conn:
            if source_file:
                conn.execute("DELETE FROM ingest_state WHERE source_file = ?", (source_file,))
            else:
                conn.execute("DELETE FROM ingest_state")

    # ---- work queue ------------------------------------------------------------------

    def recover_interrupted(self) -> int:
        """Rows left `processing` by a stopped process go back to `pending` (retry)."""
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE answers SET status = 'pending', last_error = "
                "COALESCE(last_error, 'interrupted: process stopped mid-answer') "
                "WHERE status = 'processing'"
            )
            return cur.rowcount

    def claim_batch(
        self, limit: int, *, max_attempts: int = 3, retry_failed: bool = True,
        not_tried_since: str | None = None, retry_not_before: str | None = None,
    ) -> list[AnswerRecord]:
        """Take up to `limit` answers to work on and mark them `processing` (attempt + 1).

        New (pending) answers go first; failed ones are re-tried only while they still have
        attempts left. `not_tried_since` (ISO time) keeps a caller from re-claiming, within one
        run, a failed answer it already tried in that run. `retry_not_before` (ISO time) is the
        back-off: failed answers whose last attempt is later than this are left alone for now.
        """
        eligible = "status = 'pending'"
        params: list[Any] = []
        if retry_failed:
            eligible = "(status = 'pending' OR (status = 'failed' AND attempt_count < ?"
            params.append(max_attempts)
            if not_tried_since:
                eligible += " AND (started_at IS NULL OR started_at < ?)"
                params.append(not_tried_since)
            if retry_not_before:
                eligible += " AND (processed_at IS NULL OR processed_at <= ?)"
                params.append(retry_not_before)
            eligible += "))"
        with self._tx() as conn:
            rows = conn.execute(
                f"""SELECT * FROM answers WHERE {eligible}
                    ORDER BY (status = 'failed'), rowid LIMIT ?""",
                (*params, limit),
            ).fetchall()
            now = utcnow()
            conn.executemany(
                "UPDATE answers SET status = 'processing', attempt_count = attempt_count + 1, "
                "started_at = ? WHERE answer_id = ?",
                [(now, r["answer_id"]) for r in rows],
            )
        return [
            AnswerRecord(
                answer_id=r["answer_id"], crawl_run_id=r["crawl_run_id"],
                target_month=r["target_month"], crawled_at=r["crawled_at"], chatbot=r["chatbot"],
                model_name=r["model_name"], query_text=r["query_text"],
                answer_text=r["answer_text"],
            )
            for r in rows
        ]

    def unclaim(self, answer_ids: list[str]) -> None:
        """Return claimed-but-untouched answers to the queue without spending an attempt."""
        with self._tx() as conn:
            conn.executemany(
                "UPDATE answers SET status = 'pending', attempt_count = MAX(attempt_count - 1, 0) "
                "WHERE answer_id = ? AND status = 'processing'",
                [(i,) for i in answer_ids],
            )

    def count_workable(self, *, max_attempts: int = 3, retry_failed: bool = True,
                       retry_not_before: str | None = None) -> int:
        """How many answers a run could pick up right now (same rules as `claim_batch`)."""
        sql = "SELECT COUNT(*) FROM answers WHERE (status = 'pending'"
        params: list[Any] = []
        if retry_failed:
            sql += " OR (status = 'failed' AND attempt_count < ?"
            params.append(max_attempts)
            if retry_not_before:
                sql += " AND (processed_at IS NULL OR processed_at <= ?)"
                params.append(retry_not_before)
            sql += ")"
        sql += ")"
        return self._conn.execute(sql, params).fetchone()[0]

    def save(self, answer: AnswerRecord, output: ExtractionOutput) -> None:
        """Store the outcome of one answer in a single transaction.

        ok/empty replace the answer's previous claims (moving them to `claims_history`).
        A failure only updates the status, so claims from an earlier good run survive.
        """
        meta = output.model_dump(mode="json")
        now = utcnow()
        with self._tx() as conn:
            if output.extract_status == "failed":
                conn.execute(
                    """UPDATE answers SET status = 'failed', last_error = ?, domain = ?,
                       extractor_model = ?, prompt_hash = ?, extractor_version = ?,
                       duration_ms = ?, processed_at = ?, llm_calls = llm_calls + ?,
                       prompt_tokens = prompt_tokens + ?, completion_tokens = completion_tokens + ?,
                       usage_missing_calls = usage_missing_calls + ? WHERE answer_id = ?""",
                    (output.error, output.domain, output.extractor_model, output.prompt_hash,
                     output.extractor_version, output.duration_ms, now, *_usage(output),
                     answer.answer_id),
                )
                return
            conn.execute(
                """INSERT INTO claims_history (answer_id, claim_id, extractor_version,
                                               superseded_at, data)
                   SELECT c.answer_id, c.claim_id, a.extractor_version, ?, c.data
                   FROM claims c JOIN answers a USING (answer_id) WHERE c.answer_id = ?""",
                (now, answer.answer_id),
            )
            conn.execute("DELETE FROM claims WHERE answer_id = ?", (answer.answer_id,))
            conn.execute("DELETE FROM rejected WHERE answer_id = ?", (answer.answer_id,))
            conn.execute(
                """UPDATE answers SET status = ?, last_error = NULL, note = ?, domain = ?,
                   extractor_model = ?, prompt_hash = ?, extractor_version = ?, duration_ms = ?,
                   processed_at = ?, llm_calls = llm_calls + ?, prompt_tokens = prompt_tokens + ?,
                   completion_tokens = completion_tokens + ?,
                   usage_missing_calls = usage_missing_calls + ? WHERE answer_id = ?""",
                (output.extract_status, output.note, output.domain, output.extractor_model,
                 output.prompt_hash, output.extractor_version, output.duration_ms, now,
                 *_usage(output), answer.answer_id),
            )
            conn.executemany(
                "INSERT INTO claims (claim_id, answer_id, domain, target_month, confidence_flag, "
                "data) VALUES (?, ?, ?, ?, ?, ?)",
                [(c["claim_id"], answer.answer_id, output.domain, answer.target_month,
                  c.get("confidence_flag"), _dumps(c)) for c in meta["claims"]],
            )
            conn.executemany(
                "INSERT INTO rejected (answer_id, reason, data) VALUES (?, ?, ?)",
                [(answer.answer_id, r.get("reason", "unknown"), _dumps(r))
                 for r in meta["rejected"]],
            )

    def mark_pending(
        self,
        *,
        statuses: Iterable[str] = (),
        answer_ids: Iterable[str] = (),
        target_month: str | None = None,
        crawl_run_id: str | None = None,
        stale_version: str | None = None,
        reset_attempts: bool = True,
    ) -> int:
        """Deliberate reprocess: put matching answers back in the queue.

        Select by status, ids, month, crawl run, or "extracted with another extractor version"
        (`stale_version` = the current version). Nothing is deleted here; old claims move to
        `claims_history` when the new result is saved. In-flight (`processing`) rows are skipped.
        """
        where, params = ["status != 'processing'"], []
        statuses, answer_ids = list(statuses), list(answer_ids)
        if statuses:
            where.append(f"status IN ({','.join('?' * len(statuses))})")
            params += statuses
        if answer_ids:
            where.append(f"answer_id IN ({','.join('?' * len(answer_ids))})")
            params += answer_ids
        if target_month:
            where.append("target_month = ?")
            params.append(target_month)
        if crawl_run_id:
            where.append("crawl_run_id = ?")
            params.append(crawl_run_id)
        if stale_version:
            where.append("status IN ('ok', 'empty') AND COALESCE(extractor_version, '') != ?")
            params.append(stale_version)
        reset = ", attempt_count = 0" if reset_attempts else ""
        with self._tx() as conn:
            cur = conn.execute(
                f"UPDATE answers SET status = 'pending', reprocess_count = reprocess_count + 1"
                f"{reset} WHERE {' AND '.join(where)}",
                params,
            )
            return cur.rowcount

    def is_done(self, answer_id: str) -> bool:
        row = self._conn.execute(
            "SELECT status FROM answers WHERE answer_id = ?", (answer_id,)
        ).fetchone()
        return row is not None and row[0] in _DONE_STATUSES

    # ---- worker lock (single worker, across processes) ----------------------------------

    def acquire_lock(self, owner: str, *, stale_after_s: int = 120, activity: str = "") -> bool:
        """Take the single-worker lock. A lock whose heartbeat is stale is taken over."""
        now = datetime.now(timezone.utc)
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM worker_lock WHERE id = 1").fetchone()
            if row is not None:
                age = now - datetime.fromisoformat(row["heartbeat_at"])
                if row["owner"] != owner and age < timedelta(seconds=stale_after_s):
                    return False
            conn.execute(
                """INSERT INTO worker_lock (id, owner, pid, host, acquired_at, heartbeat_at, activity)
                   VALUES (1, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET owner = excluded.owner, pid = excluded.pid,
                       host = excluded.host, acquired_at = excluded.acquired_at,
                       heartbeat_at = excluded.heartbeat_at, activity = excluded.activity""",
                (owner, os.getpid(), socket.gethostname(), now.isoformat(timespec="seconds"),
                 now.isoformat(timespec="seconds"), activity),
            )
        return True

    def heartbeat(self, owner: str, activity: str | None = None) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE worker_lock SET heartbeat_at = ?, activity = COALESCE(?, activity) "
                "WHERE id = 1 AND owner = ?",
                (utcnow(), activity, owner),
            )

    def release_lock(self, owner: str) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM worker_lock WHERE id = 1 AND owner = ?", (owner,))

    def lock_info(self) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM worker_lock WHERE id = 1").fetchone()
        return dict(row) if row else None

    # ---- run log ------------------------------------------------------------------------

    def start_run(self, trigger: str, mode: str, input_file: str, version: str) -> int:
        with self._tx() as conn:
            return conn.execute(
                "INSERT INTO run_log (trigger, mode, started_at, status, input_file, "
                "extractor_version) VALUES (?, ?, ?, 'running', ?, ?)",
                (trigger, mode, utcnow(), input_file, version),
            ).lastrowid

    def finish_run(self, run_id: int, status: str, duration_ms: int, error: str | None = None,
                   **counts: int) -> None:
        allowed = ("registered", "invalid_lines", "processed", "ok", "empty", "failed",
                   "claims", "rejected", "llm_calls", "prompt_tokens", "completion_tokens",
                   "usage_missing_calls")
        sets = ", ".join(f"{k} = ?" for k in counts if k in allowed)
        values = [v for k, v in counts.items() if k in allowed]
        with self._tx() as conn:
            conn.execute(
                f"UPDATE run_log SET finished_at = ?, status = ?, duration_ms = ?, error = ?"
                f"{', ' + sets if sets else ''} WHERE run_id = ?",
                (utcnow(), status, duration_ms, error, *values, run_id),
            )

    def close_dangling_runs(self) -> int:
        """Runs still marked `running` belong to a process that died; close them as aborted."""
        with self._tx() as conn:
            return conn.execute(
                "UPDATE run_log SET status = 'aborted', finished_at = ?, "
                "error = 'process stopped before the run finished' WHERE status = 'running'",
                (utcnow(),),
            ).rowcount

    # ---- reads -----------------------------------------------------------------------

    def iter_claims(self, domain: str | None = None, target_month: str | None = None
                    ) -> Iterator[dict[str, Any]]:
        where, params = [], []
        if domain:
            where.append("domain = ?")
            params.append(domain)
        if target_month:
            where.append("target_month = ?")
            params.append(target_month)
        sql = "SELECT data FROM claims" + (f" WHERE {' AND '.join(where)}" if where else "")
        for row in self._conn.execute(sql + " ORDER BY rowid", params):
            yield json.loads(row[0])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """Read-only helper for monitoring code (stats.py, the UI)."""
        return [dict(r) for r in self._conn.execute(sql, tuple(params))]

    def counts(self) -> dict[str, int]:
        scalar = lambda sql: self._conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "answers": scalar("SELECT COUNT(*) FROM answers"),
            "answers_failed": scalar("SELECT COUNT(*) FROM answers WHERE status = 'failed'"),
            "claims": scalar("SELECT COUNT(*) FROM claims"),
            "rejected": scalar("SELECT COUNT(*) FROM rejected"),
        }
