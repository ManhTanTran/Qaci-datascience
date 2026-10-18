"""Offline Deep Research report parsing, source mapping, and sidecar audit storage."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from .core import norm, validate_listing

SOURCE_VERIFIED = "SOURCE_VERIFIED"
SOURCE_PARTIAL = "SOURCE_PARTIAL"
CATEGORY_ONLY = "CATEGORY_ONLY"
UNVERIFIED = "UNVERIFIED"
WEB_SEARCH_UNAVAILABLE = "WEB_SEARCH_UNAVAILABLE"
SOURCE_STATUSES = {SOURCE_VERIFIED, SOURCE_PARTIAL, CATEGORY_ONLY, UNVERIFIED}


def make_deep_research_prompt(target: dict[str, Any], count: int = 5) -> str:
    """Build the bounded rank-specific research prompt; it performs no I/O."""
    if not 1 <= count <= 5:
        raise ValueError("Deep Research pilot count must be 1..5")
    return f"""Nghiên cứu tin rao BÁN bất động sản công khai cho đúng địa bàn sau:
- target_rank: {target["rank"]}
- phường/xã theo danh sách: {target["ward"]}
- quận/huyện cũ: {target["district"]}
- tỉnh/thành: {target["province"]}

Tìm tối đa {count} tin rao riêng biệt. Chỉ nhận tin bán cụ thể, không lấy tin cho
thuê, bài tổng hợp thị trường, bảng giá đất, dự án không có tin cụ thể, hoặc
AI_ESTIMATE/giá do bạn tự ước tính. Không tự tạo giá, diện tích, địa chỉ, URL,
hoặc citation. Không gom nhiều tin dưới một URL danh mục.

Với mỗi tin, báo title, địa chỉ đầy đủ, property_type (chỉ DAT_O, NHA_RIENG,
CHUNG_CU), tổng giá bán price_vnd dạng số VND, area_m2 dạng số, và citation ID
được Deep Research gắn cho nguồn của chính tin đó. Đặt citation marker [cite: N]
ngay trong phần mô tả tin tương ứng. Nếu nguồn không nêu rõ trường nào, để trường
đó null hoặc bỏ candidate; không suy diễn.

Cuối báo cáo, nếu có candidate, thêm đúng một fenced JSON block dạng:
```json
{{"listings":[{{"title":"...","address":"...","property_type":"NHA_RIENG",
"price_vnd":7800000000,"area_m2":74.5,"source_citation_ids":[1]}}]}}
```
Các giá trị trên chỉ minh họa schema, không phải dữ liệu thật. source_citation_ids
phải trỏ đến citation ID thật trong sources của báo cáo. Nếu không có tin phù hợp,
dùng {{"listings":[]}}. Không đưa URL do mình tự dựng vào JSON.
"""


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def classify_source_url(url: Any) -> str:
    """Classify URL shape conservatively; this does not prove page contents."""
    if not isinstance(url, str) or not url.strip():
        return "INVALID_URL"
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "INVALID_URL"
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return "INVALID_URL"

    path = parts.path.casefold().rstrip("/")
    host = parts.hostname.casefold().removeprefix("www.")
    query = parse_qs(parts.query)
    if not path or path in {"/search", "/tim-kiem", "/category", "/categories"}:
        return "CATEGORY_PAGE"
    if any(
        key.casefold() in {"q", "query", "keyword", "page", "filter", "category"} for key in query
    ):
        return "CATEGORY_PAGE"
    if re.search(r"/(?:tin-tuc|news|blog|kinh-nghiem|du-an)(?:/|$)", path):
        return "ARTICLE_OR_PROJECT_PAGE"

    has_listing_id = bool(
        re.search(r"(?:^|/)(?:p|pr|id|tin|item)[-_]?\d{4,}(?:/|$)", path)
        or re.search(r"-[a-z]*\d{6,}(?:/|$)", path)
        or any(key.casefold() in {"id", "listing_id", "post_id"} for key in query)
    )
    if has_listing_id:
        return "LISTING_DETAIL_CANDIDATE"

    category_markers = (
        "/bat-dong-san/",
        "/nha-dat-ban/",
        "/mua-ban-nha-dat/",
        "/ban-bat-dong-san/",
        "/properties/",
    )
    if any(marker in f"{path}/" for marker in category_markers):
        return "CATEGORY_PAGE"
    if host in {"muaban.net", "batdongsan.com.vn", "alonhadat.com.vn"}:
        return "UNKNOWN_PAGE"
    return "UNKNOWN_PAGE"


def serialize_sources(sources: list[Any] | None) -> list[dict[str, Any]]:
    """Preserve source identifiers and URLs from DeepResearchDocument.sources."""
    serialized: list[dict[str, Any]] = []
    for source in sources or []:
        source_id = _value(source, "id")
        if source_id is None:
            continue
        url = _value(source, "url")
        serialized.append(
            {
                "id": str(source_id),
                "title": _value(source, "title"),
                "url": url,
                "favicon": _value(source, "favicon"),
                "source_kind": classify_source_url(url),
            }
        )
    return serialized


def parse_report_listings(report_text: str) -> tuple[list[dict[str, Any]], str]:
    """Read only an explicit JSON listings block; do not mine prose for facts."""
    if not isinstance(report_text, str) or not report_text.strip():
        return [], "EMPTY_DOCUMENT"

    blocks = re.finditer(
        r"```(?P<language>[a-zA-Z0-9_-]*)\s*\r?\n(?P<body>[\s\S]*?)```",
        report_text,
    )
    for match in blocks:
        body = match.group("body").strip()
        if match.group("language").casefold() not in {"", "json"}:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("listings"), list):
            return [item for item in parsed["listings"] if isinstance(item, dict)], "JSON_BLOCK"

    stripped = report_text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("listings"), list):
            return [item for item in parsed["listings"] if isinstance(item, dict)], "JSON_DOCUMENT"
    return [], "NO_STRUCTURED_LISTINGS_BLOCK"


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _decimal_spellings(value: Decimal) -> set[str]:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    spellings = {normalized}
    if "." in normalized:
        spellings.add(normalized.replace(".", ","))
    return spellings


def _matches_price(price_vnd: int, text: str) -> bool:
    compact_digits = re.sub(r"\D", "", text)
    if str(price_vnd) in compact_digits:
        return True
    for scale, units in (
        (Decimal(1_000_000_000), r"(?:tỷ|tỉ|ty|bn)"),
        (Decimal(1_000_000), r"(?:triệu|trieu|tr)"),
    ):
        amount = Decimal(price_vnd) / scale
        for spelling in _decimal_spellings(amount):
            pattern = rf"(?<!\d){re.escape(spelling)}\s*{units}(?!\w)"
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
    return False


def _matches_area(area_m2: float, text: str) -> bool:
    amount = _as_decimal(area_m2)
    if amount is None:
        return False
    units = r"(?:m\s*[²2]|sqm|mét\s+vuông|met\s+vuong)"
    return any(
        re.search(
            rf"(?<!\d){re.escape(spelling)}\s*{units}(?![a-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
        for spelling in _decimal_spellings(amount)
    )


def _location_matches_source(target: dict[str, Any], text: str) -> bool:
    normalized = norm(text)
    ward = norm(target.get("ward", ""))
    ward_short = re.sub(r"^(?:phuong|xa|thi tran)\s+", "", ward)
    district = norm(target.get("district", ""))
    province = norm(target.get("province", ""))
    region_matches = bool(
        (district and district in normalized) or (province and province in normalized)
    )
    return bool(
        ward_short
        and ward_short in normalized
        and region_matches
        and not _explicit_address_ward_conflicts(text, target)
    )


def _explicit_address_ward_conflicts(address: str, target: dict[str, Any]) -> bool:
    match = re.search(
        r"\b(?:phường|phuong|xã|xa|thị trấn|thi tran)\s+([^,;.\n]+)",
        address,
        re.IGNORECASE,
    )
    if not match:
        return False
    actual = norm(match.group(0))
    expected = norm(target.get("ward", ""))
    return bool(actual and expected and actual != expected)


def _verify_source_text(
    candidate: dict[str, Any], target: dict[str, Any], page_text: str
) -> dict[str, bool]:
    return {
        "price_match": _matches_price(candidate["price_vnd"], page_text),
        "area_match": _matches_area(candidate["area_m2"], page_text),
        "location_match": _location_matches_source(target, page_text),
    }


def analyze_research_document(
    report_text: str,
    sources: list[Any] | None,
    target: dict[str, Any],
    *,
    source_text_by_id: dict[str, str] | None = None,
    requested_count: int = 5,
) -> dict[str, Any]:
    """Map structured candidates to actual citation objects and classify evidence.

    `source_text_by_id` must come from a permitted source retrieval or a test fixture.
    The function never fetches URLs and never treats model-supplied URLs as citations.
    """
    source_records = serialize_sources(sources)
    source_map = {record["id"]: record for record in source_records}
    source_text_by_id = source_text_by_id or {}
    if not 1 <= requested_count <= 5:
        raise ValueError("Deep Research pilot count must be 1..5")
    raw_candidates, parse_status = parse_report_listings(report_text)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    for index, raw in enumerate(raw_candidates, start=1):
        if index > requested_count:
            rejected.append({"index": index, "reason": "requested_count_exceeded", "raw": raw})
            continue
        if str(raw.get("record_type", raw.get("estimate_type", ""))).upper() == "AI_ESTIMATE":
            rejected.append({"index": index, "reason": "ai_estimate_not_listing", "raw": raw})
            continue
        rank_value = raw.get("target_rank", target["rank"])
        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            rejected.append({"index": index, "reason": "bad_target_rank", "raw": raw})
            continue
        source_ids_raw = raw.get("source_citation_ids", [])
        if isinstance(source_ids_raw, (str, int)):
            source_ids_raw = [source_ids_raw]
        if not isinstance(source_ids_raw, list):
            source_ids_raw = []
        source_ids = list(
            dict.fromkeys(str(value) for value in source_ids_raw if value is not None)
        )
        linked_sources = [
            source_map[source_id] for source_id in source_ids if source_id in source_map
        ]
        usable_sources = [
            source
            for source in linked_sources
            if source["source_kind"] != "INVALID_URL"
            and isinstance(source.get("url"), str)
            and source["url"].strip()
        ]
        missing_source_ids = [source_id for source_id in source_ids if source_id not in source_map]
        source_urls = [source["url"] for source in usable_sources]
        first_https_url = next(
            (
                source["url"]
                for source in usable_sources
                if urlsplit(source["url"]).scheme.casefold() == "https"
            ),
            None,
        )
        item = {
            "target_rank": rank,
            "original_ward": target["ward"],
            "property_type": raw.get("property_type"),
            "title": raw.get("title"),
            "address": raw.get("address"),
            "price_vnd": raw.get("price_vnd"),
            "area_m2": raw.get("area_m2"),
            "source_url": first_https_url,
            "source_website": urlsplit(first_https_url).hostname if first_https_url else None,
            "published_at": raw.get("published_at"),
            "evidence_status": UNVERIFIED,
        }
        validated, reason = validate_listing(item, {int(target["rank"]): target})
        if reason:
            rejected.append({"index": index, "reason": reason, "raw": raw})
            continue

        if _explicit_address_ward_conflicts(validated["address"], target):
            rejected.append({"index": index, "reason": "wrong_ward_quarantined", "raw": raw})
            continue
        verification_by_source: dict[str, dict[str, bool]] = {}
        for source in usable_sources:
            page_text = source_text_by_id.get(source["id"])
            if page_text and source["source_kind"] == "LISTING_DETAIL_CANDIDATE":
                verification_by_source[source["id"]] = _verify_source_text(
                    validated, target, page_text
                )

        if validated["geo_status"] == "MISMATCH":
            rejected.append({"index": index, "reason": "wrong_ward_quarantined", "raw": raw})
            continue

        if validated["geo_status"] != "MATCH" or not usable_sources:
            evidence_status = UNVERIFIED
        elif all(source["source_kind"] == "CATEGORY_PAGE" for source in usable_sources):
            evidence_status = CATEGORY_ONLY
        elif any(all(checks.values()) for checks in verification_by_source.values()):
            evidence_status = SOURCE_VERIFIED
        elif any(any(checks.values()) for checks in verification_by_source.values()) or any(
            source["source_kind"] != "CATEGORY_PAGE" for source in usable_sources
        ):
            evidence_status = SOURCE_PARTIAL
        else:
            evidence_status = UNVERIFIED

        detail_url = next(
            (
                source["url"]
                for source in usable_sources
                if source["source_kind"] == "LISTING_DETAIL_CANDIDATE"
            ),
            None,
        )
        fingerprint_source = detail_url or "|".join(
            [
                str(rank),
                norm(validated["property_type"]),
                norm(validated["title"]),
                norm(validated["address"]),
                str(validated["price_vnd"]),
                str(validated["area_m2"]),
            ]
        )
        candidate_fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
        if candidate_fingerprint in seen_fingerprints:
            rejected.append({"index": index, "reason": "exact_duplicate", "raw": raw})
            continue
        seen_fingerprints.add(candidate_fingerprint)
        accepted.append(
            {
                "candidate_index": index,
                **validated,
                "evidence_status": evidence_status,
                "source_citation_ids": [source["id"] for source in linked_sources],
                "source_urls": source_urls,
                "source_kinds": [source["source_kind"] for source in linked_sources],
                "missing_source_citation_ids": missing_source_ids,
                "verification_by_source": verification_by_source,
                "raw_candidate": raw,
                "research_fingerprint": candidate_fingerprint,
            }
        )

    source_kinds = Counter(record["source_kind"] for record in source_records)
    candidate_statuses = Counter(row["evidence_status"] for row in accepted)
    if not report_text.strip():
        web_search_status = WEB_SEARCH_UNAVAILABLE
    elif not source_records:
        web_search_status = "NO_SOURCES_RETURNED"
    else:
        web_search_status = "SOURCES_RETURNED"
    return {
        "report_parse_status": parse_status,
        "web_search_status": web_search_status,
        "sources": source_records,
        "source_count": len(source_records),
        "source_kind_counts": dict(source_kinds),
        "candidates": accepted,
        "candidate_count": len(accepted),
        "invalid_candidate_count": len(rejected),
        "duplicate_count": sum(row["reason"] == "exact_duplicate" for row in rejected),
        "rejected_candidates": rejected,
        "candidate_evidence_counts": dict(candidate_statuses),
        "source_verified_count": candidate_statuses[SOURCE_VERIFIED],
        "source_partial_count": candidate_statuses[SOURCE_PARTIAL],
        "category_only_count": candidate_statuses[CATEGORY_ONLY],
        "unverified_count": candidate_statuses[UNVERIFIED],
    }


def initialize_research_schema(connection: sqlite3.Connection) -> None:
    """Create only namespaced audit tables in the adapter's sidecar database."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS webpilot_research_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            target_rank INTEGER NOT NULL,
            requested_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            web_search_status TEXT NOT NULL DEFAULT 'WEB_SEARCH_UNAVAILABLE',
            prompt_text TEXT NOT NULL,
            plan_json TEXT NOT NULL DEFAULT '{}',
            document_id TEXT,
            document_title TEXT,
            raw_document_text TEXT NOT NULL DEFAULT '',
            sources_json TEXT NOT NULL DEFAULT '[]',
            result_metadata_json TEXT NOT NULL DEFAULT '{}',
            candidate_count INTEGER NOT NULL DEFAULT 0,
            invalid_candidate_count INTEGER NOT NULL DEFAULT 0,
            evidence_counts_json TEXT NOT NULL DEFAULT '{}',
            raw_document_path TEXT,
            sources_path TEXT,
            error_text TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_webpilot_research_runs_date
            ON webpilot_research_runs(occurred_at);
        CREATE TABLE IF NOT EXISTS webpilot_research_sources (
            run_id INTEGER NOT NULL,
            citation_id TEXT NOT NULL,
            title TEXT,
            url TEXT,
            source_kind TEXT NOT NULL,
            raw_source_json TEXT NOT NULL,
            PRIMARY KEY(run_id, citation_id),
            FOREIGN KEY(run_id) REFERENCES webpilot_research_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS webpilot_research_candidates (
            run_id INTEGER NOT NULL,
            candidate_index INTEGER NOT NULL,
            fingerprint TEXT NOT NULL,
            title TEXT NOT NULL,
            address TEXT NOT NULL,
            property_type TEXT NOT NULL,
            price_vnd INTEGER NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            evidence_status TEXT NOT NULL CHECK(evidence_status IN (
                'SOURCE_VERIFIED','SOURCE_PARTIAL','CATEGORY_ONLY','UNVERIFIED'
            )),
            source_citation_ids_json TEXT NOT NULL,
            source_urls_json TEXT NOT NULL,
            verification_json TEXT NOT NULL,
            raw_candidate_json TEXT NOT NULL,
            PRIMARY KEY(run_id, candidate_index),
            FOREIGN KEY(run_id) REFERENCES webpilot_research_runs(run_id)
        );
        """
    )
    connection.commit()


def start_research_run(
    connection: sqlite3.Connection,
    *,
    target_rank: int,
    requested_count: int,
    prompt_text: str,
    status: str = "LIVE_STARTED",
) -> int:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")
    with connection:
        cursor = connection.execute(
            """INSERT INTO webpilot_research_runs(
                occurred_at,target_rank,requested_count,status,prompt_text
                ) VALUES(?,?,?,?,?)""",
            (now, target_rank, requested_count, status, prompt_text),
        )
    return int(cursor.lastrowid)


def save_research_result(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    web_search_status: str,
    analysis: dict[str, Any],
    plan: dict[str, Any] | None,
    document_id: str | None,
    document_title: str | None,
    raw_document_text: str,
    result_metadata: dict[str, Any],
    raw_document_path: str | None = None,
    sources_path: str | None = None,
    error_text: str | None = None,
) -> None:
    sources = analysis["sources"]
    candidates = analysis["candidates"]
    with connection:
        connection.execute(
            """UPDATE webpilot_research_runs SET status=?,web_search_status=?,plan_json=?,
               document_id=?,document_title=?,raw_document_text=?,sources_json=?,
               result_metadata_json=?,candidate_count=?,invalid_candidate_count=?,
               evidence_counts_json=?,raw_document_path=?,sources_path=?,error_text=?
               WHERE run_id=?""",
            (
                status,
                web_search_status,
                json.dumps(plan or {}, ensure_ascii=False, sort_keys=True),
                document_id,
                document_title,
                raw_document_text,
                json.dumps(sources, ensure_ascii=False, sort_keys=True),
                json.dumps(result_metadata, ensure_ascii=False, sort_keys=True),
                analysis["candidate_count"],
                analysis["invalid_candidate_count"],
                json.dumps(
                    analysis["candidate_evidence_counts"], ensure_ascii=False, sort_keys=True
                ),
                raw_document_path,
                sources_path,
                error_text,
                run_id,
            ),
        )
        connection.execute("DELETE FROM webpilot_research_sources WHERE run_id=?", (run_id,))
        connection.execute("DELETE FROM webpilot_research_candidates WHERE run_id=?", (run_id,))
        connection.executemany(
            """INSERT INTO webpilot_research_sources(
                run_id,citation_id,title,url,source_kind,raw_source_json
            ) VALUES(?,?,?,?,?,?)""",
            [
                (
                    run_id,
                    source["id"],
                    source.get("title"),
                    source.get("url"),
                    source["source_kind"],
                    json.dumps(source, ensure_ascii=False, sort_keys=True),
                )
                for source in sources
            ],
        )
        connection.executemany(
            """INSERT INTO webpilot_research_candidates(
                run_id,candidate_index,fingerprint,title,address,property_type,price_vnd,
                area_m2,price_per_m2,evidence_status,source_citation_ids_json,
                source_urls_json,verification_json,raw_candidate_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    run_id,
                    candidate["candidate_index"],
                    candidate["research_fingerprint"],
                    candidate["title"],
                    candidate["address"],
                    candidate["property_type"],
                    candidate["price_vnd"],
                    candidate["area_m2"],
                    candidate["price_per_m2"],
                    candidate["evidence_status"],
                    json.dumps(candidate["source_citation_ids"], ensure_ascii=False),
                    json.dumps(candidate["source_urls"], ensure_ascii=False),
                    json.dumps(
                        candidate["verification_by_source"], ensure_ascii=False, sort_keys=True
                    ),
                    json.dumps(candidate["raw_candidate"], ensure_ascii=False, sort_keys=True),
                )
                for candidate in candidates
            ],
        )


def fail_research_run(connection: sqlite3.Connection, run_id: int, error_text: str) -> None:
    with connection:
        connection.execute(
            "UPDATE webpilot_research_runs SET status='LIVE_FAILED',web_search_status=?,error_text=? WHERE run_id=?",
            (WEB_SEARCH_UNAVAILABLE, error_text[:1000], run_id),
        )


def research_status(connection: sqlite3.Connection, limit: int = 20) -> dict[str, Any]:
    rows = connection.execute(
        """SELECT run_id,occurred_at,target_rank,requested_count,status,web_search_status,
                  document_title,candidate_count,invalid_candidate_count,evidence_counts_json,
                  raw_document_path,sources_path,error_text
           FROM webpilot_research_runs ORDER BY run_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return {"research_runs": [dict(row) for row in rows], "count": len(rows)}
