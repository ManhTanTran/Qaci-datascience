import time

import pytest
from fastapi.testclient import TestClient

from support import GoodLLM
from support import answer_line, append
from pipeline.runner import Runner
from pipeline.web.app import create_app

H = {"X-Requested-With": "ops-ui"}


@pytest.fixture()
def client(cfg):
    runner = Runner(cfg, llm_factory=lambda _c: GoodLLM())
    with TestClient(create_app(cfg, runner)) as c:
        c.runner = runner
        yield c


def wait_idle(client, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if not client.get("/api/v1/extract-claims/status").json()["worker"]["progress"]["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_page_and_status_before_any_data(client):
    assert "Module 2" in client.get("/extract-claims").text
    s = client.get("/api/v1/extract-claims/status").json()
    assert s["mode"] == "manual" and s["overview"]["status"]["total"] == 0
    assert s["input_file"]["exists"] is False


def test_post_requires_ui_header(client):
    assert client.post("/api/v1/extract-claims/run", json={}).status_code == 403


def test_run_from_ui_then_read_quality_answers_claims_export(client, cfg):
    append(cfg.input_file, *(answer_line(i) for i in range(1, 8)), "{broken\n")
    assert client.post("/api/v1/extract-claims/run", json={"limit": 5}, headers=H).json()["started"]
    wait_idle(client)
    st = client.get("/api/v1/extract-claims/status").json()
    assert st["overview"]["status"]["ok"] == 5 and st["overview"]["status"]["pending"] == 2
    assert st["overview"]["input_errors"] == 1 and st["last_run"]["status"] == "completed"

    client.post("/api/v1/extract-claims/run", json={}, headers=H)
    wait_idle(client)
    q = client.get("/api/v1/extract-claims/quality").json()
    assert q["claims"] == 7 and q["rates"]["ok"] == 1.0 and q["by_month"][0]["month"] == "2026-10"

    rows = client.get("/api/v1/extract-claims/answers", params={"status": "ok", "limit": 3}).json()
    assert rows["total"] == 7 and len(rows["rows"]) == 3
    detail = client.get(f"/api/v1/extract-claims/answers/{rows['rows'][0]['answer_id']}").json()
    assert detail["claims"][0]["source_urls"] and "Giá phổ biến" in detail["answer_text"]
    assert client.get("/api/v1/extract-claims/answers/nope").status_code == 404
    assert client.get("/api/v1/extract-claims/claims", params={"month": "2026-10"}).json()["total"] == 7
    assert client.get("/api/v1/extract-claims/answers", params={"status": "bogus"}).status_code == 400
    csv = client.get("/api/v1/extract-claims/export", params={"format": "csv", "month": "2026-10"})
    assert csv.status_code == 200 and csv.text.count("\n") == 8  # header + 7
    assert len(client.get("/api/v1/extract-claims/input-errors").json()) == 1
    assert client.get("/api/v1/extract-claims/runs").json()[0]["processed"] == 2


def test_reprocess_and_retry_actions_and_validation(client, cfg):
    append(cfg.input_file, answer_line(1))
    client.post("/api/v1/extract-claims/run", json={}, headers=H)
    wait_idle(client)
    assert client.post("/api/v1/extract-claims/reprocess", json={}, headers=H).status_code == 400
    assert client.post("/api/v1/extract-claims/reprocess", json={"target_month": "10/2026"}, headers=H).status_code == 422
    r = client.post("/api/v1/extract-claims/reprocess", json={"answer_ids": ["id00001"], "run": False}, headers=H).json()
    assert r["requeued"] == 1
    assert client.get("/api/v1/extract-claims/status").json()["overview"]["status"]["pending"] == 1
    assert client.post("/api/v1/extract-claims/retry-failed", headers=H).json()["requeued"] == 0


def test_second_run_while_busy_gets_409(client, cfg):
    import threading
    gate = threading.Event()

    class Slow(GoodLLM):
        def complete(self, s, u):
            gate.wait(5)
            return super().complete(s, u)
    client.app.state.service.runner._llm_factory = lambda _c: Slow()
    append(cfg.input_file, answer_line(1))
    assert client.post("/api/v1/extract-claims/run", json={}, headers=H).status_code == 200
    time.sleep(0.3)
    assert client.post("/api/v1/extract-claims/run", json={}, headers=H).status_code == 409
    assert client.get("/api/v1/extract-claims/status").json()["worker"]["progress"]["running"]
    client.post("/api/v1/extract-claims/stop", headers=H)
    gate.set()
    wait_idle(client)


def test_auto_switch_from_ui_processes_new_data(cfg_factory):
    cfg = cfg_factory()
    runner = Runner(cfg, llm_factory=lambda _c: GoodLLM())
    with TestClient(create_app(cfg, runner)) as c:
        assert c.post("/api/v1/extract-claims/auto", json={"enabled": True}, headers=H).json()["auto"]
        append(cfg.input_file, answer_line(1), answer_line(2))
        end = time.time() + 10
        while time.time() < end and c.get("/api/v1/extract-claims/status").json()["overview"]["status"]["ok"] < 2:
            time.sleep(0.1)
        assert c.get("/api/v1/extract-claims/status").json()["overview"]["status"]["ok"] == 2
        assert not c.post("/api/v1/extract-claims/auto", json={"enabled": False}, headers=H).json()["auto"]


def test_mode_switch_can_be_locked_by_config(cfg_factory):
    cfg = cfg_factory(ui={"allow_mode_switch": False})
    with TestClient(create_app(cfg, Runner(cfg, llm_factory=lambda _c: GoodLLM()))) as c:
        assert c.post("/api/v1/extract-claims/auto", json={"enabled": True}, headers=H).status_code == 403


def test_html_in_answers_is_stored_verbatim_for_ui_to_escape(client, cfg):
    append(cfg.input_file, answer_line(1, text='<img src=x onerror=alert(1)> giá 200 - 430 triệu/m² tại P1'))
    client.post("/api/v1/extract-claims/run", json={}, headers=H)
    wait_idle(client)
    d = client.get("/api/v1/extract-claims/answers/id00001").json()
    assert "<img" in d["answer_text"]          # raw data untouched; app.js renders it through esc()
    js = open(client.app.state.service.config.root.parent.parent.parent if False else
              __import__("pipeline.web.app", fromlist=["STATIC"]).STATIC / "app.js", encoding="utf-8").read()
    assert "innerHTML" in js and "const esc" in js


def test_one_app_serves_module1_and_module2(client):
    assert client.get("/api/v1/research-answers/config").status_code == 200   # module 1 route
    assert client.get("/research-answers").status_code == 200                  # module 1 page
    html1 = client.get("/research-answers").text
    assert 'href="/extract-claims"' in html1                                    # tab to module 2
    html2 = client.get("/extract-claims").text
    assert 'href="/research-answers"' in html2 and "/extract-assets/app.js" in html2
    assert client.get("/extract-assets/app.js").status_code == 200


def test_usage_endpoints_for_both_modules(cfg_factory):
    cfg = cfg_factory(cost={"currency": "USD", "module1": {"search_per_call": 0.008,
                      "model_input_per_1m": 1.0, "model_output_per_1m": 2.0},
                      "module2": {"input_per_1m": 1.0, "output_per_1m": 4.0}})
    runner = Runner(cfg, llm_factory=lambda _c: GoodLLM())
    with TestClient(create_app(cfg, runner)) as c:
        append(cfg.input_file, answer_line(1), answer_line(2),
               answer_line(3, text="KẾT QUẢ: CHƯA TÌM THẤY\nkhông có"))
        c.post("/api/v1/extract-claims/run", json={}, headers=H)
        wait_idle(c)
        u = c.get("/api/v1/extract-claims/usage").json()
        assert u["total"]["llm_calls"] == 2 and u["total"]["prompt_tokens"] == 200
        assert u["total"]["completion_tokens"] == 40 and u["total"]["answers_without_llm"] == 1
        assert u["total"]["cost"] == round((200 * 1.0 + 40 * 4.0) / 1e6, 6)
        assert u["by_run"][0]["prompt_tokens"] == 200 and u["by_month"][0]["month"] == "2026-10"
        m1 = c.get("/api/v1/research-answers/usage").json()
        assert m1["total"]["jobs"] == 0 and m1["prices_configured"] is True
        assert c.get("/api/v1/research-answers/usage?period=10-2026").status_code == 422


def test_prices_not_configured_shows_tokens_but_no_cost(client, cfg):
    append(cfg.input_file, answer_line(1))
    client.post("/api/v1/extract-claims/run", json={}, headers=H)
    wait_idle(client)
    u = client.get("/api/v1/extract-claims/usage").json()
    assert u["total"]["tokens"] == 120 and u["total"]["cost"] is None and not u["prices_configured"]
