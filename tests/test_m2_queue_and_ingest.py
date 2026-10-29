"""code_plan.md §10: schema, incremental, partial-write, duplicate, cross-month, retry, restart."""

import json

from claims_extractor.ingest import ingest_file
from claims_extractor.models import AnswerRecord
from claims_extractor.pipeline import process_pending
from claims_extractor import stats
from support import FakeLLM, claims_json, make_claim


def row(i=1, **extra):
    base = {"answer_id": f"a{i}", "crawled_at": "2026-10-28T10:00:00+07:00", "chatbot": "gemma",
            "query_text": "q", "answer_text": "Giá phổ biến 200 - 430 triệu/m² tại Bồ Đề"}
    base.update(extra)
    return json.dumps(base, ensure_ascii=False) + "\n"


def write(path, *lines, mode="a"):
    with open(path, mode, encoding="utf-8", newline="") as h:
        h.write("".join(lines))


def test_schema_valid_optional_missing_and_broken_line(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1), '{"chatbot": "x"}\n', "{broken\n",
          json.dumps({"crawled_at": "2026-10-28T10:00:00+07:00", "chatbot": "g",
                      "answer_text": "no ids, no query"}) + "\n")
    res = ingest_file(store, f)
    assert (res.registered, res.invalid) == (2, 2)
    assert len(stats.list_input_errors(store)) == 2


def test_incremental_reads_only_new_lines_and_checkpoint_survives_reopen(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1), row(2))
    assert ingest_file(store, f).registered == 2
    assert ingest_file(store, f).unchanged
    write(f, row(3))
    res = ingest_file(store, f)
    assert (res.registered, res.duplicates) == (1, 0)


def test_partial_last_line_is_not_processed_until_complete(tmp_path, store):
    f = tmp_path / "in.jsonl"
    full = row(2)
    write(f, row(1), full[:40])
    res = ingest_file(store, f)
    assert res.registered == 1 and res.waiting_bytes == 40
    write(f, full[40:])
    res = ingest_file(store, f)
    assert res.registered == 1 and res.waiting_bytes == 0 and res.invalid == 0


def test_duplicate_id_and_rescan_do_not_duplicate_but_conflicts_are_reported(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1), row(1))
    assert ingest_file(store, f).registered == 1
    assert ingest_file(store, f, rescan=True).registered == 0
    write(f, row(1, answer_text="a different text"))
    ingest_file(store, f)
    assert any(e["reason"] == "answer_id_conflict" for e in stats.list_input_errors(store))


def test_rewritten_file_triggers_rescan_without_duplicates(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1), row(2))
    ingest_file(store, f)
    write(f, row(1), row(2), row(3), mode="w")  # same head, bigger: plain append semantics
    assert ingest_file(store, f).registered == 1
    write(f, row(9), row(1), mode="w")  # replaced with other content, shorter
    assert ingest_file(store, f).registered == 1


def test_cross_month_same_text_is_two_observations(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    base = dict(answer_text="Giá 200 - 430 triệu/m²", query_text="q", chatbot="gemma")
    a = AnswerRecord(crawled_at="2026-10-01T00:00:00Z", target_month="2026-09", crawl_run_id="r1", **base)
    b = AnswerRecord(crawled_at="2026-11-01T00:00:00Z", target_month="2026-10", crawl_run_id="r2", **base)
    assert a.answer_id != b.answer_id
    write(f, *(json.dumps(x.model_dump(mode="json"), ensure_ascii=False) + "\n" for x in (a, b)))
    assert ingest_file(store, f).registered == 2
    process_pending(store, make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²")))))
    assert sorted(r["month"] for r in stats.quality(store)["by_month"]) == ["2026-09", "2026-10"]
    assert store.counts()["claims"] == 2


def test_bad_target_month_is_rejected_as_invalid_line(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1, target_month="10/2026"))
    assert ingest_file(store, f).invalid == 1


def test_retry_until_max_attempts_then_stays_failed(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1))
    ingest_file(store, f)
    ex = make_extractor(FakeLLM(RuntimeError("503")))
    for _ in range(5):
        process_pending(store, ex, max_attempts=3)
    r = store.query("SELECT status, attempt_count, last_error FROM answers")[0]
    assert (r["status"], r["attempt_count"]) == ("failed", 3) and "503" in r["last_error"]
    # recovers after reset + working LLM; no duplicated claims
    store.mark_pending(statuses=["failed"])
    process_pending(store, make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²")))))
    process_pending(store, make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²")))))
    assert store.counts()["claims"] == 1 and store.counts()["answers_failed"] == 0


def test_failure_in_one_call_is_not_retried_in_same_call(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1))
    ingest_file(store, f)
    llm = FakeLLM(RuntimeError("down"))
    s = process_pending(store, make_extractor(llm), max_attempts=3)
    assert (s.processed, s.failed) == (1, 1) and len(llm.calls) == 1


def test_restart_recovers_interrupted_rows(tmp_path, store):
    f = tmp_path / "in.jsonl"
    write(f, row(1), row(2))
    ingest_file(store, f)
    store.claim_batch(5)  # simulate a crash while both were 'processing'
    assert store.recover_interrupted() == 2
    assert stats.status_counts(store)["pending"] == 2


def test_graceful_stop_releases_unprocessed_rows_without_spending_attempts(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1), row(2), row(3))
    ingest_file(store, f)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2  # allow the first answer only
    s = process_pending(store, make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²")))),
                        batch_size=3, should_stop=stop)
    assert s.stopped and s.processed == 1
    left = store.query("SELECT status, attempt_count FROM answers WHERE status != 'ok'")
    assert [(r["status"], r["attempt_count"]) for r in left] == [("pending", 0), ("pending", 0)]


def test_reprocess_keeps_history_and_stale_version_selection(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1))
    ingest_file(store, f)
    ex = make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²"))))
    process_pending(store, ex)
    assert store.mark_pending(stale_version=ex.version) == 0  # current version: nothing stale
    assert store.mark_pending(stale_version="old-version") == 1
    process_pending(store, ex)
    assert store.counts()["claims"] == 1
    assert store.query("SELECT COUNT(*) n FROM claims_history")[0]["n"] == 1
    assert store.query("SELECT reprocess_count r FROM answers")[0]["r"] == 1


def test_failed_reprocess_keeps_earlier_claims(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1))
    ingest_file(store, f)
    process_pending(store, make_extractor(FakeLLM(claims_json(make_claim(quote="200 - 430 triệu/m²")))))
    store.mark_pending(statuses=["ok"])
    process_pending(store, make_extractor(FakeLLM(RuntimeError("down"))))
    assert store.counts()["claims"] == 1


def test_worker_lock_is_exclusive_and_stale_lock_is_taken_over(store):
    assert store.acquire_lock("A")
    assert not store.acquire_lock("B")
    assert store.acquire_lock("A")  # re-entrant for the owner
    store.release_lock("A")
    assert store.acquire_lock("B")
    store._conn.execute("UPDATE worker_lock SET heartbeat_at = '2000-01-01T00:00:00+00:00'")
    assert store.acquire_lock("C", stale_after_s=60)


def test_no_result_answers_skip_the_llm(tmp_path, store, make_extractor):
    f = tmp_path / "in.jsonl"
    write(f, row(1, answer_text="KẾT QUẢ: CHƯA TÌM THẤY\nTavily không tìm thấy.\n\nNguồn tìm kiếm (Tavily):"))
    ingest_file(store, f)
    llm = FakeLLM(claims_json(make_claim()))
    s = process_pending(store, make_extractor(llm))
    assert s.empty == 1 and not llm.calls and s.llm_calls == 0
    assert store.query("SELECT note FROM answers")[0]["note"] == "no_result_declared"


def test_v1_database_is_migrated(tmp_path):
    import sqlite3
    from claims_extractor.store import ClaimStore
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE answers (answer_id TEXT PRIMARY KEY, crawled_at TEXT NOT NULL,
      chatbot TEXT NOT NULL, model_name TEXT, query_text TEXT NOT NULL, answer_text TEXT NOT NULL,
      domain TEXT NOT NULL, extract_status TEXT NOT NULL, extractor_model TEXT NOT NULL,
      prompt_hash TEXT NOT NULL, extracted_at TEXT NOT NULL, error TEXT);
      CREATE TABLE claims (claim_id TEXT PRIMARY KEY, answer_id TEXT NOT NULL REFERENCES answers(answer_id),
      domain TEXT NOT NULL, confidence_flag TEXT, data TEXT NOT NULL);
      INSERT INTO answers VALUES ('x','2026-10-01','g',NULL,'q','t','real_estate','ok','m','h','2026-10-02',NULL);
      INSERT INTO claims VALUES ('c1','x','real_estate','ok','{}');""")
    con.commit(); con.close()
    with ClaimStore(db) as s:
        assert s.query("SELECT status FROM answers")[0]["status"] == "ok"
        assert s.counts()["claims"] == 1
