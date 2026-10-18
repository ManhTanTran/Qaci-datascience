"""Conservative HTML/JSON-LD parsing; stores fields and evidence pointers, not whole pages."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from .models import DiscoveredUrl

PROPERTY_TYPES = {"DAT_O", "NHA_RIENG", "CHUNG_CU"}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.text: list[str] = []
        self.title_parts: list[str] = []
        self._script = False
        self._jsonld_script = False
        self._title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag.casefold() == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop")
            if key and values.get("content"):
                self.meta[key.casefold()] = values["content"]
        if tag.casefold() == "script":
            self._script = True
            self._jsonld_script = values.get("type", "").casefold() == "application/ld+json"
            if self._jsonld_script:
                self.jsonld.append("")
        if tag.casefold() == "title":
            self._title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script":
            self._script = False
            self._jsonld_script = False
        elif tag.casefold() == "title":
            self._title = False

    def handle_data(self, data: str) -> None:
        if self._script and self._jsonld_script and self.jsonld:
            self.jsonld[-1] += data
        elif not self._script:
            cleaned = " ".join(data.split())
            if cleaned:
                self.text.append(cleaned)
                if self._title:
                    self.title_parts.append(cleaned)


def parse_page(html: str | bytes) -> dict[str, Any]:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    parser = _PageParser()
    parser.feed(html)
    return {
        "links": parser.links,
        "jsonld": parser.jsonld,
        "meta": parser.meta,
        "text": " ".join(parser.text),
        "title": " ".join(parser.title_parts).strip(),
        "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
    }


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.casefold() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only absolute public HTTPS URLs without credentials are accepted")
    if parts.port not in {None, 443}:
        raise ValueError("Only the standard HTTPS port is accepted")
    host = parts.hostname.casefold().rstrip(".")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", host, path, parts.query, ""))


def _host_allowed(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    return any(host == domain.casefold().removeprefix("www.") or host.endswith("." + domain.casefold().removeprefix("www.")) for domain in domains)


def classify_detail_url(url: str, detail_path_regex: str = "") -> str:
    path = urlsplit(url).path
    if detail_path_regex and re.search(detail_path_regex, path, flags=re.IGNORECASE):
        return "DIRECT_LISTING"
    if not path.strip("/") or re.search(r"(?:mua-ban|nha-dat|bat-dong-san|listing|search|tim-kiem)(?:/|$)", path, re.IGNORECASE):
        return "CATEGORY"
    return "UNKNOWN"


def discover_listing_urls(
    html: str | bytes,
    *,
    page_url: str,
    domains: list[str],
    detail_path_regex: str = "",
    limit: int = 100,
) -> list[DiscoveredUrl]:
    if limit < 0:
        raise ValueError("limit cannot be negative")
    page = parse_page(html)
    found: dict[str, DiscoveredUrl] = {}
    for href in page["links"]:
        absolute = urljoin(page_url, href)
        try:
            identity = canonical_url(absolute)
        except ValueError:
            continue
        if not _host_allowed(identity, domains):
            continue
        kind = classify_detail_url(identity, detail_path_regex)
        if identity not in found:
            found[identity] = DiscoveredUrl(absolute, identity, kind)
    return list(found.values())[:limit]


def _jsonld_objects(raw: list[str]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if isinstance(value.get("@graph"), list):
                visit(value["@graph"])
            else:
                objects.append(value)
                for key in ("mainEntity", "item", "itemOffered"):
                    if key in value and isinstance(value[key], (dict, list)):
                        visit(value[key])

    for block in raw:
        try:
            visit(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
    return objects


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value).casefold()
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d")).strip()


def _local_number(value: str) -> float | None:
    text = re.sub(r"[^0-9,.]", "", value)
    if not text:
        return None
    if "." in text and "," in text:
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        pieces = text.split(sep)
        if len(pieces) > 2 or (len(pieces[-1]) == 3 and len(pieces[0]) >= 1):
            text = "".join(pieces)
        else:
            text = "".join(pieces[:-1]) + "." + pieces[-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None


def parse_price_vnd(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        return price if 1_000_000 <= price <= 10**15 else None
    text = str(value).casefold().replace("₫", " dong ").replace("vnđ", " dong ")
    matches = list(re.finditer(r"(\d[\d.,\s]*\d|\d)\s*(tỷ|tỉ|ty|triệu|trieu|tr|million|billion)", text))
    if matches:
        total = 0.0
        for match in matches:
            number = _local_number(match.group(1))
            unit = match.group(2)
            if number is None:
                continue
            total += number * (1_000_000_000 if unit in {"tỷ", "tỉ", "ty", "billion"} else 1_000_000)
        return total if 1_000_000 <= total <= 10**15 else None
    number = _local_number(text)
    if number is None:
        return None
    if number >= 1_000_000:
        return number
    return None


def parse_area_m2(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        area = float(value)
        return area if 1 <= area <= 100_000 else None
    match = re.search(r"(\d[\d.,\s]*\d|\d)\s*(?:m\s*[²2]|sqm|mét\s*vuông)", str(value), re.IGNORECASE)
    if not match:
        return None
    area = _local_number(match.group(1))
    return area if area and 1 <= area <= 100_000 else None


def _address_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts = [value.get(key) for key in ("streetAddress", "addressLocality", "addressRegion")]
        return ", ".join(str(part).strip() for part in parts if part)
    return ""


def _first_offer(obj: dict[str, Any]) -> dict[str, Any]:
    offers = obj.get("offers") or obj.get("offer") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    return offers if isinstance(offers, dict) else {}


def _property_type(text: str, obj: dict[str, Any]) -> str | None:
    basis = normalize_text(" ".join([text, str(obj.get("@type", "")), str(obj.get("category", ""))]))
    if any(term in basis for term in ("dat nong nghiep", "dat trong cay", "farm land", "agricultural")):
        return None
    if any(term in basis for term in ("can ho", "chung cu", "apartment", "condominium")):
        return "CHUNG_CU"
    if any(term in basis for term in ("nha rieng", "nha pho", "nha nguyen can", "detached house", "house")):
        return "NHA_RIENG"
    if any(term in basis for term in ("dat o", "dat tho cu", "residential land", "house plot")):
        return "DAT_O"
    return None


def _date_value(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return None


def _visible_price(text: str) -> float | None:
    match = re.search(
        r"(?:gi[aá](?:\s+b[aá]n)?|price)\s*[:：]?\s*([^|;,.]{1,45}(?:tỷ|tỉ|triệu|tr|đồng|dong|₫))",
        text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(r"(?:gi[aá](?:\s+b[aá]n)?|price)\s*[:：]?\s*(\d[\d.,\s]*\d|\d)", text, re.IGNORECASE)
    return parse_price_vnd(match.group(1)) if match else None


def _visible_area(text: str) -> float | None:
    match = re.search(r"(?:di[eệ]n\s+t[ií]ch|area)\s*[:：]?\s*([^|;,.]{1,40}?\s*(?:m\s*[²2]|sqm|mét\s*vuông))", text, re.IGNORECASE)
    return parse_area_m2(match.group(1)) if match else None


def extract_listing_detail(
    html: str | bytes,
    *,
    target_rank: int,
    target_ward: str,
    target_district: str,
    target_province: str,
    source_url: str,
    source_id: str | None = None,
    fetched_at: str = "",
) -> dict[str, Any]:
    page = parse_page(html)
    objects = _jsonld_objects(page["jsonld"])
    obj = next((item for item in objects if item.get("@type")), {})
    offer = _first_offer(obj)
    title = str(obj.get("name") or page["meta"].get("og:title") or page["title"] or "").strip()
    address = _address_text(obj.get("address") or obj.get("location", {}).get("address") if isinstance(obj.get("location"), dict) else obj.get("address"))
    description = str(obj.get("description") or page["meta"].get("description") or page["meta"].get("og:description") or "")
    text = " ".join([page["text"], description])

    price_raw = offer.get("price") or obj.get("price") or page["meta"].get("product:price:amount")
    price_vnd = parse_price_vnd(price_raw)
    area_raw: Any = obj.get("floorSize") or obj.get("size") or obj.get("area")
    area_basis = "UNKNOWN"
    if isinstance(area_raw, dict):
        area_raw = area_raw.get("value") or area_raw.get("minValue")
        area_basis = "FLOOR_AREA" if obj.get("floorSize") else "UNKNOWN"
    if area_raw is None:
        for extra in obj.get("additionalProperty", []) if isinstance(obj.get("additionalProperty"), list) else []:
            if not isinstance(extra, dict):
                continue
            name = normalize_text(str(extra.get("name", "")))
            if any(word in name for word in ("dien tich", "area", "size")):
                area_raw = extra.get("value")
                if "san" in name or "floor" in name:
                    area_basis = "FLOOR_AREA"
                elif "dat" in name or "land" in name:
                    area_basis = "LAND_AREA"
                break
    area_m2 = parse_area_m2(area_raw)
    if area_m2 is None:
        visible = re.search(r"(\d[\d.,\s]*\d|\d)\s*(?:m\s*[²2]|sqm)", text, re.IGNORECASE)
        if visible:
            area_m2 = parse_area_m2(visible.group(0))
            area_basis = "UNKNOWN"

    kind = _property_type(" ".join([title, description, str(obj.get("category", ""))]), obj)
    visible_price = _visible_price(text)
    visible_area = _visible_area(text)
    normalized_text = normalize_text(text)
    normalized_address = normalize_text(address)
    address_visible = bool(normalized_address and normalized_address in normalized_text)
    target_terms_present = all(
        normalize_text(part) and normalize_text(part) in normalized_text
        for part in (target_ward, target_district, target_province)
    )
    ward_in_address = normalize_text(target_ward) in normalized_address
    detail_id = source_id
    identifier = obj.get("identifier")
    if not detail_id and isinstance(identifier, dict):
        detail_id = identifier.get("value")
    elif not detail_id and isinstance(identifier, str):
        detail_id = identifier

    validity = "SOURCE_PARTIAL"
    evidence_status = "UNVERIFIED"
    if address and not ward_in_address:
        validity = "GEO_MISMATCH"
        evidence_status = "SOURCE_CONFLICT"
    elif address and ward_in_address and not target_terms_present:
        validity = "SOURCE_PARTIAL"
        evidence_status = "SOURCE_PARTIAL"
    elif address and ward_in_address and target_terms_present:
        if price_vnd and area_m2 and visible_price == price_vnd and visible_area == area_m2 and address_visible and kind:
            validity = "SOURCE_VERIFIED"
            evidence_status = "SOURCE_VERIFIED"
        else:
            validity = "SOURCE_PARTIAL"
            evidence_status = "SOURCE_PARTIAL"

    listed_date = _date_value(obj.get("datePosted") or obj.get("datePublished"))
    expires_at = _date_value(obj.get("availabilityEnds") or obj.get("expiresAt"))
    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    if expires_at and expires_at < today:
        validity = "EXPIRED"
        evidence_status = "EXPIRED"

    canonical = canonical_url(source_url)
    source_domain = urlsplit(canonical).hostname or ""
    payload = {
        "source_id": source_id,
        "source_url": canonical,
        "retrieved_at": fetched_at,
        "content_sha256": page["content_sha256"],
        "jsonld_type": obj.get("@type"),
        "extracted_field_paths": {
            "title": "jsonld.name|og:title|title",
            "price_vnd": "offers.price|meta.product:price:amount",
            "area_m2": "floorSize|size|area|additionalProperty",
            "address": "address",
        },
        "visible_price_match": bool(price_vnd and visible_price == price_vnd),
        "visible_area_match": bool(area_m2 and visible_area == area_m2),
        "address_visible": address_visible,
        "target_terms_present": target_terms_present,
    }
    evidence = {
        "price": {"structured": price_vnd, "visible": visible_price},
        "area_m2": {"structured": area_m2, "visible": visible_area, "basis": area_basis},
        "address": address,
        "target_match": target_terms_present and ward_in_address,
        "content_sha256": page["content_sha256"],
    }
    return {
        "target_rank": target_rank,
        "original_ward": target_ward,
        "original_district": target_district,
        "original_province": target_province,
        "property_type": kind,
        "title": title,
        "address": address,
        "price_vnd": price_vnd,
        "area_m2": area_m2,
        "price_per_m2": price_vnd / area_m2 if price_vnd and area_m2 else None,
        "area_basis": area_basis,
        "source_listing_id": str(detail_id) if detail_id else None,
        "source_url": canonical,
        "canonical_url": canonical,
        "source_domain": source_domain,
        "source_url_type": "DIRECT_LISTING",
        "listed_date": listed_date,
        "expires_at": expires_at,
        "collected_at": fetched_at,
        "evidence_status": evidence_status,
        "validity_status": validity,
        "evidence": evidence,
        "raw_payload": payload,
    }
