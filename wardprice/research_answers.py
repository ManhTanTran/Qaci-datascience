"""Local, resumable sourced Q&A research by current administrative unit.

This module is intentionally separate from listing validation and statistics.
It writes partner-shaped answer records to a local JSONL export and keeps
per-area progress in a local SQLite sidecar.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, ResearchAPISettings

DEFAULT_ADMIN_CSV = (
    PROJECT_ROOT
    / "data"
    / "administrative"
    / "processed"
    / "nso_communes_as_of_2026-10-13.csv"
)
DEFAULT_RESEARCH_DB = PROJECT_ROOT / "state" / "ward_price_answers.sqlite3"
DEFAULT_JSONL_DIR = PROJECT_ROOT / "outputs" / "research_answers"
PROPERTY_TYPES = ("đất ở", "nhà riêng", "chung cư")
_RUN_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_answer_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    administrative_code TEXT NOT NULL,
    administrative_name TEXT NOT NULL,
    administrative_type TEXT NOT NULL,
    province_code TEXT NOT NULL,
    province_name TEXT NOT NULL,
    administrative_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'PENDING','RUNNING','COMPLETED','NO_RESULT','FAILED'
    )),
    query_text TEXT NOT NULL,
    answer_text TEXT,
    chatbot TEXT NOT NULL DEFAULT 'Gemma',
    model_name TEXT,
    crawled_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error_text TEXT,
    UNIQUE(period, administrative_code, administrative_version)
);
CREATE INDEX IF NOT EXISTS ix_research_answer_jobs_period_status
    ON research_answer_jobs(period, status, administrative_name);
CREATE TABLE IF NOT EXISTS research_answer_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    requested_count INTEGER NOT NULL,
    completed_count INTEGER NOT NULL DEFAULT 0,
    no_result_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_text TEXT
);
"""


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_period(period: str) -> str:
    value = str(period or "").strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("Kỳ thu thập phải có định dạng YYYY-MM, ví dụ 2026-10.")
    return value


def load_administrative_units(
    csv_path: Path = DEFAULT_ADMIN_CSV,
    *,
    province: str | None = None,
    administrative_code: str | None = None,
) -> list[dict[str, str]]:
    """Read one NSO snapshot, preferring explicit current flags when present.

    Some normalized NSO snapshots have no rows flagged current even though all
    commune rows belong to one as-of version and have no end date. For this
    snapshot-only research flow, those rows are safe to use as snapshot targets;
    this does not promote them in the canonical administrative registry.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy danh mục hành chính: {csv_path}")

    required = {
        "administrative_code",
        "administrative_name",
        "administrative_level",
        "administrative_type",
        "province_code",
        "province_name",
        "administrative_version",
        "is_current",
    }
    candidate_units: list[tuple[dict[str, str], str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV danh mục thiếu cột mã, tên hoặc phiên bản hành chính.")
        for row in reader:
            if row.get("administrative_level") != "COMMUNE":
                continue
            code = (row.get("administrative_code") or "").strip()
            name = (row.get("administrative_name") or "").strip()
            province_code = (row.get("province_code") or "").strip()
            province_name = (row.get("province_name") or "").strip()
            version = (row.get("administrative_version") or "").strip()
            if not all((code, name, province_code, province_name, version)):
                continue
            if province and province_name.casefold() != province.strip().casefold():
                continue
            if administrative_code and code != administrative_code.strip():
                continue
            candidate_units.append(
                ({
                    "administrative_code": code,
                    "administrative_name": name,
                    "administrative_type": (row.get("administrative_type") or "").strip(),
                    "province_code": province_code,
                    "province_name": province_name,
                    "administrative_version": version,
                }, (row.get("is_current") or "").strip(), (row.get("valid_to") or "").strip())
            )
    current_units = [unit for unit, is_current, _ in candidate_units if is_current == "1"]
    if current_units:
        units = current_units
    else:
        unexpired = [unit for unit, _, valid_to in candidate_units if not valid_to]
        versions = {unit["administrative_version"] for unit in unexpired}
        if len(unexpired) == len(candidate_units) and len(versions) == 1:
            units = unexpired
        else:
            units = []
    units.sort(key=lambda item: (item["province_name"], item["administrative_name"], item["administrative_code"]))
    return units


def list_provinces(csv_path: Path = DEFAULT_ADMIN_CSV) -> list[str]:
    return sorted({unit["province_name"] for unit in load_administrative_units(csv_path)})


def _connect(database_path: Path = DEFAULT_RESEARCH_DB) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def make_query_text(unit: dict[str, str], period: str) -> str:
    """Create partner-schema query text with stable administrative join keys."""
    return (
        f"Tra cứu giá rao bất động sản {period} tại {unit['administrative_name']}, "
        f"{unit['province_name']} (mã địa bàn {unit['administrative_code']}; "
        f"mã tỉnh {unit['province_code']}; danh mục {unit['administrative_version']}). "
        "Tìm thông tin có nguồn cho đất ở, nhà riêng và chung cư."
    )


def make_search_query(unit: dict[str, str], period: str) -> str:
    """Create one open-web query for listing and third-party market summaries."""
    return (
        f"giá rao giá trung vị khoảng giá số tin đất nền nhà riêng nhà phố chung cư "
        f"{unit['administrative_name']} {unit['province_name']} tháng {period[5:7]}/{period[:4]}"
    )


def prepare_jobs(
    period: str,
    *,
    province: str | None = None,
    administrative_code: str | None = None,
    csv_path: Path = DEFAULT_ADMIN_CSV,
    database_path: Path = DEFAULT_RESEARCH_DB,
) -> dict[str, Any]:
    """Create/resume local jobs for every selected commune; never calls a provider."""
    period = _validate_period(period)
    units = load_administrative_units(
        csv_path, province=province, administrative_code=administrative_code
    )
    if not units:
        raise ValueError("Không có địa bàn cấp xã trong snapshot hành chính đã chọn.")
    now = _now_utc()
    connection = _connect(database_path)
    try:
        _initialize(connection)
        with connection:
            connection.executemany(
                """INSERT OR IGNORE INTO research_answer_jobs(
                       period,administrative_code,administrative_name,administrative_type,
                       province_code,province_name,administrative_version,status,query_text,
                       created_at
                   ) VALUES(?,?,?,?,?,?,?,'PENDING',?,?)""",
                [
                    (
                        period,
                        unit["administrative_code"],
                        unit["administrative_name"],
                        unit["administrative_type"],
                        unit["province_code"],
                        unit["province_name"],
                        unit["administrative_version"],
                        make_query_text(unit, period),
                        now,
                    )
                    for unit in units
                ],
            )
        counts = _status_counts(connection, period)
        return {
            "status": "PREPARED",
            "period": period,
            "scope_province": province,
            "target_count": len(units),
            "job_counts": counts,
            "network_attempted": False,
        }
    finally:
        connection.close()


def _status_counts(connection: sqlite3.Connection, period: str) -> dict[str, int]:
    values = {name: 0 for name in ("PENDING", "RUNNING", "COMPLETED", "NO_RESULT", "FAILED")}
    rows = connection.execute(
        "SELECT status,COUNT(*) AS n FROM research_answer_jobs WHERE period=? GROUP BY status",
        (period,),
    ).fetchall()
    values.update({row["status"]: int(row["n"]) for row in rows})
    values["total"] = sum(values.values())
    return values


def research_status(
    period: str,
    *,
    database_path: Path = DEFAULT_RESEARCH_DB,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    period = _validate_period(period)
    if not database_path.is_file():
        return {
            "status": "NOT_PREPARED",
            "period": period,
            "job_counts": {"PENDING": 0, "RUNNING": 0, "COMPLETED": 0, "NO_RESULT": 0, "FAILED": 0, "total": 0},
            "jobs": [],
            "jsonl_path": None,
        }
    connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_answer_jobs'"
        ).fetchone()
        if not tables:
            return {
                "status": "NOT_PREPARED",
                "period": period,
                "job_counts": {"PENDING": 0, "RUNNING": 0, "COMPLETED": 0, "NO_RESULT": 0, "FAILED": 0, "total": 0},
                "jobs": [],
                "jsonl_path": None,
            }
        counts = _status_counts(connection, period)
        jobs = [
            dict(row)
            for row in connection.execute(
                """SELECT administrative_code,administrative_name,province_name,status,
                          attempt_count,started_at,finished_at,error_text
                   FROM research_answer_jobs WHERE period=?
                   ORDER BY province_name,administrative_name,administrative_code
                   LIMIT ? OFFSET ?""",
                (period, max(1, min(limit, 500)), max(0, offset)),
            ).fetchall()
        ]
        output_path = DEFAULT_JSONL_DIR / f"gemma_answers_{period}.jsonl"
        return {
            "status": "READY",
            "period": period,
            "job_counts": counts,
            "jobs": jobs,
            "jsonl_path": (
                str(output_path) if output_path.is_file() and output_path.stat().st_size else None
            ),
        }
    finally:
        connection.close()


def _answer_with_sources(answer: str, results: list[dict[str, str]]) -> str:
    """Append numbered URLs so citations remain usable in partner's answer_text."""
    source_lines = ["\n\nNguồn tìm kiếm (Tavily; chỉ lưu URL và tiêu đề):"]
    for index, item in enumerate(results, 1):
        published = f" · ngày nguồn: {item['published_date']}" if item["published_date"] else ""
        source_lines.append(f"\n[{index}] {item['title']}{published} — {item['url']}")
    return answer.strip() + "".join(source_lines)


def _declares_no_result(answer: str) -> bool:
    first_line = answer.strip().splitlines()[0].casefold() if answer.strip() else ""
    return first_line.startswith("kết quả: chưa tìm thấy")


def _has_valid_citation(answer: str, source_count: int) -> bool:
    return any(
        1 <= int(index) <= source_count
        for index in re.findall(r"\[(\d+)\]", answer)
    )


def _export_jsonl(period: str, *, database_path: Path) -> Path | None:
    period = _validate_period(period)
    connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT crawled_at,chatbot,model_name,query_text,answer_text
               FROM research_answer_jobs
               WHERE period=? AND chatbot='Gemma' AND status IN ('COMPLETED','NO_RESULT')
               ORDER BY province_name,administrative_name,administrative_code""",
            (period,),
        ).fetchall()
        output = DEFAULT_JSONL_DIR / f"gemma_answers_{period}.jsonl"
        if not rows:
            return output if output.is_file() and output.stat().st_size else None
        DEFAULT_JSONL_DIR.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                record = {
                    "crawled_at": row["crawled_at"],
                    "chatbot": row["chatbot"],
                    "model_name": row["model_name"],
                    "query_text": row["query_text"],
                    "answer_text": row["answer_text"],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(output)
        return output
    finally:
        connection.close()


def run_batch(
    period: str,
    *,
    limit: int = 5,
    retry_failed: bool = False,
    database_path: Path = DEFAULT_RESEARCH_DB,
) -> dict[str, Any]:
    """Search and summarize one explicit batch; never mixes answers into listing data."""
    period = _validate_period(period)
    if not 1 <= limit <= 20:
        raise ValueError("Mỗi lượt chỉ được chọn từ 1 đến 20 địa bàn.")
    settings = ResearchAPISettings.from_env()
    if not settings.search_api_key:
        raise RuntimeError("Thiếu TAVILY_API_KEY; chưa gửi request.")
    if not settings.model_api_key or not settings.model_base_url:
        raise RuntimeError("Cần cấu hình OPENAI_API_KEY và OPENAI_BASE_URL; chưa gửi request.")
    if not database_path.is_file():
        raise FileNotFoundError("Chưa chuẩn bị danh sách địa bàn cho kỳ này.")
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("Đang có một lượt nghiên cứu khác chạy trong ứng dụng này.")

    connection: sqlite3.Connection | None = None
    run_id: int | None = None
    completed = no_result = failed = 0
    try:
        connection = _connect(database_path)
        _initialize(connection)
        # A process restart may leave jobs marked RUNNING; make them resumable.
        with connection:
            connection.execute(
                """UPDATE research_answer_jobs SET status='PENDING',
                   error_text='Lượt trước dừng giữa chừng; có thể chạy lại.'
                   WHERE period=? AND status='RUNNING'""",
                (period,),
            )
        eligible_statuses = "('PENDING','FAILED')" if retry_failed else "('PENDING')"
        jobs = connection.execute(
            f"""SELECT * FROM research_answer_jobs WHERE period=? AND status IN {eligible_statuses}
                ORDER BY province_name,administrative_name,administrative_code LIMIT ?""",
            (period, limit),
        ).fetchall()
        if not jobs:
            counts = _status_counts(connection, period)
            if counts["total"] == 0:
                return {
                    "status": "NOT_PREPARED",
                    "period": period,
                    "processed": 0,
                    "job_counts": counts,
                    "jsonl_path": None,
                    "network_attempted": False,
                }
            return {
                "status": "NO_PENDING_JOBS",
                "period": period,
                "processed": 0,
                "job_counts": counts,
                "jsonl_path": (
                    str(path) if (path := _export_jsonl(period, database_path=database_path)) else None
                ),
                "network_attempted": False,
            }

        started = _now_utc()
        with connection:
            run_id = int(
                connection.execute(
                    """INSERT INTO research_answer_runs(period,started_at,status,requested_count)
                       VALUES(?,?,?,?)""",
                    (period, started, "RUNNING", len(jobs)),
                ).lastrowid
            )
        from .research_provider import search_web, summarize_search_results

        for job in jobs:
            job_started = _now_utc()
            with connection:
                connection.execute(
                    """UPDATE research_answer_jobs SET status='RUNNING',started_at=?,
                       attempt_count=attempt_count+1,error_text=NULL WHERE job_id=?""",
                    (job_started, job["job_id"]),
                )
            try:
                unit = {
                    "administrative_code": job["administrative_code"],
                    "administrative_name": job["administrative_name"],
                    "province_code": job["province_code"],
                    "province_name": job["province_name"],
                    "administrative_version": job["administrative_version"],
                }
                search_query = make_search_query(unit, period)
                query_text = make_query_text(unit, period)
                results = search_web(search_query, settings)
                if results:
                    raw_answer, resolved_model = summarize_search_results(
                        query_text=query_text,
                        search_query=search_query,
                        results=results,
                        settings=settings,
                    )
                    has_supported_result = (
                        raw_answer.strip().casefold().startswith("kết quả: tìm thấy")
                        and _has_valid_citation(raw_answer, len(results))
                    )
                    if not has_supported_result and not _declares_no_result(raw_answer):
                        raw_answer = (
                            "KẾT QUẢ: CHƯA TÌM THẤY\n"
                            "Bản tóm tắt không có citation hợp lệ gắn với kết quả tìm kiếm; "
                            "không xuất nhận định giá chưa được dẫn nguồn."
                        )
                    answer = _answer_with_sources(raw_answer, results)
                    status = "COMPLETED" if has_supported_result else "NO_RESULT"
                    model_name = resolved_model
                else:
                    answer = (
                        "KẾT QUẢ: CHƯA TÌM THẤY\n"
                        "Tavily không tìm thấy kết quả phù hợp trên web cho địa bàn và kỳ này. "
                        "Đây không chứng minh rằng không có thông tin hoặc tin rao."
                    )
                    status = "NO_RESULT"
                    model_name = None
                with connection:
                    connection.execute(
                        """UPDATE research_answer_jobs SET status=?,answer_text=?,chatbot='Gemma',
                           model_name=?,query_text=?,crawled_at=?,finished_at=?,error_text=NULL WHERE job_id=?""",
                        (status, answer, model_name, query_text, _now_utc(), _now_utc(), job["job_id"]),
                    )
                if status == "COMPLETED":
                    completed += 1
                else:
                    no_result += 1
            except Exception as exc:  # noqa: BLE001 - record only a redacted local diagnostic
                message = str(exc)
                for secret in (settings.search_api_key, settings.model_api_key):
                    if secret:
                        message = message.replace(secret, "[đã ẩn]")
                message = message[:1000]
                with connection:
                    connection.execute(
                        """UPDATE research_answer_jobs SET status='FAILED',finished_at=?,
                           error_text=? WHERE job_id=?""",
                        (_now_utc(), message, job["job_id"]),
                    )
                failed += 1
                if "429" in message:
                    break

        final_status = "COMPLETED_WITH_ERRORS" if failed else "COMPLETED"
        with connection:
            connection.execute(
                """UPDATE research_answer_runs SET finished_at=?,status=?,completed_count=?,
                   no_result_count=?,failed_count=? WHERE run_id=?""",
                (_now_utc(), final_status, completed, no_result, failed, run_id),
            )
        output_path = _export_jsonl(period, database_path=database_path)
        return {
            "status": final_status,
            "period": period,
            "run_id": run_id,
            "processed": completed + no_result + failed,
            "completed": completed,
            "no_result": no_result,
            "failed": failed,
            "job_counts": _status_counts(connection, period),
            "jsonl_path": str(output_path) if output_path else None,
            "network_attempted": True,
        }
    except Exception as exc:
        if run_id is not None and connection is not None:
            message = str(exc)
            for secret in (settings.search_api_key, settings.model_api_key):
                if secret:
                    message = message.replace(secret, "[đã ẩn]")
            message = message[:1000]
            with connection:
                connection.execute(
                    """UPDATE research_answer_runs SET finished_at=?,status='FAILED',
                       error_text=? WHERE run_id=?""",
                    (_now_utc(), message, run_id),
                )
        raise
    finally:
        if connection is not None:
            connection.close()
        _RUN_LOCK.release()
