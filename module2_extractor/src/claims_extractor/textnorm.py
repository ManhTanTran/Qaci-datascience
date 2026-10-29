"""Text helpers: quote matching and Vietnamese money-amount parsing (pure code, no LLM)."""

from __future__ import annotations

import html
import re
import unicodedata

_MARKDOWN_EMPHASIS = re.compile(r"[*_`]")  # removed: "**106**." must equal "106."
_MARKDOWN_SEPARATORS = re.compile(r"[#>|]")  # replaced by a space: table cells, headings
_WHITESPACE = re.compile(r"\s+")


_IMAGE_LINE = re.compile(r"^[ \t]*\[image\]\([^)]*\)[ \t]*$", re.MULTILINE)
_LATEX_TEXT = re.compile(r"\\text\{\s*([^{}]*?)\s*\}")
_LATEX_SQUARE = re.compile(r"\^\{?2\}?")
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_answer_text(text: str) -> str:
    """Remove copy/paste noise seen in chatbot answers, keeping the wording intact.

    HTML entities (`&#x20;`), `[image](favicon)` lines and LaTeX price cells
    (`$70 - 100 \\text{ triệu/m}^2$`) would otherwise hide units from the number checks.
    """
    text = html.unescape(text)
    text = _IMAGE_LINE.sub("", text)
    text = _LATEX_TEXT.sub(r"\1", text)
    text = _LATEX_SQUARE.sub("²", text).replace("$", "")
    return _BLANK_RUNS.sub("\n\n", text).strip()


def normalize_text(text: str) -> str:
    """Casefold, drop markdown decoration, collapse whitespace. Used on both sides of a match."""
    text = unicodedata.normalize("NFC", text).replace(" ", " ")
    text = _MARKDOWN_EMPHASIS.sub("", text)
    text = _MARKDOWN_SEPARATORS.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip().casefold()


def quote_in_text(quote: str, normalized_text: str) -> bool:
    normalized_quote = normalize_text(quote)
    return bool(normalized_quote) and normalized_quote in normalized_text


# ---- money amounts -------------------------------------------------------------------

_NUMBER = r"\d{1,3}(?:[.,]\d{3})+(?!\d)|\d+(?:[.,]\d+)?"
_UNIT = r"(?:tỷ|tỉ|ty|triệu|trieu|tr|nghìn|nghin|ngàn|k)(?![^\W\d_])"
_TOKEN = re.compile(rf"(?P<num>{_NUMBER})\+?\s*(?P<unit>{_UNIT})?", re.IGNORECASE)
_THOUSANDS_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_RANGE_SEPARATOR = re.compile(r"^\s*(?:-|–|—|~|đến|tới|den|toi|to)\s*$", re.IGNORECASE)

_UNIT_MULTIPLIER = {
    "tỷ": 10**9, "tỉ": 10**9, "ty": 10**9,
    "triệu": 10**6, "trieu": 10**6, "tr": 10**6,
    "nghìn": 10**3, "nghin": 10**3, "ngàn": 10**3, "k": 10**3,
}


def _parse_number(raw: str) -> float:
    if _THOUSANDS_GROUPED.match(raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def extract_amounts(text: str) -> list[int]:
    """All VND amounts in `text`, e.g. '200 - 430 triệu/m²' -> [200_000_000, 430_000_000].

    A number with no unit inherits the unit of the next number when only a range separator
    sits between them. A bare number below 1000 and without a unit is ignored.
    """
    tokens = list(_TOKEN.finditer(text))
    amounts: list[int] = []
    for index, token in enumerate(tokens):
        unit = (token.group("unit") or "").casefold()
        if not unit and index + 1 < len(tokens):
            following = tokens[index + 1]
            gap = text[token.end():following.start()]
            if following.group("unit") and _RANGE_SEPARATOR.match(gap):
                unit = following.group("unit").casefold()
        value = _parse_number(token.group("num"))
        if unit:
            amounts.append(round(value * _UNIT_MULTIPLIER[unit]))
        elif value >= 1000:
            amounts.append(round(value))
    return amounts


def amount_matches(value: int, amounts: list[int], tolerance: float = 0.01) -> bool:
    return any(abs(value - amount) <= tolerance * max(value, 1) for amount in amounts)
