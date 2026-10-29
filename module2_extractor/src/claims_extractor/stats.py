"""Read-only monitoring queries over the claim store (used by the ops UI and the CLI).

Everything here answers "is module 2 running well?": queue health, extraction outcomes,
verification rejections, flags, latency, per-month and per-run trends, plus threshold alerts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .store import ClaimStore


@dataclass(frozen=True)
class Thresholds:
    """Alert limits (fractions). Starting values to tune, not benchmarked numbers."""

    failed_rate: float = 0.10
    rejected_rate: float = 0.25
    flagged_rate: float = 0.30
    empty_rate: float = 0.60
    min_sample: int = 20  # no rate alerts below this many finished answers / claims


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def status_counts(store: ClaimStore) -> dict[str, int]:
    counts = {s: 0 for s in ("pending", "processing", "ok", "empty", "failed")}
    for row in store.query("SELECT status, COUNT(*) n FROM answers GROUP BY status"):
        counts[row["status"]] = row["n"]
    counts["total"] = sum(counts.values())
    return counts


def overview(store: ClaimStore, *, max_attempts: int = 3) -> dict[str, Any]:
    one = lambda sql, *p: store.query(sql, p)[0]["n"]  # noqa: E731
    return {
        "status": status_counts(store),
        "claims": one("SELECT COUNT(*) n FROM claims"),
        "rejected": one("SELECT COUNT(*) n FROM rejected"),
        "input_errors": one("SELECT COUNT(*) n FROM input_errors"),
        "failed_exhausted": one(
            "SELECT COUNT(*) n FROM answers WHERE status='failed' AND attempt_count >= ?",
            max_attempts),
        "last_processed_at": store.query("SELECT MAX(processed_at) v FROM answers")[0]["v"],
        "last_registered_at": store.query("SELECT MAX(registered_at) v FROM answers")[0]["v"],
    }


def quality(
    store: ClaimStore,
    *,
    current_version: str | None = None,
    max_attempts: int = 3,
    thresholds: Thresholds = Thresholds(),
) -> dict[str, Any]:
    st = status_counts(store)
    finished = st["ok"] + st["empty"] + st["failed"]
    claims_total = store.query("SELECT COUNT(*) n FROM claims")[0]["n"]
    rejected_total = store.query("SELECT COUNT(*) n FROM rejected")[0]["n"]
    flagged = store.query(
        "SELECT COUNT(*) n FROM claims WHERE confidence_flag IN ('ambiguous','implausible')"
    )[0]["n"]

    empty_declared = store.query(
        "SELECT COUNT(*) n FROM answers WHERE status='empty' AND note='no_result_declared'"
    )[0]["n"]
    durations = [r["duration_ms"] for r in store.query(
        "SELECT duration_ms FROM answers WHERE duration_ms IS NOT NULL AND note IS NULL "
        "AND status IN ('ok','empty')")]
    with_source = store.query(
        "SELECT COUNT(*) n FROM claims WHERE json_array_length(json_extract(data,'$.source_urls')) > 0"
    )[0]["n"]

    def dist(expr: str) -> dict[str, int]:
        rows = store.query(
            f"SELECT COALESCE({expr}, '(trống)') k, COUNT(*) n FROM claims GROUP BY k ORDER BY n DESC")
        return {r["k"]: r["n"] for r in rows}

    flag_reasons = {r["k"]: r["n"] for r in store.query(
        "SELECT j.value k, COUNT(*) n FROM claims, json_each(json_extract(claims.data,'$.flag_reasons')) j "
        "GROUP BY k ORDER BY n DESC")}
    rejected_reasons = {r["k"]: r["n"] for r in store.query(
        "SELECT reason k, COUNT(*) n FROM rejected GROUP BY reason ORDER BY n DESC")}
    errors = store.query(
        "SELECT SUBSTR(last_error, 1, 160) error, COUNT(*) n FROM answers WHERE status='failed' "
        "GROUP BY error ORDER BY n DESC LIMIT 8")

    by_month = store.query(
        """SELECT COALESCE(a.target_month, '(không rõ)') month, COUNT(*) answers,
                  SUM(a.status='ok') ok, SUM(a.status='empty') empty, SUM(a.status='failed') failed,
                  SUM(a.status IN ('pending','processing')) waiting,
                  (SELECT COUNT(*) FROM claims c WHERE COALESCE(c.target_month,'(không rõ)') =
                       COALESCE(a.target_month,'(không rõ)')) claims,
                  (SELECT COUNT(*) FROM claims c WHERE COALESCE(c.target_month,'(không rõ)') =
                       COALESCE(a.target_month,'(không rõ)')
                       AND c.confidence_flag != 'ok') flagged
           FROM answers a GROUP BY month ORDER BY month DESC""")
    by_chatbot = store.query(
        """SELECT chatbot, COUNT(*) answers, SUM(status='ok') ok, SUM(status='empty') empty,
                  SUM(status='failed') failed FROM answers GROUP BY chatbot ORDER BY answers DESC""")
    versions = store.query(
        "SELECT COALESCE(extractor_version,'(không rõ)') version, COUNT(*) n FROM answers "
        "WHERE status IN ('ok','empty') GROUP BY version ORDER BY n DESC")
    stale = 0
    if current_version:
        stale = store.query(
            "SELECT COUNT(*) n FROM answers WHERE status IN ('ok','empty') "
            "AND COALESCE(extractor_version,'') != ?", (current_version,))[0]["n"]
    retried = store.query("SELECT COUNT(*) n FROM answers WHERE attempt_count > 1")[0]["n"]
    exhausted = store.query(
        "SELECT COUNT(*) n FROM answers WHERE status='failed' AND attempt_count >= ?",
        (max_attempts,))[0]["n"]

    rates = {
        "failed": _rate(st["failed"], finished),
        "empty": _rate(st["empty"], finished),
        "ok": _rate(st["ok"], finished),
        "rejected": _rate(rejected_total, claims_total + rejected_total),
        "flagged": _rate(flagged, claims_total),
        "with_source": _rate(with_source, claims_total),
    }
    result = {
        "finished_answers": finished,
        "rates": rates,
        "claims": claims_total,
        "rejected": rejected_total,
        "flagged": flagged,
        "claims_per_ok_answer": round(claims_total / st["ok"], 2) if st["ok"] else None,
        "empty_declared_no_result": empty_declared,
        "latency_ms": {
            "avg": int(sum(durations) / len(durations)) if durations else None,
            "p50": _percentile(durations, 0.5),
            "p95": _percentile(durations, 0.95),
            "samples": len(durations),
        },
        "distributions": {
            "confidence_flag": dist("confidence_flag"),
            "property_type": dist("json_extract(data,'$.property_type')"),
            "price_basis": dist("json_extract(data,'$.price_basis')"),
            "metric": dist("json_extract(data,'$.metric')"),
            "chatbot": dist("json_extract(data,'$.chatbot')"),
        },
        "flag_reasons": flag_reasons,
        "rejected_reasons": rejected_reasons,
        "top_errors": errors,
        "by_month": by_month,
        "by_chatbot": by_chatbot,
        "extractor_versions": versions,
        "stale_answers": stale,
        "current_version": current_version,
        "retried_answers": retried,
        "failed_exhausted": exhausted,
    }
    result["alerts"] = _alerts(result, st, thresholds)
    return result


def _alerts(q: dict[str, Any], st: dict[str, int], t: Thresholds) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []

    def add(level: str, code: str, message: str) -> None:
        out.append({"level": level, "code": code, "message": message})

    pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
    r = q["rates"]
    if q["finished_answers"] >= t.min_sample:
        if r["failed"] is not None and r["failed"] > t.failed_rate:
            add("error", "high_failed_rate", f"Tỉ lệ answer lỗi {pct(r['failed'])} (ngưỡng {pct(t.failed_rate)}): "
                "kiểm tra endpoint/API key hoặc định dạng trả về của LLM.")
        if r["empty"] is not None and r["empty"] > t.empty_rate:
            add("warn", "high_empty_rate", f"{pct(r['empty'])} answer không có claim (ngưỡng {pct(t.empty_rate)}): "
                "có thể do nhiều câu 'chưa tìm thấy' hoặc prompt bỏ sót.")
    if q["claims"] + q["rejected"] >= t.min_sample:
        if r["rejected"] is not None and r["rejected"] > t.rejected_rate:
            add("error", "high_rejected_rate", f"{pct(r['rejected'])} claim bị code loại (ngưỡng {pct(t.rejected_rate)}): "
                "xem 'Lý do loại' — thường là quote không khớp văn bản hoặc sai schema.")
        if r["flagged"] is not None and q["claims"] >= t.min_sample and r["flagged"] > t.flagged_rate:
            add("warn", "high_flagged_rate", f"{pct(r['flagged'])} claim bị gắn cờ (ngưỡng {pct(t.flagged_rate)}).")
    if q["failed_exhausted"]:
        add("error", "failed_exhausted", f"{q['failed_exhausted']} answer lỗi đã hết số lần thử; "
            "cần 'Thử lại lỗi' (đặt lại số lần) sau khi sửa nguyên nhân.")
    if q["stale_answers"]:
        add("info", "stale_extractor", f"{q['stale_answers']} answer được trích bằng phiên bản prompt/logic cũ; "
            "dùng 'Xử lý lại (bản cũ)' nếu muốn cập nhật.")
    if st["pending"] and st["processing"] == 0 and st["pending"] > 0:
        add("info", "queue_waiting", f"{st['pending']} answer đang chờ xử lý.")
    return out


# ---- token usage & cost ----------------------------------------------------------------


def cost_of(prompt_tokens: int, completion_tokens: int,
            input_per_1m: float | None, output_per_1m: float | None) -> float | None:
    """Money for the tokens, or None when prices are not configured (never guessed)."""
    if input_per_1m is None or output_per_1m is None:
        return None
    return round((prompt_tokens * input_per_1m + completion_tokens * output_per_1m) / 1_000_000, 6)


def usage_report(store: ClaimStore, *, input_per_1m: float | None = None,
                 output_per_1m: float | None = None) -> dict[str, Any]:
    """Tokens (and cost, if prices are given) spent by extraction: total, per month, per run."""
    add_cost = lambda row: {**row, "cost": cost_of(  # noqa: E731
        row["prompt_tokens"], row["completion_tokens"], input_per_1m, output_per_1m)}
    total = store.query(
        """SELECT COUNT(*) answers, COALESCE(SUM(llm_calls),0) llm_calls,
                  COALESCE(SUM(prompt_tokens),0) prompt_tokens,
                  COALESCE(SUM(completion_tokens),0) completion_tokens,
                  COALESCE(SUM(usage_missing_calls),0) usage_missing_calls,
                  COALESCE(SUM(llm_calls = 0 AND status IN ('ok','empty')),0) answers_without_llm
           FROM answers""")[0]
    by_month = store.query(
        """SELECT COALESCE(target_month,'(không rõ)') month, COUNT(*) answers,
                  SUM(llm_calls) llm_calls, SUM(prompt_tokens) prompt_tokens,
                  SUM(completion_tokens) completion_tokens
           FROM answers GROUP BY month ORDER BY month DESC""")
    runs = store.query(
        """SELECT run_id, trigger, started_at, status, processed, llm_calls, prompt_tokens,
                  completion_tokens, usage_missing_calls FROM run_log ORDER BY run_id DESC LIMIT 30""")
    billed = total["answers"] - total["answers_without_llm"]
    total = add_cost(total)
    total["tokens"] = total["prompt_tokens"] + total["completion_tokens"]
    total["avg_tokens_per_llm_call"] = (
        int(total["tokens"] / total["llm_calls"]) if total["llm_calls"] else None)
    total["avg_cost_per_answer"] = (
        round(total["cost"] / billed, 6) if total["cost"] is not None and billed else None)
    return {
        "total": total,
        "by_month": [add_cost(r) for r in by_month],
        "by_run": [add_cost(r) for r in runs],
        "prices_configured": input_per_1m is not None and output_per_1m is not None,
    }


# ---- listings ------------------------------------------------------------------------


def list_answers(
    store: ClaimStore, *, status: str | None = None, target_month: str | None = None,
    chatbot: str | None = None, search: str | None = None, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    if target_month:
        where.append("target_month = ?")
        params.append(target_month)
    if chatbot:
        where.append("chatbot = ?")
        params.append(chatbot)
    if search:
        where.append("(query_text LIKE ? OR answer_id = ?)")
        params += [f"%{search}%", search]
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = store.query(f"SELECT COUNT(*) n FROM answers{clause}", params)[0]["n"]
    rows = store.query(
        f"""SELECT answer_id, target_month, crawl_run_id, crawled_at, chatbot, status, attempt_count,
                   substr(last_error,1,200) last_error, note, extractor_version, duration_ms,
                   reprocess_count, processed_at, substr(query_text,1,160) query_text,
                   (SELECT COUNT(*) FROM claims c WHERE c.answer_id = answers.answer_id) claims,
                   (SELECT COUNT(*) FROM rejected r WHERE r.answer_id = answers.answer_id) rejected
            FROM answers{clause} ORDER BY rowid DESC LIMIT ? OFFSET ?""",
        [*params, max(1, min(limit, 500)), max(0, offset)])
    return {"total": total, "rows": rows}


def answer_detail(store: ClaimStore, answer_id: str) -> dict[str, Any] | None:
    rows = store.query("SELECT * FROM answers WHERE answer_id = ?", (answer_id,))
    if not rows:
        return None
    detail = rows[0]
    detail["claims"] = [json.loads(r["data"]) for r in store.query(
        "SELECT data FROM claims WHERE answer_id = ? ORDER BY rowid", (answer_id,))]
    detail["rejected_items"] = [
        {"reason": r["reason"], **json.loads(r["data"])} for r in store.query(
            "SELECT reason, data FROM rejected WHERE answer_id = ? ORDER BY id", (answer_id,))]
    detail["history_count"] = store.query(
        "SELECT COUNT(*) n FROM claims_history WHERE answer_id = ?", (answer_id,))[0]["n"]
    return detail


def list_claims(
    store: ClaimStore, *, target_month: str | None = None, flag: str | None = None,
    property_type: str | None = None, search: str | None = None, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    where, params = [], []
    if target_month:
        where.append("target_month = ?")
        params.append(target_month)
    if flag:
        where.append("confidence_flag = ?")
        params.append(flag)
    if property_type:
        where.append("json_extract(data,'$.property_type') = ?")
        params.append(property_type)
    if search:
        where.append("(json_extract(data,'$.ward') LIKE ? OR json_extract(data,'$.district') LIKE ? "
                     "OR json_extract(data,'$.street') LIKE ?)")
        params += [f"%{search}%"] * 3
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = store.query(f"SELECT COUNT(*) n FROM claims{clause}", params)[0]["n"]
    rows = store.query(
        f"SELECT data FROM claims{clause} ORDER BY rowid DESC LIMIT ? OFFSET ?",
        [*params, max(1, min(limit, 500)), max(0, offset)])
    return {"total": total, "rows": [json.loads(r["data"]) for r in rows]}


def list_input_errors(store: ClaimStore, limit: int = 100) -> list[dict[str, Any]]:
    return store.query(
        "SELECT id, source_file, position, reason, snippet, seen_at FROM input_errors "
        "ORDER BY id DESC LIMIT ?", (limit,))


def list_runs(store: ClaimStore, limit: int = 30) -> list[dict[str, Any]]:
    rows = store.query("SELECT * FROM run_log ORDER BY run_id DESC LIMIT ?", (limit,))
    for row in rows:
        done = row["processed"]
        row["failed_rate"] = _rate(row["failed"], done)
        row["rejected_rate"] = _rate(row["rejected"], row["claims"] + row["rejected"])
    return rows
