"""Strict structural validation. This does NOT validate market prices or geography."""

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

PROPERTY_TYPES = {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
DATA_TYPES = {"AI_ESTIMATE", "MARKET_REFERENCE_UNVERIFIED"}
LISTING_EVIDENCE_STATUSES = {"SEARCH_SNIPPET_ONLY", "SOURCE_PAGE_CONFIRMED"}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("price must be numeric (VND/m2)")  # noqa: TRY004 - malformed model data is a value error
    if not math.isfinite(value) or not (100000 <= value <= 5_000_000_000):
        raise ValueError("price outside sanity range")
    return round(value)


def normalize_result(raw: dict, ward, *, grounding_used: bool, model: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("result must be an object")  # noqa: TRY004 - malformed model output is a value error
    if str(raw.get("ward_code", "")).strip() != ward.code:
        raise ValueError("ward_code mismatch")
    if str(raw.get("ward_name", "")).strip().casefold() != ward.name.casefold():
        raise ValueError("ward_name mismatch")
    if str(raw.get("province", "")).strip().casefold() != ward.province.casefold():
        raise ValueError("province mismatch")
    kind = raw.get("property_type")
    if kind not in PROPERTY_TYPES:
        raise ValueError("unsupported property_type")
    avg = _number(raw.get("average_price_per_m2"))
    lower = _number(raw.get("min_estimated_price_per_m2"))
    upper = _number(raw.get("max_estimated_price_per_m2"))
    if not lower <= avg <= upper:
        raise ValueError("price range inconsistency")
    notes = str(raw.get("estimation_basis", "")).strip()
    if len(notes) < 20:
        raise ValueError("estimation_basis too short")
    data_type = str(raw.get("data_type", "AI_ESTIMATE"))
    if data_type not in DATA_TYPES:
        raise ValueError("model claimed unsupported or verified status")
    urls = raw.get("source_urls") or []
    if not isinstance(urls, list):
        raise ValueError("source_urls must be list")  # noqa: TRY004 - malformed model output is a value error
    urls = list(
        dict.fromkeys(
            u.strip()
            for u in urls
            if isinstance(u, str) and u.startswith("https://") and urlparse(u).hostname
        )
    )[:15]
    if not grounding_used or not urls:
        data_type = "AI_ESTIMATE"
    return {
        "ward_code": ward.code,
        "ward_name": ward.name,
        "province": ward.province,
        "property_type": kind,
        "average_price_per_m2": avg,
        "min_estimated_price_per_m2": lower,
        "max_estimated_price_per_m2": upper,
        "data_type": data_type,
        "quality_gate": "RESEARCH_ONLY",  # no automatic conversion to VERIFIED
        "confidence": "LOW",  # not a calibrated probability
        "estimation_basis": notes[:1200],
        "source_urls": urls,
        "grounding_used": bool(grounding_used),
        "model": model,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def extract_json(text: str):
    """Accept raw JSON or a single fenced JSON block, refuse unrelated prose."""
    import json

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
    result = json.loads(stripped)
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise ValueError('expected object with "results" array')  # noqa: TRY004 - JSON shape error
    return result


def canonicalize_listing_url(value: str) -> tuple[str, str]:
    """Return a stable HTTPS URL identity and normalized source domain."""
    parsed = urlparse(str(value).strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise ValueError("source_url must be a public HTTPS URL")
    host = host.removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    tracking = {"fbclid", "gclid", "ref", "referrer"}
    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in tracking and not key.lower().startswith("utm_")
    ]
    query.sort()
    canonical = urlunparse(("https", host, path, "", urlencode(query), ""))
    return canonical, host


def _normalized_identity_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(text.split())


def _positive_number(value, field: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > maximum:
        raise ValueError(f"{field} outside allowed range")
    return number


def _match_grounded_url(candidate_url: str, grounded_urls: list[str]) -> bool:
    for url in grounded_urls:
        try:
            canonical, _ = canonicalize_listing_url(url)
        except ValueError:
            continue
        if canonical == candidate_url:
            return True
    return False


def normalize_listing(raw: dict, ward, *, grounded_urls: list[str]) -> dict:
    """Validate one source-backed listing and compute price/m² locally."""
    if not isinstance(raw, dict):
        raise TypeError("listing must be an object")
    if str(raw.get("ward_code", "")).strip() != ward.code:
        raise ValueError("ward_code is outside the imported whitelist")
    if str(raw.get("ward_name", "")).strip().casefold() != ward.name.casefold():
        raise ValueError("ward_name mismatch")
    if str(raw.get("province", "")).strip().casefold() != ward.province.casefold():
        raise ValueError("province mismatch")
    property_type = raw.get("property_type")
    if property_type not in PROPERTY_TYPES:
        raise ValueError("unsupported property_type")
    price_vnd = _positive_number(raw.get("price_vnd"), "price_vnd", 1e15)
    area_m2 = _positive_number(raw.get("area_m2"), "area_m2", 100_000)
    address = " ".join(str(raw.get("address", "")).split())
    if len(address) < 8:
        raise ValueError("address is missing or too short for deduplication")
    source_url = str(raw.get("source_url", "")).strip()
    identity_key, source_domain = canonicalize_listing_url(source_url)
    if not _match_grounded_url(identity_key, grounded_urls):
        raise ValueError("source_url is not present in Google Search grounding sources")
    listed_date = raw.get("listed_date")
    if listed_date in (None, ""):
        listed_date = None
    else:
        listed_date = str(listed_date).strip()
        try:
            listed_date = datetime.fromisoformat(listed_date[:10]).date().isoformat()
        except ValueError as exc:
            raise ValueError("listed_date must use YYYY-MM-DD") from exc
    price_evidence = " ".join(str(raw.get("price_evidence", "")).split())
    area_evidence = " ".join(str(raw.get("area_evidence", "")).split())
    excerpt = " ".join(str(raw.get("evidence_excerpt", "")).split())
    if len(price_evidence) < 3 or len(area_evidence) < 3:
        raise ValueError("price_evidence and area_evidence are required")
    excerpt = excerpt or f"Giá: {price_evidence}; Diện tích: {area_evidence}"
    requested_status = str(raw.get("evidence_status", "SEARCH_SNIPPET_ONLY")).upper()
    if requested_status not in LISTING_EVIDENCE_STATUSES:
        requested_status = "SEARCH_SNIPPET_ONLY"
    # Grounding metadata exposes citations but not whether Google fetched a full detail page.
    # Only retain the stronger label when the response also supplies explicit page-read evidence.
    evidence_status = (
        "SOURCE_PAGE_CONFIRMED"
        if requested_status == "SOURCE_PAGE_CONFIRMED" and raw.get("source_page_read") is True
        else "SEARCH_SNIPPET_ONLY"
    )
    identity_components = [
        ward.code,
        property_type,
        _normalized_identity_text(address),
        str(round(price_vnd)),
        f"{area_m2:.4f}",
        listed_date or "",
    ]
    identity_fingerprint = hashlib.sha256(
        "|".join(identity_components).encode("utf-8")
    ).hexdigest()
    listing_id = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:32]
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "listing_id": listing_id,
        "identity_key": identity_key,
        "identity_fingerprint": identity_fingerprint,
        "ward_code": ward.code,
        "ward_name": ward.name,
        "province": ward.province,
        "property_type": property_type,
        "price_vnd": price_vnd,
        "area_m2": area_m2,
        "price_per_m2": price_vnd / area_m2,
        "address": address,
        "source_url": source_url,
        "source_domain": source_domain,
        "listed_date": listed_date,
        "collected_at": collected_at,
        "evidence_status": evidence_status,
        "evidence_excerpt": excerpt[:1000],
        "raw_payload": json.dumps(raw, ensure_ascii=False, sort_keys=True),
    }
