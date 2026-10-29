"""Volume smoke test: throughput and memory with an instant fake LLM (measures our overhead)."""

import resource
import time

from support import GoodLLM
from support import answer_line, append
from pipeline.runner import Runner


def test_three_thousand_answers_complete_and_report_rates(cfg_factory, capsys):
    cfg = cfg_factory(processing={"batch_size": 50})
    r = Runner(cfg, llm_factory=lambda _c: GoodLLM())
    append(cfg.input_file, *(answer_line(i) for i in range(3000)))
    t0 = time.time()
    out = r.run_once("volume")
    dt = time.time() - t0
    assert (out["registered"], out["ok"], out["claims"]) == (3000, 3000, 3000)
    t1 = time.time()
    assert r.run_once("volume")["registered"] == 0          # unchanged file: instant
    idle = time.time() - t1
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"\nVOLUME 3000 answers: {dt:.1f}s ({3000/dt:.0f}/s), idle rescan {idle*1000:.0f} ms, peak RSS {rss_mb:.0f} MB")
    assert idle < 1.0
