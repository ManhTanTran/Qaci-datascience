"""Recorded extractor outputs for the real sample answers (examples/llm_answers.sample.jsonl).

The JSON files in fixtures/replay were produced by an independent LLM run with the production
prompt. Replaying them checks that real-world formatting (markdown tables, LaTeX cells,
"900+", chat-UI noise) passes the code-side verification, with no token cost.
"""

from pathlib import Path

import pytest

from claims_extractor.extract import Extractor
from claims_extractor.io import read_answers

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPLAYS = Path(__file__).parent / "fixtures" / "replay"
# tag -> (index in the sample file, minimum expected claims)
CASES = {
    "gemini1": (0, 7), "gemini2": (2, 20), "gemini3": (4, 12), "gemini4": (6, 4),
    "gemini5": (8, 20), "chatgpt1": (1, 8), "chatgpt4": (7, 6),
}


class ReplayLLM:
    name = "replay"

    def __init__(self, path: Path) -> None:
        self._text = path.read_text(encoding="utf-8")

    def complete(self, system: str, user: str) -> str:
        return self._text


@pytest.fixture(scope="module")
def sample_answers():
    answers, problems = read_answers(FIXTURES_DIR / "llm_answers.sample.jsonl")
    assert not problems and len(answers) == 10
    return answers


@pytest.fixture(scope="module")
def extracted(sample_answers, domain_module):
    return {
        tag: Extractor(ReplayLLM(REPLAYS / f"{tag}.json"), domain_module).extract(sample_answers[idx])
        for tag, (idx, _) in CASES.items()
    }


@pytest.fixture(scope="module")
def domain_module():
    from claims_extractor.domains import get_domain
    return get_domain("real_estate")


@pytest.mark.parametrize("tag", CASES)
def test_replayed_claims_all_pass_verification(extracted, tag):
    output = extracted[tag]
    assert output.extract_status == "ok"
    assert len(output.claims) >= CASES[tag][1]
    assert output.rejected == []
    flagged = [(c["flag_reasons"], c["quote"][:60]) for c in output.claims if c["confidence_flag"] != "ok"]
    assert flagged == []


def test_latex_table_and_plus_signs_survive(extracted):
    gia_lam = {(c["ward"], c["sub_segment"]): c for c in extracted["gemini5"].claims if c["ward"]}
    row = gia_lam[("Trâu Quỳ", "mặt đường lớn / kinh doanh")]
    assert (row["value_low"], row["value_high"], row["open_ended"]) == (130_000_000, 200_000_000, True)


def test_shared_price_is_split_per_ward(extracted):
    wards = {c["ward"] for c in extracted["gemini2"].claims if c["value_low"] == 300_000_000}
    assert wards == {"Trung Hòa", "Yên Hòa"}


def test_state_table_is_kept_apart_from_market_prices(extracted):
    bases = {c["price_basis"] for c in extracted["gemini3"].claims}
    assert bases == {"MARKET", "STATE_TABLE"}
    state = [c for c in extracted["chatgpt4"].claims if c["price_basis"] == "STATE_TABLE"]
    assert state and state[0]["value_low"] == 695_300_000


def test_illustrative_totals_are_not_extracted(extracted):
    values = {c["value_low"] for c in extracted["chatgpt1"].claims}
    assert not values & {10_000_000_000, 24_000_000_000, 40_000_000_000}
