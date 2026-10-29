import csv
import json

from claims_extractor.cli import main
from claims_extractor.export import export_csv, export_jsonl
from claims_extractor.io import read_answers
from claims_extractor.pipeline import run_pipeline
from support import FakeLLM, claims_json, make_claim


def test_read_answers_tolerates_blank_lines_and_reports_bad_ones(tmp_path, answers_file):
    with answers_file.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
        handle.write(json.dumps({"chatbot": "gemini", "answer_text": "x"}) + "\n")  # no crawled_at
    records, problems = read_answers(answers_file)
    assert len(records) == 2 and len(problems) == 2
    assert all(len(r.answer_id) == 32 for r in records)
    assert records[0].answer_id != records[1].answer_id


def test_read_answers_accepts_json_array_and_single_object(tmp_path):
    row = {"crawled_at": "2026-10-26T09:00:00+07:00", "chatbot": "gemini", "answer_text": "a"}
    (tmp_path / "list.json").write_text(json.dumps([row, row]))
    (tmp_path / "one.json").write_text(json.dumps(row))
    assert len(read_answers(tmp_path / "list.json")[0]) == 2
    assert len(read_answers(tmp_path / "one.json")[0]) == 1


def test_pipeline_is_idempotent(answers_file, store, make_extractor):
    llm = FakeLLM(claims_json(make_claim()))
    extractor = make_extractor(llm)
    first = run_pipeline(answers_file, store, extractor)
    assert (first.processed, first.ok, first.claims) == (2, 2, 2)  # one claim per answer

    second = run_pipeline(answers_file, store, extractor)
    assert second.processed == 0  # file unchanged: nothing new, nothing pending
    assert len(llm.calls) == 2
    assert store.counts()["claims"] == 2


def test_failed_answers_are_retried_and_force_replaces_rows(answers_file, store, make_extractor):
    llm = FakeLLM("garbage", "garbage", claims_json(make_claim()))
    extractor = make_extractor(llm)
    first = run_pipeline(answers_file, store, extractor, limit=1)
    assert (first.processed, first.failed) == (1, 1)

    retry = run_pipeline(answers_file, store, extractor)
    assert retry.processed == 2 and retry.failed == 0 and store.counts()["answers_failed"] == 0

    claims_before = store.counts()["claims"]
    forced = run_pipeline(answers_file, store, extractor, force=True)
    assert forced.processed == 2 and store.counts()["claims"] == claims_before


def test_duplicate_answers_in_one_file_are_processed_once(tmp_path, answers_file, store, make_extractor):
    line = answers_file.read_text(encoding="utf-8").splitlines()[0]
    answers_file.write_text(f"{line}\n{line}\n", encoding="utf-8")
    llm = FakeLLM(claims_json(make_claim()))
    summary = run_pipeline(answers_file, store, make_extractor(llm))
    assert (summary.processed, summary.skipped) == (1, 1)


def test_rejected_claims_are_kept_for_audit(answers_file, store, make_extractor):
    llm = FakeLLM(claims_json(make_claim(), make_claim(ward="Việt Hưng", quote="bịa 5 triệu")))
    run_pipeline(answers_file, store, make_extractor(llm))
    assert store.counts()["rejected"] == 2


def test_exports(answers_file, store, domain, make_extractor, tmp_path):
    run_pipeline(answers_file, store, make_extractor(FakeLLM(claims_json(
        make_claim(), make_claim(metric="point", value_low=20_000_000, value_high=None,
                                 quote="giá trung vị khoảng 402 triệu/m²"),
    ))))
    out_csv = tmp_path / "out" / "claims.csv"
    assert export_csv(store, domain, out_csv) == 4
    raw = out_csv.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8-sig")))
    assert list(rows[0].keys()) == domain.csv_columns
    assert {r["confidence_flag"] for r in rows} == {"ok", "ambiguous"}
    assert any(r["flag_reasons"] == "value_low_not_in_quote" for r in rows)

    out_jsonl = tmp_path / "claims.jsonl"
    assert export_jsonl(store, domain, out_jsonl) == 4
    assert json.loads(out_jsonl.read_text(encoding="utf-8").splitlines()[0])["ward"] == "Bồ Đề"


def test_cli_run_then_export(answers_file, tmp_path, capsys):
    db, out = tmp_path / "cli.db", tmp_path / "cli.csv"
    factory = lambda model: FakeLLM(claims_json(make_claim()))  # noqa: E731
    code = main(["run", "--input", str(answers_file), "--db", str(db)], llm_factory=factory)
    assert code == 0 and "processed=2" in capsys.readouterr().out

    assert main(["export", "--db", str(db), "--out", str(out)]) == 0
    assert len(list(csv.DictReader(out.open(encoding="utf-8-sig")))) == 2
