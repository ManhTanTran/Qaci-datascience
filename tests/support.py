"""Shared test helpers: fake LLMs, hand-off line builders, claim factories."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

def answer_line(i: int, month: str = "2026-10", text: str | None = None, **extra) -> str:
    row = {
        "answer_id": f"id{i:05d}", "crawl_run_id": "run-1", "target_month": month,
        "crawled_at": "2026-10-28T10:00:00+07:00", "chatbot": "Gemma", "model_name": "gemma",
        "query_text": f"Tra cứu giá rao {month} tại Phường P{i}, Hà Nội",
        "answer_text": text or f"Giá phổ biến 200 - 430 triệu/m² tại P{i} [1]\n\nNguồn tìm kiếm (Tavily):\n[1] A — https://a.example/{i}",
    }
    row.update(extra)
    return json.dumps(row, ensure_ascii=False) + "\n"


def append(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as h:
        h.write("".join(lines))


class GoodLLM:
    """Returns one verifiable claim per answer by echoing the 'Giá phổ biến' sentence."""
    name = "good-llm"

    last_usage = None

    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 20}
        found = re.search(r"triệu/m² tại P(\d+)", user)
        ward = found.group(1) if found else "0"
        quote = "200 - 430 triệu/m²"
        if f"tại P{ward} [1]" in user:
            quote = f"{quote} tại P{ward} [1]"  # keeps the citation marker, like a real answer
        return json.dumps({"claims": [{
            "province": "Hà Nội", "ward": f"P{ward}", "property_type": "NHA_RIENG", "price_basis": "MARKET",
            "metric": "typical_range", "value_low": 200000000, "value_high": 430000000,
            "unit_original": "triệu/m²", "quote": quote, "qualifier": "giá chào bán",
        }]})


class FlakyLLM(GoodLLM):
    def __init__(self, fail_first: int):
        super().__init__()
        self.fail_first = fail_first

    def complete(self, system, user):
        if self.calls < self.fail_first:
            self.calls += 1
            raise RuntimeError("503 service unavailable")
        return super().complete(system, user)


class FakeLLM:
    """Scripted LLM: replies are consumed in order, the last one repeats. Exceptions are raised."""

    name = "fake-llm"

    def __init__(self, *replies: str | Exception) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def claims_json(*claims: dict[str, Any]) -> str:
    return json.dumps({"claims": list(claims)}, ensure_ascii=False)


def make_claim(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "province": None, "district": "Long Biên", "ward": "Bồ Đề",
        "property_type": "NHA_RIENG", "sub_segment": "mặt phố", "metric": "typical_range",
        "value_low": 200_000_000, "value_high": 430_000_000, "unit_original": "triệu/m²",
        "qualifier": None, "quote": "khoảng giá phổ biến 200 - 430 triệu/m²",
    }
    base.update(overrides)
    return base


def admin_csv(path: Path) -> Path:
    fields = [
        "administrative_code",
        "administrative_name",
        "administrative_level",
        "administrative_type",
        "province_code",
        "province_name",
        "administrative_version",
        "is_current",
        "valid_to",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "administrative_code": "00001",
                "administrative_name": "Phường Minh Hòa",
                "administrative_level": "COMMUNE",
                "administrative_type": "WARD",
                "province_code": "01",
                "province_name": "Thành phố Hà Nội",
                "administrative_version": "nso-2026-10",
                "is_current": "1",
                "valid_to": "",
            }
        )
    return path
