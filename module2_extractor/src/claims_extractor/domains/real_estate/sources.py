"""Helpers for answers produced by module 1's search-and-summarise flow.

Such an answer ends with a block "Nguồn tìm kiếm ...:" listing `[n] title — url`. The block is
metadata, not content to extract from, but it lets code resolve the `[n]` markers a claim quotes
into real URLs (provenance) without asking the LLM to do it.
"""

from __future__ import annotations

import re

_SOURCES_HEADER = re.compile(r"^\s*nguồn tìm kiếm\b.*$", re.IGNORECASE | re.MULTILINE)
_SOURCE_LINE = re.compile(r"^\s*\[(\d+)\]\s*(.*?)\s*[—-]\s*(https?://\S+)\s*$", re.MULTILINE)
_CITATION = re.compile(r"\[(\d+)\]")
_NO_RESULT = "kết quả: chưa tìm thấy"


def declares_no_result(text: str) -> str | None:
    """Reason string when the answer itself says nothing was found (no LLM call needed)."""
    stripped = text.strip()
    first_line = stripped.splitlines()[0].casefold() if stripped else ""
    return "no_result_declared" if first_line.startswith(_NO_RESULT) else None


def split_sources(text: str) -> tuple[str, dict[int, str]]:
    """Return (body without the sources block, {citation number: url})."""
    match = _SOURCES_HEADER.search(text)
    if not match:
        return text, {}
    urls = {int(n): url for n, _title, url in _SOURCE_LINE.findall(text[match.end():])}
    return text[:match.start()].rstrip(), urls


def strip_sources(text: str) -> str:
    return split_sources(text)[0]


def resolve_citations(quote: str, urls: dict[int, str]) -> list[str]:
    """URLs for the `[n]` markers present in `quote` (unknown numbers are ignored)."""
    seen: list[str] = []
    for number in _CITATION.findall(quote):
        url = urls.get(int(number))
        if url and url not in seen:
            seen.append(url)
    return seen
