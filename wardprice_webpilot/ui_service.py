"""Single-request Streamlit bridge for the local Gemini Web pilot."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .candidate_batch import classify_source_url_type
from .core import (
    connect,
    load_targets,
    make_prompt,
    parse_json_text,
    process_payload,
    process_response_for_run,
    start_run,
)

MAX_UI_COUNT = 10
MAX_DAILY_CALLS = 3
MAX_TRACKED_CANDIDATES = 500


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    result = str(value)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    return result


def _source_list(citations: list[dict[str, Any]], secrets: tuple[str, ...]):
    safe = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        safe.append(
            {
                "title": _redact(str(citation.get("title") or ""), secrets),
                "url": _redact(str(citation.get("url") or ""), secrets),
            }
        )
    return safe


def run_live_collection(
    *,
    targets_db: Path,
    audit_db: Path,
    inbox: Path,
    rank: int,
    count: int,
    session_cookie: str,
    session_token: str = "",
    progress: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Run one bounded request and store only in the separate pilot audit DB.

    Credentials are passed as arguments and are never written to SQLite or files.
    The response remains an unverified research candidate; canonical tables are
    intentionally untouched.
    """
    cookie = str(session_cookie or "").strip()
    token = str(session_token or "").strip()
    secrets = (cookie, token)
    if not cookie:
        raise ValueError("Nhập cookie 1PSID trước khi chạy; chưa gửi request.")
    if not 1 <= rank <= 50:
        raise ValueError("Chọn target rank từ 1 đến 50.")
    if not 1 <= count <= MAX_UI_COUNT:
        raise ValueError(f"UI giới hạn tối đa {MAX_UI_COUNT} tin trong một request.")
    if targets_db.resolve() == audit_db.resolve():
        raise ValueError("Database audit phải tách biệt database target/production.")
    if importlib.util.find_spec("gemini_webapi") is None:
        raise ValueError("Chưa cài gemini_webapi; chưa gửi request.")

    targets = load_targets(targets_db)
    target = targets[rank]
    prompt = make_prompt(target, count)
    if progress:
        progress("preflight", "Đã tải target và kiểm tra giới hạn request.")

    inbox.mkdir(parents=True, exist_ok=True)
    prompt_path = inbox / "latest_ui_live_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    database = connect(audit_db)
    run_id: int | None = None
    try:
        usage_day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        database.execute("BEGIN IMMEDIATE")
        candidate_count = database.execute("SELECT COUNT(*) FROM webpilot_candidates").fetchone()[0]
        batch_table = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='webpilot_batch_candidates'"
        ).fetchone()
        if batch_table:
            candidate_count += database.execute(
                "SELECT COUNT(*) FROM webpilot_batch_candidates"
            ).fetchone()[0]
        daily_attempts = database.execute(
            """SELECT COUNT(*) FROM webpilot_runs
               WHERE origin='gemini_web_attempt' AND date(occurred_at,'+7 hours')=?""",
            (usage_day,),
        ).fetchone()[0]
        if candidate_count >= MAX_TRACKED_CANDIDATES:
            database.rollback()
            raise ValueError("Đã đạt giới hạn 500 ứng viên audit; không gửi request.")
        if daily_attempts >= MAX_DAILY_CALLS:
            database.rollback()
            raise ValueError(
                f"Đã dùng {daily_attempts}/{MAX_DAILY_CALLS} request pilot hôm nay; không gửi thêm."
            )

        run_id = start_run(
            database,
            origin="gemini_web_attempt",
            requested_rank=rank,
            prompt_text=prompt,
            request_metadata={
                "model": None,
                "requested_count": count,
                "adapter": "gemini_webapi",
                "retry_policy": "no_generation_retry",
                "daily_call_cap": MAX_DAILY_CALLS,
                "daily_call_number": daily_attempts + 1,
                "usage_day_vietnam": usage_day,
                "interface": "streamlit_local",
                "prompt_file": str(prompt_path),
                "credential_storage": "memory_only_then_discarded",
            },
        )
        database.commit()

        if progress:
            progress("gemini", "Đang gửi một request Gemini Web; không tự retry.")
        try:
            from .webclient import collect_from_web

            raw_text, citations = asyncio.run(
                collect_from_web(
                    prompt,
                    session_cookie=cookie,
                    session_token=token,
                )
            )
        except Exception as exc:  # noqa: BLE001 - safe diagnostic, never include credentials
            safe_error = _redact(str(exc) or type(exc).__name__, secrets)[:1500]
            with database:
                database.execute(
                    "UPDATE webpilot_runs SET status='FAILED',result_json=? WHERE run_id=?",
                    (json.dumps({"error": safe_error}, ensure_ascii=False), run_id),
                )
            return {
                "status": "FAILED",
                "run_id": run_id,
                "target": target,
                "error": safe_error,
                "network_attempted": True,
                "production_database_written": False,
                "prompt_file": str(prompt_path),
            }

        safe_text = _redact(raw_text, secrets)
        safe_citations = _source_list(citations or [], secrets)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        raw_path = inbox / f"gemini_web_ui_rank{rank:02d}_{stamp}.txt"
        raw_path.write_text(safe_text, encoding="utf-8")
        with database:
            database.execute(
                """UPDATE webpilot_runs SET status='RECEIVED',raw_response_text=?,
                   citation_count=?,citations_json=? WHERE run_id=?""",
                (
                    safe_text,
                    len(safe_citations),
                    json.dumps(safe_citations, ensure_ascii=False),
                    run_id,
                ),
            )

        if progress:
            progress("parse", "Đã nhận phản hồi; đang parse JSON và giới hạn số tin.")
        try:
            payload = parse_json_text(safe_text)
        except (TypeError, ValueError):
            result = process_response_for_run(
                database,
                run_id,
                safe_text,
                targets,
                requested_rank=rank,
                citations=safe_citations,
            )
            response_count = None
            truncated_count = 0
        else:
            if isinstance(payload, list):
                response_count = len(payload)
                payload = payload[:count]
                truncated_count = max(response_count - count, 0)
            else:
                listings = payload.get("listings")
                response_count = len(listings) if isinstance(listings, list) else None
                if isinstance(listings, list):
                    payload = {**payload, "listings": listings[:count]}
                truncated_count = max((response_count or 0) - count, 0)
            try:
                result = process_payload(
                    database,
                    run_id,
                    payload,
                    targets,
                    raw_response_text=safe_text,
                    requested_rank=rank,
                    citations=safe_citations,
                )
            except (TypeError, ValueError) as exc:
                safe_error = _redact(str(exc), secrets)[:1000]
                with database:
                    database.execute(
                        """UPDATE webpilot_runs SET status='SCHEMA_FAILURE',result_json=?
                           WHERE run_id=?""",
                        (json.dumps({"error": safe_error}, ensure_ascii=False), run_id),
                    )
                result = {
                    "run_id": run_id,
                    "status": "SCHEMA_FAILURE",
                    "error": safe_error,
                    "received": 0,
                }

        if progress:
            progress(
                "audit", "Đã ghi kết quả vào sidecar audit; không ghi database giá production."
            )
        result.update(
            {
                "status": result.get("status") or "COMPLETE",
                "target": target,
                "requested_count": count,
                "response_listing_count": response_count,
                "truncated_to_limit": truncated_count,
                "raw_response_file": str(raw_path),
                "prompt_file": str(prompt_path),
                "network_attempted": True,
                "production_database_written": False,
                "evidence_note": "Gemini claims/citations are audit signals; all candidates remain UNVERIFIED until independently checked.",
            }
        )
        return result
    finally:
        database.close()


def recent_candidates(audit_db: Path, rank: int, *, limit: int = 10) -> list[dict[str, Any]]:
    """Read a small target-scoped view from the pilot sidecar, never production."""
    if not audit_db.exists():
        return []
    database = sqlite3.connect(f"file:{audit_db.resolve().as_posix()}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    try:
        rows: list[dict[str, Any]] = []
        try:
            legacy_rows = database.execute(
                """SELECT target_rank,original_ward,property_type,title,address,price_vnd,
                          area_m2,price_per_m2,source_url,evidence_status,geo_status,
                          quarantine_reason,collected_at,possible_duplicate
                   FROM webpilot_candidates WHERE target_rank=?
                   ORDER BY collected_at DESC,rowid DESC LIMIT ?""",
                (rank, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            legacy_rows = []
        for source in legacy_rows:
            row = dict(source)
            row["source_url_type"] = classify_source_url_type(row.get("source_url"))
            row["verification_label"] = "Chưa xác minh nguồn"
            quarantine = str(row.get("quarantine_reason") or "")
            row["review_status"] = (
                "SOURCE_CONFLICT"
                if row.get("possible_duplicate") and "conflict" in quarantine.casefold()
                else "NEEDS_REVIEW"
                if row.get("possible_duplicate") or quarantine
                else "NEEDS_SOURCE_REVIEW"
            )
            row["review_warning"] = quarantine
            rows.append(row)

        has_batch_candidates = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='webpilot_batch_candidates'"
        ).fetchone()
        if has_batch_candidates:
            imported_rows = database.execute(
                """SELECT target_rank,original_ward,property_type,title,address,price_vnd,
                          area_m2,price_per_m2,source_url,source_url_type,evidence_status,
                          verification_label,geo_status,review_status,review_warning,
                          quarantine_reason,first_run_date AS collected_at,possible_duplicate
                   FROM webpilot_batch_candidates WHERE target_rank=?
                   ORDER BY first_run_date DESC,rowid DESC LIMIT ?""",
                (rank, limit),
            ).fetchall()
            rows.extend(dict(row) for row in imported_rows)

        # Category URLs are deliberately excluded from the cross-source identity.
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            identity = (
                row.get("target_rank"),
                row.get("property_type"),
                str(row.get("title") or "").casefold().strip(),
                str(row.get("address") or "").casefold().strip(),
                row.get("price_vnd"),
                round(float(row.get("area_m2") or 0), 4),
            )
            unique.setdefault(identity, row)
        return sorted(
            unique.values(),
            key=lambda row: (str(row.get("collected_at") or ""), str(row.get("title") or "")),
            reverse=True,
        )[: max(1, min(int(limit), 100))]
    finally:
        database.close()
