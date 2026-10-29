from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from claims_extractor.domains import get_domain
from claims_extractor.extract import Extractor
from claims_extractor.models import AnswerRecord
from claims_extractor.store import ClaimStore

from common.config import load_config


@pytest.fixture()
def cfg_factory(tmp_path):
    def make(**overrides):
        raw = {
            "mode": "manual",
            "input_file": "data/llm_answers.jsonl",
            "database_file": "data/claims.db",
            "export_dir": "data/exports",
            "processing": {"batch_size": 5, "poll_interval_seconds": 0.05, "stable_file_checks": 2,
                           "max_retries": 3, "retry_backoff_seconds": 0},
            "quality": {"min_sample": 5},
            "logging": {"level": "WARNING"},
        }
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(raw.get(k), dict):
                raw[k].update(v)
            else:
                raw[k] = v
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return load_config(path)
    return make


@pytest.fixture()
def cfg(cfg_factory):
    return cfg_factory()


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_handoff_file(tmp_path, monkeypatch):
    """No test may write the real data/llm_answers.jsonl."""
    monkeypatch.setenv("LLM_ANSWERS_FILE", str(tmp_path / "handoff" / "llm_answers.jsonl"))


@pytest.fixture
def answer_text() -> str:
    return (FIXTURES / "gemini_long_bien.txt").read_text(encoding="utf-8")


@pytest.fixture
def answer(answer_text: str) -> AnswerRecord:
    return AnswerRecord(
        crawled_at="2026-10-26T09:00:00+07:00", chatbot="gemini",
        query_text="Giá bất động sản Long Biên", answer_text=answer_text,
    )


@pytest.fixture
def domain():
    return get_domain("real_estate")


@pytest.fixture
def store(tmp_path: Path):
    with ClaimStore(tmp_path / "claims.db") as opened:
        yield opened


@pytest.fixture
def make_extractor(domain):
    return lambda llm: Extractor(llm, domain)


@pytest.fixture
def answers_file(tmp_path: Path, answer_text: str) -> Path:
    """A phase-1 hand-off file with a blank line, as seen in real files."""
    rows = [
        {"crawled_at": "2026-10-26T09:00:00+07:00", "chatbot": "gemini",
         "query_text": "q1", "answer_text": answer_text},
        {"crawled_at": "2026-10-26T09:05:00+07:00", "chatbot": "chatgpt",
         "query_text": "q1", "answer_text": answer_text},
    ]
    path = tmp_path / "llm_answers.jsonl"
    path.write_text(
        json.dumps(rows[0], ensure_ascii=False) + "\n\n" + json.dumps(rows[1], ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
