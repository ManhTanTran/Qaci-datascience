"""Offline validation and audit storage for optional Gemini Web candidates.

The Web pilot never writes to WardPriceDaily's canonical listing tables. Its
audit tables are namespaced and every candidate remains UNVERIFIED until a
separate source review is implemented.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

VALID_TYPES = {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
EVIDENCE_UNVERIFIED = "UNVERIFIED"


def norm(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def load_targets(database: Path) -> dict[int, dict[str, str]]:
    """Read the imported legacy target registry without exposing customer columns."""
    if not database.is_file():
        raise FileNotFoundError(f"Target database not found: {database}")
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """SELECT rank, old_ward, old_district, old_province
               FROM ward_target_legacy ORDER BY rank"""
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("Database is missing ward_target_legacy") from exc
    finally:
        connection.close()

    targets: dict[int, dict[str, str]] = {}
    for rank_value, ward, district, province in rows:
        rank = int(rank_value)
        if rank in targets or not 1 <= rank <= 50:
            raise ValueError(f"Bad or duplicate target rank: {rank}")
        targets[rank] = {
            "rank": rank,
            "ward": str(ward).strip(),
            "district": str(district).strip(),
            "province": str(province).strip(),
        }
    if set(targets) != set(range(1, 51)):
        raise ValueError("Expected exactly 50 numbered targets in ward_target_legacy")
    return targets


def plan_slot(start_date: date, requested_date: date, slot: int) -> int:
    if not 1 <= slot <= 5:
        raise ValueError("Slot must be 1..5")
    elapsed = (requested_date - start_date).days
    if elapsed < 0:
        raise ValueError("Requested date is earlier than schedule start")
    return (elapsed % 10) * 5 + slot


def parse_json_text(text: str) -> dict[str, Any] | list[Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Response text is empty")
    source = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", source, flags=re.IGNORECASE)
    if fence:
        source = fence.group(1).strip()
    try:
        result = json.loads(source)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        result = None
        for match in re.finditer(r"[\[{]", source):
            try:
                result, _ = decoder.raw_decode(source[match.start() :])
                break
            except json.JSONDecodeError:
                continue
        if result is None:
            raise ValueError("No valid JSON object or array in response") from None
    if not isinstance(result, (dict, list)):
        raise TypeError("JSON output must be an object or array")
    return result


def _ward_name(ward: str) -> str:
    return re.sub(r"^(phuong|xa|thi tran)\s+", "", norm(ward)).strip()


def geo_check(address: str, target_ward: str) -> str:
    """Conservative text check; this is not geocoding or source verification."""
    normalized_address = norm(address)
    target = _ward_name(target_ward)
    if not normalized_address or not target:
        return "REVIEW"

    exact_prefix = re.compile(r"\b(?:phuong|xa)\s+" + re.escape(target) + r"\b(?:\s+([a-z0-9]+))?")
    match = exact_prefix.search(normalized_address)
    if match:
        next_token = match.group(1)
        if next_token and (
            (len(next_token) == 1 and next_token.isalpha())
            or next_token.isdigit()
            or next_token in {"hoa", "dong", "tay", "bac", "nam"}
        ):
            return "MISMATCH"
        return "MATCH"

    if re.search(r"\b" + re.escape(target) + r"\b", normalized_address):
        return "REVIEW"
    parts = target.split()
    if len(parts) > 1 and re.search(
        r"\b(?:phuong|xa)\s+" + re.escape(" ".join(parts[:-1])) + r"\s+\S+",
        normalized_address,
    ):
        return "MISMATCH"
    return "REVIEW"


def _date_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _valid_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname:
        return None
    return url


def _canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), host, path, "", ""))


def validate_listing(
    item: dict[str, Any], targets: dict[int, dict[str, str]]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        rank = int(item["target_rank"])
        target = targets[rank]
    except (KeyError, TypeError, ValueError):
        return None, "bad_target_rank"
    if norm(item.get("original_ward", "")) != norm(target["ward"]):
        return None, "target_ward_disagrees_with_registry"

    property_type = str(item.get("property_type", "")).strip().upper()
    if property_type not in VALID_TYPES:
        return None, "bad_property_type"
    try:
        raw_price = item.get("price_vnd")
        raw_area = item.get("area_m2")
        if isinstance(raw_price, bool) or isinstance(raw_area, bool):
            return None, "bad_price_or_area"
        price = int(raw_price)
        area = float(raw_area)
    except (TypeError, ValueError, OverflowError):
        return None, "bad_price_or_area"
    if price <= 0 or price > 10**16 or not (0 < area < 10_000_000):
        return None, "bad_price_or_area"

    title = str(item.get("title", "")).strip()
    address = str(item.get("address", "")).strip()
    if len(title) < 5 or len(address) < 4:
        return None, "missing_title_or_address"

    source_url = _valid_url(item.get("source_url"))
    website = str(item.get("source_website") or "").strip() or None
    published_at = _date_str(item.get("published_at"))
    identity = _canonical_url(source_url) or "|".join(
        [str(rank), property_type, norm(title), norm(address)]
    )
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "fingerprint": fingerprint,
        "target_rank": rank,
        "original_ward": target["ward"],
        "original_district": target["district"],
        "original_province": target["province"],
        "property_type": property_type,
        "title": title,
        "address": address,
        "price_vnd": price,
        "area_m2": area,
        "price_per_m2": price / area,
        "source_website": website,
        "source_url": source_url,
        "published_at": published_at,
        "collected_at": datetime.now(timezone.utc).astimezone().date().isoformat(),
        # Model-provided labels, URLs and search claims are not evidence.
        "evidence_status": EVIDENCE_UNVERIFIED,
        "requested_evidence_status": str(item.get("evidence_status", "")).strip().upper(),
        # Keep the model's claim in raw_payload, but never treat it as a verified read.
        "source_page_read": False,
        "price_evidence": str(item.get("price_evidence") or "").strip(),
        "area_evidence": str(item.get("area_evidence") or "").strip(),
        "evidence_excerpt": str(item.get("evidence_excerpt") or "").strip(),
        "geo_status": geo_check(address, target["ward"]),
        "possible_duplicate": item.get("possible_duplicate") is True,
        "raw_payload": json.dumps(item, ensure_ascii=False, sort_keys=True),
    }, None


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS webpilot_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            origin TEXT NOT NULL,
            requested_rank INTEGER,
            search_claim TEXT NOT NULL,
            citation_count INTEGER NOT NULL DEFAULT 0,
            citations_json TEXT NOT NULL DEFAULT '[]',
            citation_url_match_count INTEGER NOT NULL DEFAULT 0,
            prompt_text TEXT,
            raw_response_text TEXT,
            request_metadata_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            accepted_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            quarantined_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS webpilot_candidates (
            fingerprint TEXT PRIMARY KEY,
            target_rank INTEGER NOT NULL,
            original_ward TEXT NOT NULL,
            original_district TEXT NOT NULL,
            original_province TEXT NOT NULL,
            property_type TEXT NOT NULL,
            title TEXT NOT NULL,
            address TEXT NOT NULL,
            price_vnd INTEGER NOT NULL,
            area_m2 REAL NOT NULL,
            price_per_m2 REAL NOT NULL,
            source_website TEXT,
            source_url TEXT,
            published_at TEXT,
            collected_at TEXT NOT NULL,
            evidence_status TEXT NOT NULL CHECK(
                evidence_status IN ('UNVERIFIED','SEARCH_SNIPPET_ONLY','SOURCE_PAGE_CONFIRMED')
            ),
            geo_status TEXT NOT NULL,
            possible_duplicate INTEGER NOT NULL,
            quarantine_reason TEXT,
            source_page_read INTEGER NOT NULL DEFAULT 0,
            price_evidence TEXT NOT NULL DEFAULT '',
            area_evidence TEXT NOT NULL DEFAULT '',
            evidence_excerpt TEXT NOT NULL DEFAULT '',
            raw_payload TEXT NOT NULL,
            first_run_id INTEGER NOT NULL,
            FOREIGN KEY(first_run_id) REFERENCES webpilot_runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS ix_webpilot_candidates_rank
            ON webpilot_candidates(target_rank, property_type);
        """
    )
    connection.commit()
    return connection


def start_run(
    connection: sqlite3.Connection,
    *,
    origin: str,
    requested_rank: int | None = None,
    prompt_text: str | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = json.dumps(request_metadata or {}, ensure_ascii=False, sort_keys=True)
    with connection:
        cursor = connection.execute(
            """INSERT INTO webpilot_runs(
                occurred_at,origin,requested_rank,search_claim,prompt_text,
                request_metadata_json,status
            ) VALUES(?,?,?,?,?,?,?)""",
            (now, origin, requested_rank, "NOT_STATED", prompt_text, metadata, "STARTED"),
        )
    return int(cursor.lastrowid)


def _citation_match_count(listings: list[Any], citations: list[dict[str, Any]]) -> int:
    cited_urls = {
        _canonical_url(_valid_url(item.get("url"))) for item in citations if isinstance(item, dict)
    }
    cited_urls.discard(None)
    return sum(
        1
        for item in listings
        if isinstance(item, dict)
        and _canonical_url(_valid_url(item.get("source_url"))) in cited_urls
    )


def _url_matches_citation(url: str | None, citations: list[dict[str, Any]]) -> bool:
    canonical = _canonical_url(_valid_url(url))
    if not canonical:
        return False
    return any(
        _canonical_url(_valid_url(citation.get("url"))) == canonical
        for citation in citations
        if isinstance(citation, dict)
    )


def _evidence_status(
    item: dict[str, Any], candidate: dict[str, Any], citations: list[dict[str, Any]]
) -> str:
    """Return snippet evidence only; wrapper citations do not confirm page contents."""
    has_cited_source = _url_matches_citation(candidate.get("source_url"), citations)
    has_price_and_area_quotes = (
        len(candidate["price_evidence"]) >= 3 and len(candidate["area_evidence"]) >= 3
    )
    requested = candidate["requested_evidence_status"]
    if not (has_cited_source and has_price_and_area_quotes):
        return EVIDENCE_UNVERIFIED
    # A model's claim that it read a page is not independent confirmation. The
    # wrapper returns citation URLs, not proof that the detail page was fetched.
    if requested in {"SEARCH_SNIPPET_ONLY", "SOURCE_PAGE_CONFIRMED"}:
        return "SEARCH_SNIPPET_ONLY"
    return EVIDENCE_UNVERIFIED


def process_payload(
    connection: sqlite3.Connection,
    run_id: int,
    payload: dict[str, Any] | list[Any],
    targets: dict[int, dict[str, str]],
    *,
    raw_response_text: str = "",
    requested_rank: int | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if isinstance(payload, list):
        listings = payload
        search_value = None
    else:
        listings = payload.get("listings")
        search_value = payload.get("web_search_used")
    if not isinstance(listings, list):
        raise TypeError("Expected 'listings' array")
    if len(listings) > 500:
        raise ValueError("Batch too large (>500)")

    search_claim = (
        "NO_WEB_SEARCH"
        if search_value is False
        else "SELF_REPORTED_SEARCH"
        if search_value is True
        else "NOT_STATED"
    )
    citations = citations or []
    inserted = duplicate = rejected = quarantined = citation_matches = 0
    reject_reasons: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    citation_matches = _citation_match_count(listings, citations)

    with connection:
        for item in listings:
            if not isinstance(item, dict):
                rejected += 1
                reject_reasons["not_an_object"] += 1
                continue
            validated, error = validate_listing(item, targets)
            if error:
                rejected += 1
                reject_reasons[error] += 1
                continue
            assert validated is not None
            if requested_rank is not None and validated["target_rank"] != requested_rank:
                rejected += 1
                reject_reasons["wrong_requested_rank"] += 1
                continue

            quarantine_reasons = []
            if validated["geo_status"] != "MATCH":
                quarantine_reasons.append(f"GEO_{validated['geo_status']}")
            if validated["possible_duplicate"]:
                quarantine_reasons.append("MODEL_FLAGGED_POSSIBLE_DUPLICATE")
            if quarantine_reasons:
                quarantined += 1
            validated["evidence_status"] = _evidence_status(item, validated, citations)
            evidence_counts[validated["evidence_status"]] += 1

            fields = (
                "fingerprint",
                "target_rank",
                "original_ward",
                "original_district",
                "original_province",
                "property_type",
                "title",
                "address",
                "price_vnd",
                "area_m2",
                "price_per_m2",
                "source_website",
                "source_url",
                "published_at",
                "collected_at",
                "evidence_status",
                "geo_status",
                "possible_duplicate",
                "quarantine_reason",
                "source_page_read",
                "price_evidence",
                "area_evidence",
                "evidence_excerpt",
                "raw_payload",
            )
            values = [validated[key] for key in fields[:-6]]
            values.extend(
                [
                    ";".join(quarantine_reasons) or None,
                    int(validated["source_page_read"]),
                    validated["price_evidence"],
                    validated["area_evidence"],
                    validated["evidence_excerpt"],
                    validated["raw_payload"],
                ]
            )
            existing = connection.execute(
                """SELECT evidence_status,price_vnd,area_m2,address,title,source_url,first_run_id
                   FROM webpilot_candidates WHERE fingerprint=?""",
                (validated["fingerprint"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO webpilot_candidates(
                        fingerprint,target_rank,original_ward,original_district,original_province,
                        property_type,title,address,price_vnd,area_m2,price_per_m2,source_website,
                        source_url,published_at,collected_at,evidence_status,geo_status,
                        possible_duplicate,quarantine_reason,source_page_read,price_evidence,
                        area_evidence,evidence_excerpt,raw_payload,first_run_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [*values, run_id],
                )
                inserted += 1
            else:
                duplicate += 1
                previous_evidence = existing["evidence_status"]
                evidence_rank = {
                    "UNVERIFIED": 0,
                    "SEARCH_SNIPPET_ONLY": 1,
                    "SOURCE_PAGE_CONFIRMED": 2,
                }
                content_unchanged = all(
                    existing[field] == validated[field]
                    for field in ("price_vnd", "area_m2", "address", "title", "source_url")
                )
                if content_unchanged:
                    stored_evidence = max(
                        (previous_evidence, validated["evidence_status"]),
                        key=evidence_rank.__getitem__,
                    )
                    stored_run_id = (
                        run_id
                        if evidence_rank[validated["evidence_status"]]
                        >= evidence_rank[previous_evidence]
                        else existing["first_run_id"]
                    )
                else:
                    stored_evidence = validated["evidence_status"]
                    stored_run_id = run_id
                connection.execute(
                    """UPDATE webpilot_candidates SET
                        original_ward=?,original_district=?,original_province=?,property_type=?,
                        title=?,address=?,price_vnd=?,area_m2=?,price_per_m2=?,source_website=?,
                        source_url=?,published_at=COALESCE(?,published_at),collected_at=?,
                        evidence_status=?,geo_status=?,possible_duplicate=?,quarantine_reason=?,
                        source_page_read=?,price_evidence=?,area_evidence=?,evidence_excerpt=?,
                        raw_payload=?,first_run_id=? WHERE fingerprint=?""",
                    (
                        validated["original_ward"],
                        validated["original_district"],
                        validated["original_province"],
                        validated["property_type"],
                        validated["title"],
                        validated["address"],
                        validated["price_vnd"],
                        validated["area_m2"],
                        validated["price_per_m2"],
                        validated["source_website"],
                        validated["source_url"],
                        validated["published_at"],
                        validated["collected_at"],
                        stored_evidence,
                        validated["geo_status"],
                        int(validated["possible_duplicate"]),
                        ";".join(quarantine_reasons) or None,
                        int(validated["source_page_read"]),
                        validated["price_evidence"],
                        validated["area_evidence"],
                        validated["evidence_excerpt"],
                        validated["raw_payload"],
                        stored_run_id,
                        validated["fingerprint"],
                    ),
                )

        result_json = json.dumps(
            {"listings_count": len(listings), "rejected_reasons": dict(reject_reasons)},
            ensure_ascii=False,
            sort_keys=True,
        )
        connection.execute(
            """UPDATE webpilot_runs SET raw_response_text=?,result_json=?,search_claim=?,
                citation_count=?,citations_json=?,citation_url_match_count=?,accepted_count=?,
                duplicate_count=?,rejected_count=?,quarantined_count=?,status='IMPORTED'
                WHERE run_id=?""",
            (
                raw_response_text,
                result_json,
                search_claim,
                len(citations),
                json.dumps(citations, ensure_ascii=False, sort_keys=True),
                citation_matches,
                inserted,
                duplicate,
                rejected,
                quarantined,
                run_id,
            ),
        )
    return {
        "run_id": run_id,
        "received": len(listings),
        "inserted_candidates": inserted,
        "duplicates_exact": duplicate,
        "rejected": rejected,
        "rejected_reasons": dict(reject_reasons),
        "quarantined": quarantined,
        "web_search_claim": search_claim,
        "citations_reported_by_wrapper": len(citations),
        "wrapper_citations": citations,
        "listing_source_urls": [
            item.get("source_url")
            for item in listings
            if isinstance(item, dict) and item.get("source_url")
        ],
        "listing_urls_matching_citations": citation_matches,
        "price_area_valid_count": inserted + duplicate,
        "evidence_status_counts": dict(evidence_counts),
        "source_verified_count": 0,
        "note": "Wrapper citations and model excerpts are audit signals; none is independently source-verified.",
    }


def import_payload(
    connection: sqlite3.Connection,
    payload: dict[str, Any] | list[Any],
    targets: dict[int, dict[str, str]],
    origin: str = "manual_json",
    requested_rank: int | None = None,
    citations: list[dict[str, Any]] | None = None,
    *,
    raw_response_text: str = "",
    prompt_text: str | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = start_run(
        connection,
        origin=origin,
        requested_rank=requested_rank,
        prompt_text=prompt_text,
        request_metadata=request_metadata,
    )
    return process_payload(
        connection,
        run_id,
        payload,
        targets,
        raw_response_text=raw_response_text,
        requested_rank=requested_rank,
        citations=citations,
    )


def import_response(
    connection: sqlite3.Connection,
    response_text: str,
    targets: dict[int, dict[str, str]],
    *,
    origin: str,
    requested_rank: int | None = None,
    prompt_text: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = start_run(
        connection,
        origin=origin,
        requested_rank=requested_rank,
        prompt_text=prompt_text,
        request_metadata=request_metadata,
    )
    return process_response_for_run(
        connection,
        run_id,
        response_text,
        targets,
        requested_rank=requested_rank,
        citations=citations,
    )


def process_response_for_run(
    connection: sqlite3.Connection,
    run_id: int,
    response_text: str,
    targets: dict[int, dict[str, str]],
    *,
    requested_rank: int | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse and import one response into an already-created audit run."""
    if not response_text.strip():
        with connection:
            connection.execute(
                "UPDATE webpilot_runs SET raw_response_text=?,status='EMPTY_RESPONSE' WHERE run_id=?",
                (response_text, run_id),
            )
        return {"run_id": run_id, "status": "EMPTY_RESPONSE", "received": 0}
    try:
        payload = parse_json_text(response_text)
    except ValueError as exc:
        with connection:
            connection.execute(
                """UPDATE webpilot_runs SET raw_response_text=?,status='PARSE_FAILURE',
                   result_json=? WHERE run_id=?""",
                (response_text, json.dumps({"error": str(exc)}, ensure_ascii=False), run_id),
            )
        return {"run_id": run_id, "status": "PARSE_FAILURE", "error": str(exc), "received": 0}
    try:
        return process_payload(
            connection,
            run_id,
            payload,
            targets,
            raw_response_text=response_text,
            requested_rank=requested_rank,
            citations=citations,
        )
    except (TypeError, ValueError) as exc:
        with connection:
            connection.execute(
                """UPDATE webpilot_runs SET raw_response_text=?,status='SCHEMA_FAILURE',
                   result_json=? WHERE run_id=?""",
                (response_text, json.dumps({"error": str(exc)}, ensure_ascii=False), run_id),
            )
        return {"run_id": run_id, "status": "SCHEMA_FAILURE", "error": str(exc), "received": 0}


def status(connection: sqlite3.Connection) -> dict[str, Any]:
    counts = connection.execute(
        """SELECT COUNT(*) AS candidate_count,
           SUM(CASE WHEN geo_status='MATCH' THEN 1 ELSE 0 END) AS geo_match,
           SUM(CASE WHEN geo_status='MISMATCH' THEN 1 ELSE 0 END) AS geo_mismatch,
           SUM(CASE WHEN geo_status='REVIEW' THEN 1 ELSE 0 END) AS geo_review,
           SUM(CASE WHEN source_url IS NOT NULL THEN 1 ELSE 0 END) AS url_count,
           SUM(CASE WHEN quarantine_reason IS NOT NULL THEN 1 ELSE 0 END) AS quarantined
           FROM webpilot_candidates"""
    ).fetchone()
    table_names = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    batch_candidate_count = 0
    batch_observation_count = 0
    source_conflict_count = 0
    if "webpilot_batch_candidates" in table_names:
        batch_candidate_count = connection.execute(
            "SELECT COUNT(*) FROM webpilot_batch_candidates"
        ).fetchone()[0]
        source_conflict_count = connection.execute(
            "SELECT COUNT(*) FROM webpilot_batch_candidates WHERE review_status='SOURCE_CONFLICT'"
        ).fetchone()[0]
    if "webpilot_batch_observations" in table_names:
        batch_observation_count = connection.execute(
            "SELECT COUNT(*) FROM webpilot_batch_observations"
        ).fetchone()[0]
    return {
        "candidate_count": (counts["candidate_count"] or 0) + batch_candidate_count,
        "live_candidate_count": counts["candidate_count"] or 0,
        "imported_batch_candidate_count": batch_candidate_count,
        "imported_batch_observation_count": batch_observation_count,
        "source_conflict_count": source_conflict_count,
        "geo_match": counts["geo_match"] or 0,
        "geo_mismatch": counts["geo_mismatch"] or 0,
        "geo_review": counts["geo_review"] or 0,
        "quarantined": counts["quarantined"] or 0,
        "url_present_unverified": counts["url_count"] or 0,
        "run_count": connection.execute("SELECT COUNT(*) FROM webpilot_runs").fetchone()[0],
        "verified_listing_count": 0,
        "statistics_eligible_candidate_count": 0,
        "disclaimer": "Web pilot records are audit candidates; none are source-verified.",
    }


def export(connection: sqlite3.Connection, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    rows = [
        dict(row)
        for row in connection.execute(
            """SELECT c.*,r.search_claim,r.citation_count,r.citation_url_match_count,
                      r.citations_json
               FROM webpilot_candidates c
               JOIN webpilot_runs r ON r.run_id=c.first_run_id
               ORDER BY c.target_rank,c.property_type,c.title"""
        )
    ]
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "webpilot_batch_candidates" in tables:
        batch_rows = connection.execute(
            """SELECT * FROM webpilot_batch_candidates
               ORDER BY target_rank,property_type,title"""
        ).fetchall()
        for source in batch_rows:
            row = dict(source)
            row.update(
                {
                    "collected_at": row["first_run_date"],
                    "search_claim": "NOT_STATED",
                    "citation_count": 0,
                    "citation_url_match_count": 0,
                    "citations_json": "[]",
                    "price_evidence": "",
                    "area_evidence": "",
                    "evidence_excerpt": "",
                }
            )
            rows.append(row)
    csv_path = output / "candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fieldnames = (
            list(dict.fromkeys(key for row in rows for key in row))
            if rows
            else [
                "target_rank",
                "original_ward",
                "property_type",
                "price_vnd",
                "area_m2",
                "evidence_status",
                "geo_status",
                "quarantine_reason",
            ]
        )
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Handoff requires a real wrapper citation matching the listing URL plus
    # price/area evidence text. Remaining candidates stay audit-only.
    eligible = [
        row
        for row in rows
        if row["evidence_status"] in {"SEARCH_SNIPPET_ONLY", "SOURCE_PAGE_CONFIRMED"}
        and row["geo_status"] == "MATCH"
        and not row["possible_duplicate"]
        and not row["quarantine_reason"]
        and row["source_url"]
        and row["price_evidence"]
        and row["area_evidence"]
    ]
    handoff_rows = [
        {
            "target_rank": row["target_rank"],
            "original_ward": row["original_ward"],
            "original_district": row["original_district"],
            "original_province": row["original_province"],
            "property_type": row["property_type"],
            "title": row["title"],
            "address": row["address"],
            "price_vnd": row["price_vnd"],
            "area_m2": row["area_m2"],
            "source_url": row["source_url"],
            "published_at": row["published_at"],
            "evidence_status": row["evidence_status"],
            "source_page_read": bool(row["source_page_read"]),
            "price_evidence": row["price_evidence"],
            "area_evidence": row["area_evidence"],
            "evidence_excerpt": row["evidence_excerpt"],
            "grounded_urls": [
                citation["url"]
                for citation in json.loads(row["citations_json"])
                if isinstance(citation, dict) and _valid_url(citation.get("url"))
            ],
        }
        for row in eligible
    ]
    handoff_path = output / "for_wardprice_import.json"
    handoff_path.write_text(
        json.dumps(
            {
                "producer": "wardprice_webpilot",
                "listings": handoff_rows,
                "warning": "Only independently evidenced rows may be promoted.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = {
        "candidate_count": len(rows),
        "evidence_status_counts": dict(Counter(row["evidence_status"] for row in rows)),
        "geo_status_counts": dict(Counter(row["geo_status"] for row in rows)),
        "review_status_counts": dict(
            Counter(row.get("review_status", "NEEDS_SOURCE_REVIEW") for row in rows)
        ),
        "source_url_type_counts": dict(
            Counter(row.get("source_url_type", "UNKNOWN") for row in rows)
        ),
        "quarantined_count": sum(bool(row["quarantine_reason"]) for row in rows),
        "canonical_handoff_count": len(handoff_rows),
        "statistics_computed": False,
        "note": "No price aggregates are calculated from unverified candidates.",
    }
    summary_path = output / "candidate_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "csv": str(csv_path),
        "import_json": str(handoff_path),
        "summary": str(summary_path),
        "eligible_candidates": len(handoff_rows),
    }


def make_prompt(target: dict[str, str], count: int = 5) -> str:
    if not 1 <= count <= 50:
        raise ValueError("count must be 1..50")
    return f"""Bạn đang thu thập dữ liệu thử nghiệm cho WardPriceDaily.
Tìm tối đa {count} tin rao BÁN BĐS RIÊNG BIỆT trong địa giới cũ:
- target_rank: {target["rank"]}
- phường/xã: {target["ward"]}
- quận/huyện cũ: {target["district"]}
- tỉnh/thành: {target["province"]}

Chỉ tìm tin rao cụ thể có giá bán tổng cộng, diện tích, địa chỉ thuộc đúng phường
được chỉ định và URL tin rao có thật. Không lấy tin cho thuê, giá AI ước tính,
bảng giá đất hoặc tin thuộc phường/xã khác. Không tự tạo URL, giá hay tin rao.
Chỉ xuất một listing khi có trích dẫn ngắn riêng cho price_evidence và area_evidence.
Nếu chỉ có snippet, evidence_status=SEARCH_SNIPPET_ONLY. Chỉ dùng
SOURCE_PAGE_CONFIRMED khi đã đọc trang chi tiết và source_page_read=true.
Không có URL hoặc trích dẫn khớp URL thì hệ thống giữ UNVERIFIED.
Nếu không tìm được tin phù hợp, trả listings=[]. Không tự tính giá/m² hoặc thống kê.

property_type chỉ được chọn: DAT_O, NHA_RIENG, CHUNG_CU.
Chỉ xuất JSON object, không có diễn giải hoặc markdown:
{{"listings":[{{"target_rank":{target["rank"]},"original_ward":{json.dumps(target["ward"], ensure_ascii=False)},"property_type":"DAT_O","title":"...","address":"...","price_vnd":123456789,"area_m2":60.0,"source_website":null,"source_url":"https://...","published_at":null,"evidence_status":"SEARCH_SNIPPET_ONLY","source_page_read":false,"price_evidence":"...","area_evidence":"...","evidence_excerpt":"..."}}]}}
Các giá trị ví dụ trong schema không phải listing thật; không sao chép chúng.
"""
