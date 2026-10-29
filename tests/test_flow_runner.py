import threading
import time

import pytest

from claims_extractor import stats
from support import answer_line, append
from support import FlakyLLM, GoodLLM
from pipeline.runner import Runner, WorkerBusy
from pipeline.watcher import InputWatcher


def make_runner(cfg, llm):
    return Runner(cfg, llm_factory=lambda _c: llm)


def test_incremental_run_processes_each_answer_exactly_once(cfg):
    llm = GoodLLM()
    r = make_runner(cfg, llm)
    append(cfg.input_file, *(answer_line(i) for i in range(1, 4)))
    first = r.run_once("test")
    assert (first["registered"], first["processed"], first["ok"], first["claims"]) == (3, 3, 3, 3)
    append(cfg.input_file, answer_line(4))
    second = r.run_once("test")
    assert (second["registered"], second["processed"]) == (1, 1)
    third = r.run_once("test")
    assert (third["registered"], third["processed"]) == (0, 0) and llm.calls == 4


def test_partial_write_is_not_processed(cfg):
    r = make_runner(cfg, GoodLLM())
    line = answer_line(2)
    append(cfg.input_file, answer_line(1), line[:50])
    assert r.run_once("test")["processed"] == 1
    append(cfg.input_file, line[50:])
    out = r.run_once("test")
    assert (out["registered"], out["processed"], out["invalid_lines"]) == (1, 1, 0)


def test_duplicate_answer_id_creates_no_duplicate_claims(cfg):
    r = make_runner(cfg, GoodLLM())
    append(cfg.input_file, answer_line(1), answer_line(1))
    r.run_once("test")
    append(cfg.input_file, answer_line(1))
    r.run_once("test", rescan=True)
    with r.open_store() as s:
        assert s.counts() == {"answers": 1, "answers_failed": 0, "claims": 1, "rejected": 0}


def test_cross_month_same_question_is_new_observation(cfg):
    r = make_runner(cfg, GoodLLM())
    same = "Giá phổ biến 200 - 430 triệu/m² tại P1"
    append(cfg.input_file,
           answer_line(1, "2026-09", text=same, answer_id=None, crawl_run_id="r-sep"),
           answer_line(2, "2026-10", text=same, answer_id=None, crawl_run_id="r-oct"))
    out = r.run_once("test")
    assert out["registered"] == 2 and out["claims"] == 2


def test_retry_then_recovery_without_duplicates(cfg):
    llm = FlakyLLM(fail_first=2)
    r = make_runner(cfg, llm)
    append(cfg.input_file, answer_line(1), answer_line(2))
    first = r.run_once("test")
    assert first["failed"] == 2 and first["status"] == "completed_with_errors"
    second = r.run_once("test")  # LLM healthy now; failed answers are retried
    assert (second["ok"], second["failed"]) == (2, 0)
    with r.open_store() as s:
        assert s.counts()["claims"] == 2
        assert {row["attempt_count"] for row in s.query("SELECT attempt_count FROM answers")} == {2}


def test_failed_answers_stop_being_retried_after_max_retries(cfg):
    r = make_runner(cfg, FlakyLLM(fail_first=99))
    append(cfg.input_file, answer_line(1))
    for _ in range(5):
        r.run_once("test")
    with r.open_store() as s:
        row = s.query("SELECT status, attempt_count FROM answers")[0]
        assert (row["status"], row["attempt_count"]) == ("failed", 3)
        assert stats.overview(s, max_attempts=3)["failed_exhausted"] == 1


def test_restart_continues_from_saved_state(cfg):
    r = make_runner(cfg, GoodLLM())
    append(cfg.input_file, *(answer_line(i) for i in range(1, 8)))
    # a run that is killed after 3 answers: simulate with the stop flag and an abandoned claim
    calls = {"n": 0}
    orig = r.state.stop_requested
    r.state.stop_requested = lambda: (calls.__setitem__("n", calls["n"] + 1) or calls["n"] > 4)
    stopped = r.run_once("test")
    assert stopped["status"] == "stopped" and 0 < stopped["processed"] < 7
    # hard crash: rows left in 'processing' + a dangling run + a stale lock
    with r.open_store() as s:
        s.claim_batch(2)
        s.start_run("crash", "manual", "x", "v")
        s.acquire_lock("dead-owner")
        s._conn.execute("UPDATE worker_lock SET heartbeat_at='2000-01-01T00:00:00+00:00'")
    r.state.stop_requested = orig
    fresh = make_runner(cfg, GoodLLM())  # "restarted process"
    out = fresh.run_once("test")
    assert out["status"] == "completed"
    with fresh.open_store() as s:
        assert stats.status_counts(s)["ok"] == 7 and s.counts()["claims"] == 7
        assert s.query("SELECT COUNT(*) n FROM run_log WHERE status='aborted'")[0]["n"] == 1


def test_only_one_worker_at_a_time(cfg):
    gate, entered = threading.Event(), threading.Event()

    class Slow(GoodLLM):
        def complete(self, s, u):
            entered.set()
            gate.wait(5)
            return super().complete(s, u)

    r1, r2 = make_runner(cfg, Slow()), make_runner(cfg, GoodLLM())
    append(cfg.input_file, answer_line(1))
    t = threading.Thread(target=r1.run_once, args=("a",))
    t.start()
    assert entered.wait(5)
    with pytest.raises(WorkerBusy):
        r2.run_once("b")           # a second process-like runner is refused
    with pytest.raises(WorkerBusy):
        r1.run_once("c")           # and so is a second run in the same process
    gate.set()
    t.join(5)
    assert make_runner(cfg, GoodLLM()).run_once("d")["status"] == "completed"


def test_missing_api_key_is_reported_not_crashing(cfg, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    append(cfg.input_file, answer_line(1))
    out = Runner(cfg).run_once("test")
    assert out["status"] == "failed" and "OPENAI_API_KEY" in out["error"]
    with Runner(cfg).open_store() as s:
        assert stats.status_counts(s)["pending"] == 1  # nothing lost


def test_missing_input_file_is_not_an_error(cfg):
    assert make_runner(cfg, GoodLLM()).run_once("test")["status"] == "completed"


def test_watcher_requires_stable_signature(tmp_path):
    f = tmp_path / "x.jsonl"
    w = InputWatcher(f, stable_checks=2)
    assert not w.poll()                    # no file
    f.write_text("a\n")
    assert not w.poll() and w.poll()       # needs two identical polls
    w.mark_handled()
    assert not w.poll()
    f.write_text("a\nb\n")
    assert not w.poll()
    f.write_text("a\nb\nc\n")              # still changing: streak restarts
    assert not w.poll() and w.poll()


def test_auto_mode_picks_up_new_data_and_stops_cleanly(cfg_factory):
    cfg = cfg_factory(mode="auto")
    r = make_runner(cfg, GoodLLM())
    stop = threading.Event()
    th = threading.Thread(target=r.watch, args=(stop,))
    th.start()
    try:
        append(cfg.input_file, answer_line(1), answer_line(2))
        deadline = time.time() + 10
        while time.time() < deadline:
            with r.open_store() as s:
                if stats.status_counts(s)["ok"] == 2:
                    break
            time.sleep(0.1)
        append(cfg.input_file, answer_line(3))
        deadline = time.time() + 10
        while time.time() < deadline:
            with r.open_store() as s:
                if stats.status_counts(s)["ok"] == 3:
                    break
            time.sleep(0.1)
        with r.open_store() as s:
            assert stats.status_counts(s)["ok"] == 3 and s.counts()["claims"] == 3
    finally:
        stop.set()
        th.join(5)
    assert not th.is_alive()
