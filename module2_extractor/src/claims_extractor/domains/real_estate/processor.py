"""Pure-code verification of LLM claims. The LLM never decides trust; this module does."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import ValidationError

from ...domain import ClaimResult
from ...models import AnswerRecord
from ...textnorm import amount_matches, extract_amounts, normalize_text, quote_in_text
from .schema import PriceClaim, StoredPriceClaim
from .sources import resolve_citations, split_sources

AREA_BASIS_BY_TYPE = {"DAT_O": "LAND_AREA", "NHA_RIENG": "LAND_AREA", "CHUNG_CU": "FLOOR_AREA"}

# VND per m². Upper bound is generous on purpose: old-quarter Hanoi houses reach ~1.3 billion.
PLAUSIBLE_MIN = 5_000_000
PLAUSIBLE_MAX = 2_000_000_000

_TOTAL_PRICE = re.compile(r"/\s*căn|mỗi\s+căn|trên\s+căn", re.IGNORECASE)
_PER_M2 = re.compile(r"/\s*m|mỗi\s+m|trên\s+m|một\s+m", re.IGNORECASE)

_PLACE_PREFIX = re.compile(
    r"^(?:(?:quận|huyện|thị xã|thành phố|phường|thị trấn|xã)\s+|(?:tp|tt|q|h|p)\.\s*|(?=[qp]\d)[qp])",
    re.IGNORECASE,
)


def normalize_place(name: str | None, numeric_prefix: str = "") -> str | None:
    """Drop the administrative-type prefix ("Quận", "Phường", "P."...), tidy casing.

    Purely numeric names keep a prefix ("Quận 1") because "1" alone is meaningless.
    """
    if not name:
        return None
    cleaned = " ".join(name.split())
    rest = _PLACE_PREFIX.sub("", cleaned, count=1).strip()
    if not rest:
        return None
    if rest.isdigit() and numeric_prefix:
        return f"{numeric_prefix} {rest}"
    if rest.islower() or (rest.isupper() and " " in rest):  # keep acronyms such as "HCM"
        rest = rest.title()
    return rest


def _squash(text: str | None) -> str:
    return normalize_text(text) if text else ""


def make_claim_id(answer_id: str, claim: dict[str, Any]) -> str:
    key = "|".join(
        str(part)
        for part in (
            answer_id, _squash(claim["district"]), _squash(claim["ward"]), _squash(claim["street"]),
            claim["property_type"], _squash(claim["sub_segment"]), claim["price_basis"],
            _squash(claim["period_text"]), claim["metric"], claim["value_low"], claim["value_high"],
            claim["open_ended"],
        )
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _reject(reason: str, raw: dict[str, Any], detail: str | None = None) -> ClaimResult:
    rejected: dict[str, Any] = {"reason": reason, "raw": raw}
    if detail:
        rejected["detail"] = detail
    return ClaimResult(rejected=rejected)


def _flag(reasons: list[str], implausible: bool) -> str:
    if implausible:
        return "implausible"
    return "ambiguous" if reasons else "ok"


def process_claim(raw: dict[str, Any], answer: AnswerRecord, answer_norm: str) -> ClaimResult:
    try:
        claim = PriceClaim.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        return _reject("schema_error", raw, f"{'.'.join(map(str, first['loc']))}: {first['msg']}")

    if not quote_in_text(claim.quote, answer_norm):
        return _reject("quote_not_in_answer", raw)

    district = normalize_place(claim.district, "Quận")
    ward = normalize_place(claim.ward, "Phường")
    if not district and not ward:
        return _reject("missing_location", raw)

    low, high = claim.value_low, claim.value_high
    reasons: list[str] = []
    if high is not None and high < low:
        low, high = high, low
        reasons.append("range_swapped")
    if high is not None and high == low:
        high = None

    amounts = extract_amounts(claim.quote)
    for label, value in (("value_low", low), ("value_high", high)):
        if value is not None and not amount_matches(value, amounts):
            reasons.append(f"{label}_not_in_quote")
    if claim.metric == "typical_range" and high is None:
        reasons.append("range_without_high")
    if _TOTAL_PRICE.search(claim.quote) and not _PER_M2.search(claim.quote):
        reasons.append("total_price_in_quote")

    implausible = any(
        value is not None and not PLAUSIBLE_MIN <= value <= PLAUSIBLE_MAX for value in (low, high)
    )
    if implausible:
        reasons.append("outside_plausible_range")

    fields = {
        "province": normalize_place(claim.province),
        "district": district,
        "ward": ward,
        "street": (claim.street or "").strip() or None,
        "property_type": claim.property_type,
        "sub_segment": (claim.sub_segment or "").strip() or None,
        "price_basis": claim.price_basis,
        "metric": claim.metric,
        "value_low": low,
        "value_high": high,
        "open_ended": claim.open_ended,
        "unit_original": claim.unit_original.strip(),
        "qualifier": (claim.qualifier or "").strip() or None,
        "period_text": (claim.period_text or "").strip() or None,
        "quote": claim.quote.strip(),
    }
    stored = StoredPriceClaim(
        claim_id=make_claim_id(answer.answer_id, fields),
        answer_id=answer.answer_id,
        crawl_run_id=answer.crawl_run_id,
        target_month=answer.target_month,
        source_urls=resolve_citations(claim.quote, split_sources(answer.answer_text)[1]),
        crawled_at=answer.crawled_at,
        chatbot=answer.chatbot,
        area_basis=AREA_BASIS_BY_TYPE.get(claim.property_type),
        confidence_flag=_flag(reasons, implausible),
        flag_reasons=reasons,
        **fields,
    )
    return ClaimResult(stored=stored.model_dump(mode="json"))
