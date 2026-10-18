"""Local listing ingestion, deduplication and Python-only price statistics."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from openpyxl import load_workbook

from .national_registry import PROPERTY_TYPES, normalize_admin_name, search_administrative_units

AREA_BASES = {"LAND_AREA", "FLOOR_AREA", "USABLE_AREA", "OTHER"}
MAX_DAILY_OBSERVATIONS = 500
CALCULATION_VERSION = "listing-statistics-v1"


def _tabular_records(headers: list[Any], values: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    names = [str(header or "").strip() for header in headers]
    if not names or not any(names):
        raise ValueError("listing input has no header row")
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("listing input headers must be nonempty and unique")
    rows = []
    for row_number, values_row in enumerate(values, start=2):
        if not any(value is not None and str(value).strip() for value in values_row):
            continue
        if len(values_row) != len(names):
            raise ValueError(f"listing input row {row_number} does not match the header width")
        row = {}
        for name, value in zip(names, values_row, strict=True):
            if isinstance(value, (datetime, date)):
                value = value.isoformat()
            row[name] = value
        rows.append(row)
    return rows


def load_listing_payload(path: Path) -> Any:
    """Load a JSON, CSV, or XLSX listing batch without contacting external services."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".json":
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise ValueError("listing CSV is empty") from exc
            return _tabular_records(headers, list(reader))
    if suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet = next(
                (sheet for sheet in workbook.worksheets if sheet.title.casefold() in {
                    "listings", "national listings", "national_listings"
                }),
                workbook.active,
            )
            rows = worksheet.iter_rows(values_only=True)
            try:
                headers = list(next(rows))
            except StopIteration as exc:
                raise ValueError("listing workbook sheet is empty") from exc
            return _tabular_records(headers, list(rows))
        finally:
            workbook.close()
    raise ValueError("listing input must be a .json, .csv, or .xlsx file")


def canonicalize_source_url(value: Any) -> str:
    """Normalize a public HTTPS listing URL for stable deduplication."""
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme.casefold() != "https" or not parts.hostname:
        raise ValueError("source_url must be an absolute HTTPS URL")
    host = parts.hostname.casefold().rstrip(".")
    host = host.removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in {"gclid", "fbclid", "ref", "source"}
    ]
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if parsed <= 0 or not math.isfinite(parsed):
        raise ValueError(f"{field} must be a positive finite number")
    return parsed


def _resolve_current_unit(db: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    rank = row.get("target_rank")
    if rank is not None:
        target = db.execute(
            """SELECT DISTINCT pt.target_rank,pt.mapping_status,pm.administrative_unit_id,
                      u.administrative_code,u.administrative_name,u.province_name,
                      u.administrative_level,u.administrative_type,u.is_current
               FROM priority_targets pt
               LEFT JOIN priority_target_mappings pm ON pm.target_rank=pt.target_rank
               LEFT JOIN administrative_units u ON u.id=pm.administrative_unit_id
                 AND u.is_current=1 WHERE pt.target_rank=?""",
            (int(rank),),
        ).fetchall()
        if not target:
            raise ValueError("unknown target_rank")
        mapped = {item["administrative_unit_id"]: item for item in target if item["administrative_unit_id"]}
        if not mapped:
            fallback = db.execute(
                """SELECT pt.target_rank,pt.mapping_status,pt.administrative_unit_id,
                          u.administrative_code,u.administrative_name,u.province_name,
                          u.administrative_level,u.administrative_type,u.is_current
                   FROM priority_targets pt LEFT JOIN administrative_units u
                     ON u.id=pt.administrative_unit_id WHERE pt.target_rank=?""",
                (int(rank),),
            ).fetchone()
            if fallback and fallback["administrative_unit_id"] and fallback["is_current"]:
                mapped[fallback["administrative_unit_id"]] = fallback
        if not mapped:
            raise ValueError("target_rank has no reviewed current administrative mapping")
        if len(mapped) > 1:
            raise ValueError("target_rank maps to multiple current units; specify an administrative_code")
        target = next(iter(mapped.values()))
        unit = {
            "unit_id": target["administrative_unit_id"],
            "administrative_code": target["administrative_code"],
            "name": target["administrative_name"],
            "province": target["province_name"],
            "administrative_level": target["administrative_level"],
            "administrative_type": target["administrative_type"],
            "is_current": bool(target["is_current"]),
        }
        code = row.get("administrative_code") or row.get("ward_code")
        if code and str(code) != str(unit["administrative_code"]):
            raise ValueError("listing administrative code conflicts with target_rank mapping")
        supplied_name = row.get("ward_name") or row.get("administrative_name")
        if supplied_name and normalize_admin_name(supplied_name) != normalize_admin_name(unit["name"]):
            raise ValueError("listing ward_name conflicts with target_rank mapping")
        supplied_province = row.get("province")
        if supplied_province and normalize_admin_name(supplied_province) != normalize_admin_name(unit["province"]):
            raise ValueError("listing province conflicts with target_rank mapping")
        return unit

    code = row.get("administrative_code") or row.get("ward_code")
    if code:
        matches = search_administrative_units(db, str(code), include_historical=False, limit=10)
        exact = [item for item in matches if str(item.get("administrative_code")) == str(code)]
    else:
        name = str(row.get("ward_name") or row.get("administrative_name") or "").strip()
        province = str(row.get("province") or "").strip()
        if not name or not province:
            raise ValueError("administrative_code or exact ward_name and province are required")
        matches = search_administrative_units(
            db, name, province=province, include_historical=False, limit=100
        )
        normalized_name = normalize_admin_name(name)
        normalized_province = normalize_admin_name(province)
        exact = [
            item for item in matches
            if normalize_admin_name(item["name"]) == normalized_name
            and normalize_admin_name(item["province"]) == normalized_province
        ]
    if not exact:
        raise ValueError("listing ward is not in the current administrative registry")
    unique = {item["unit_id"]: item for item in exact}
    if len(unique) != 1:
        raise ValueError("listing ward is ambiguous in the current administrative registry")
    unit = next(iter(unique.values()))
    if not unit.get("is_current"):
        raise ValueError("listing ward does not resolve to a current administrative unit")
    supplied_name = row.get("ward_name") or row.get("administrative_name")
    supplied_province = row.get("province")
    if supplied_name and normalize_admin_name(supplied_name) != normalize_admin_name(unit["name"]):
        raise ValueError("listing ward_name conflicts with administrative_code")
    if supplied_province and normalize_admin_name(supplied_province) != normalize_admin_name(unit["province"]):
        raise ValueError("listing province conflicts with administrative_code")
    return unit


def _address_matches_ward(address: str, ward_name: str) -> bool:
    address_tokens = normalize_admin_name(address).split()
    ward_tokens = normalize_admin_name(ward_name).split()
    candidates = [ward_tokens]
    if ward_tokens and ward_tokens[0] in {"phuong", "xa", "dac", "khu"}:
        candidates.append(ward_tokens[1:] if ward_tokens[0] != "dac" else ward_tokens[2:])
    for candidate in candidates:
        if not candidate:
            continue
        for start in range(len(address_tokens) - len(candidate) + 1):
            if address_tokens[start : start + len(candidate)] == candidate:
                return True
    return False


def _make_candidate(
    db: sqlite3.Connection,
    raw: Any,
    *,
    operator_verified: bool,
    verified_by: str | None,
    verification_reference: str | None,
    collected_at: datetime,
    source_page_verified: bool = False,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("listing record must be a JSON object")
    unit = _resolve_current_unit(db, raw)
    property_type = str(raw.get("property_type") or "").strip().upper()
    if property_type not in PROPERTY_TYPES:
        raise ValueError(f"property_type must be one of {sorted(PROPERTY_TYPES)}")
    price = _number(raw.get("price_vnd"), "price_vnd")
    area = _number(raw.get("area_m2"), "area_m2")
    area_basis = str(raw.get("area_basis") or "OTHER").strip().upper()
    if area_basis not in AREA_BASES:
        raise ValueError(f"area_basis must be one of {sorted(AREA_BASES)}")
    title = str(raw.get("title") or "").strip()
    address = str(raw.get("address") or "").strip()
    if not title:
        raise ValueError("title is required")
    if not address:
        raise ValueError("address is required")
    if not _address_matches_ward(address, unit["name"]):
        raise ValueError("address does not contain the resolved current ward name")
    source_url = str(raw.get("source_url") or raw.get("source_website") or "").strip()
    canonical_url = canonicalize_source_url(source_url)
    source_domain = urlsplit(canonical_url).hostname or ""
    if source_domain in {"example.com", "localhost"}:
        raise ValueError("placeholder source domains cannot identify listings")
    evidence_fields = [
        str(raw.get(field) or "").strip()
        for field in ("price_evidence", "area_evidence", "address_evidence")
    ]
    proof = raw.get("_collector_source_page_proof")
    proof_valid = bool(
        source_page_verified
        and isinstance(proof, dict)
        and proof.get("retrieved_direct") is True
        and proof.get("detail_url") == canonical_url
        and re.fullmatch(r"[a-f0-9]{64}", str(proof.get("content_sha256", "")))
        and proof.get("visible_price_match") is True
        and proof.get("visible_area_match") is True
        and proof.get("address_verified") is True
        and all(evidence_fields)
    )
    operator_proof = bool(operator_verified and verified_by and verification_reference and all(evidence_fields))
    verified = proof_valid or operator_proof
    evidence_status = "SOURCE_PAGE_CONFIRMED" if verified else "UNVERIFIED"
    if not verified and str(raw.get("evidence_status") or "").upper() == "SEARCH_SNIPPET_ONLY":
        evidence_status = "SEARCH_SNIPPET_ONLY"
    validation_status = "VALIDATED" if verified else "CANDIDATE"
    target_rank = raw.get("target_rank")
    if target_rank is not None:
        target_rank = int(target_rank)
    fingerprint_payload = "|".join(
        (
            str(unit["unit_id"]),
            property_type,
            normalize_admin_name(title),
            normalize_admin_name(address),
            f"{area:.4f}",
            area_basis,
        )
    )
    fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
    return {
        "administrative_unit_id": int(unit["unit_id"]),
        "ward_code": str(unit["administrative_code"]),
        "ward_name": str(unit["name"]),
        "province": str(unit["province"]),
        "target_rank": target_rank,
        "property_type": property_type,
        "price_vnd": price,
        "area_m2": area,
        "price_per_m2": price / area,
        "area_basis": area_basis,
        "title": title,
        "address": address,
        "source_url": source_url,
        "canonical_url": canonical_url,
        "source_domain": source_domain,
        "listed_date": raw.get("listed_date") or raw.get("published_at"),
        "published_at": raw.get("published_at") or raw.get("listed_date"),
        "evidence_status": evidence_status,
        "validation_status": validation_status,
        "included_in_stats": int(verified),
        "evidence_excerpt": " | ".join(value for value in evidence_fields if value),
        "raw_payload": json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str),
        "identity_fingerprint": fingerprint,
        "identity_key": f"source:{canonical_url}",
        "listing_id": hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:32],
        "collected_at": collected_at.isoformat(timespec="seconds"),
        "observed_day": collected_at.date().isoformat(),
        "verification_reference": verification_reference or "",
        "verified_by": verified_by or "",
    }


def prepare_listing_import(
    db: sqlite3.Connection,
    payload: Any,
    *,
    operator_verified: bool = False,
    verified_by: str | None = None,
    verification_reference: str | None = None,
    collected_at: datetime | None = None,
    source_page_verified: bool = False,
) -> dict[str, Any]:
    """Validate data without writing; AI-authored verification claims are ignored."""
    rows = payload.get("listings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TypeError("input must be a JSON array or an object containing listings[]")
    if any(
        isinstance(row, dict) and row.get("source_website") == "DEMO_SYNTHETIC"
        for row in rows
    ):
        raise ValueError(
            "DEMO_SYNTHETIC records must use the isolated wardprice.demo importer; "
            "the canonical listing warehouse never accepts synthetic fixtures."
        )
    collected_at = collected_at or datetime.now(timezone.utc)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    duplicates_exact = 0
    for index, raw in enumerate(rows, start=1):
        try:
            candidate = _make_candidate(
                db,
                raw,
                operator_verified=operator_verified,
                verified_by=verified_by,
                verification_reference=verification_reference,
                collected_at=collected_at,
                source_page_verified=source_page_verified,
            )
            if candidate["canonical_url"] in seen_urls or candidate["identity_fingerprint"] in seen_fingerprints:
                duplicates_exact += 1
                rejected.append({"row_index": index, "reason": "DUPLICATE_IN_INPUT", "raw": raw})
                continue
            seen_urls.add(candidate["canonical_url"])
            seen_fingerprints.add(candidate["identity_fingerprint"])
            accepted.append(candidate)
        except (TypeError, ValueError, OverflowError) as exc:
            rejected.append({"row_index": index, "reason": str(exc), "raw": raw})
    return {
        "received": len(rows),
        "candidate_count": len(accepted),
        "rejected_count": len(rejected),
        "duplicates_exact": duplicates_exact,
        "candidates": accepted,
        "rejected": rejected,
        "verified_candidate_count": sum(row["included_in_stats"] for row in accepted),
        "unverified_candidate_count": sum(not row["included_in_stats"] for row in accepted),
    }


def _existing_listing(db: sqlite3.Connection, candidate: dict[str, Any]) -> sqlite3.Row | None:
    return db.execute(
        """SELECT l.* FROM listing_sources s JOIN listings l ON l.listing_id=s.listing_id
           WHERE s.canonical_url=? LIMIT 1""",
        (candidate["canonical_url"],),
    ).fetchone()


def _fingerprint_listing(db: sqlite3.Connection, candidate: dict[str, Any]) -> sqlite3.Row | None:
    return db.execute(
        """SELECT * FROM listings WHERE administrative_unit_id=?
           AND identity_fingerprint=? AND active=1 LIMIT 1""",
        (candidate["administrative_unit_id"], candidate["identity_fingerprint"]),
    ).fetchone()


def _upsert_listing(
    db: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    run_id: str,
) -> str:
    existing = _existing_listing(db, candidate)
    if existing and int(existing["administrative_unit_id"] or -1) != candidate["administrative_unit_id"]:
        raise ValueError("source URL already belongs to another administrative unit")
    if not existing:
        existing = _fingerprint_listing(db, candidate)
    inserted = existing is None
    listing_id = candidate["listing_id"] if inserted else existing["listing_id"]
    identity_key = candidate["identity_key"] if inserted else existing["identity_key"]
    if inserted:
        db.execute(
            """INSERT INTO listings(
               listing_id,identity_key,identity_fingerprint,ward_code,ward_name,province,
               property_type,price_vnd,area_m2,price_per_m2,address,source_url,source_domain,
               listed_date,collected_at,last_seen_at,evidence_status,evidence_excerpt,
               raw_payload,active,included_in_stats,administrative_unit_id,target_rank,
               area_basis,validation_status,dedup_key,title,source_website,published_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                listing_id,
                identity_key,
                candidate["identity_fingerprint"],
                candidate["ward_code"],
                candidate["ward_name"],
                candidate["province"],
                candidate["property_type"],
                candidate["price_vnd"],
                candidate["area_m2"],
                candidate["price_per_m2"],
                candidate["address"],
                candidate["source_url"],
                candidate["source_domain"],
                candidate["listed_date"],
                candidate["collected_at"],
                candidate["collected_at"],
                candidate["evidence_status"],
                candidate["evidence_excerpt"],
                candidate["raw_payload"],
                1,
                candidate["included_in_stats"],
                candidate["administrative_unit_id"],
                candidate["target_rank"],
                candidate["area_basis"],
                candidate["validation_status"],
                candidate["identity_fingerprint"],
                candidate["title"],
                candidate["source_domain"],
                candidate["published_at"],
            ),
        )
    else:
        db.execute(
            """UPDATE listings SET identity_fingerprint=?,ward_code=?,ward_name=?,province=?,
               property_type=?,price_vnd=?,area_m2=?,price_per_m2=?,address=?,
               source_domain=?,listed_date=COALESCE(?,listed_date),last_seen_at=?,
               evidence_status=?,evidence_excerpt=?,raw_payload=?,active=1,
               included_in_stats=?,administrative_unit_id=?,target_rank=COALESCE(?,target_rank),
               area_basis=?,validation_status=?,dedup_key=?,title=?,source_website=?,
               published_at=COALESCE(?,published_at) WHERE listing_id=?""",
            (
                candidate["identity_fingerprint"],
                candidate["ward_code"],
                candidate["ward_name"],
                candidate["province"],
                candidate["property_type"],
                candidate["price_vnd"],
                candidate["area_m2"],
                candidate["price_per_m2"],
                candidate["address"],
                candidate["source_domain"],
                candidate["listed_date"],
                candidate["collected_at"],
                candidate["evidence_status"],
                candidate["evidence_excerpt"],
                candidate["raw_payload"],
                candidate["included_in_stats"],
                candidate["administrative_unit_id"],
                candidate["target_rank"],
                candidate["area_basis"],
                candidate["validation_status"],
                candidate["identity_fingerprint"],
                candidate["title"],
                candidate["source_domain"],
                candidate["published_at"],
                listing_id,
            ),
        )
    db.execute(
        """INSERT INTO listing_sources(
           canonical_url,listing_id,source_url,source_domain,first_seen_at,last_seen_at
           ) VALUES(?,?,?,?,?,?) ON CONFLICT(canonical_url) DO UPDATE SET
           last_seen_at=excluded.last_seen_at""",
        (
            candidate["canonical_url"],
            listing_id,
            candidate["source_url"],
            candidate["source_domain"],
            candidate["collected_at"],
            candidate["collected_at"],
        ),
    )
    observation = db.execute(
        """SELECT id FROM listing_observations WHERE listing_id=? AND observation_date=?""",
        (listing_id, candidate["observed_day"]),
    ).fetchone()
    if observation:
        db.execute(
            """UPDATE listing_observations SET administrative_unit_id=?,observed_at=?,
               observed_price_vnd=?,observed_area_m2=?,price_per_m2=?,area_basis=?,
               evidence_status=?,validation_status=?,source_run_id=?,source_url=?,raw_payload=?
               WHERE id=?""",
            (
                candidate["administrative_unit_id"],
                candidate["collected_at"],
                candidate["price_vnd"],
                candidate["area_m2"],
                candidate["price_per_m2"],
                candidate["area_basis"],
                candidate["evidence_status"],
                candidate["validation_status"],
                run_id,
                candidate["source_url"],
                candidate["raw_payload"],
                observation["id"],
            ),
        )
    else:
        db.execute(
            """INSERT INTO listing_observations(
               listing_id,administrative_unit_id,observation_date,observed_at,
               observed_price_vnd,observed_area_m2,price_per_m2,area_basis,
               evidence_status,validation_status,source_run_id,source_url,raw_payload
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                listing_id,
                candidate["administrative_unit_id"],
                candidate["observed_day"],
                candidate["collected_at"],
                candidate["price_vnd"],
                candidate["area_m2"],
                candidate["price_per_m2"],
                candidate["area_basis"],
                candidate["evidence_status"],
                candidate["validation_status"],
                run_id,
                candidate["source_url"],
                candidate["raw_payload"],
            ),
        )
    return "INSERTED" if inserted else "UPDATED"


def import_listing_payload(
    db: sqlite3.Connection,
    payload: Any,
    *,
    apply: bool = False,
    run_id: str = "manual-import",
    operator_verified: bool = False,
    verified_by: str | None = None,
    verification_reference: str | None = None,
    collected_at: datetime | None = None,
    daily_limit: int = MAX_DAILY_OBSERVATIONS,
    source_page_verified: bool = False,
) -> dict[str, Any]:
    """Preview or transactionally import listings and one observation per listing/day."""
    if daily_limit < 0 or daily_limit > MAX_DAILY_OBSERVATIONS:
        raise ValueError(f"daily_limit must be between 0 and {MAX_DAILY_OBSERVATIONS}")
    prepared = prepare_listing_import(
        db,
        payload,
        operator_verified=operator_verified,
        verified_by=verified_by,
        verification_reference=verification_reference,
        collected_at=collected_at,
        source_page_verified=source_page_verified,
    )
    day = (collected_at or datetime.now(timezone.utc)).date().isoformat()
    already_observed_today = int(
        db.execute(
            "SELECT COUNT(*) FROM listing_observations WHERE observation_date=?", (day,)
        ).fetchone()[0]
    )
    remaining = max(0, daily_limit - already_observed_today)
    result = {
        "status": "APPLIED" if apply else "PREVIEW_ONLY",
        "received": prepared["received"],
        "candidate_count": prepared["candidate_count"],
        "inserted": 0,
        "updated": 0,
        "duplicates_existing": 0,
        "duplicates_exact": prepared["duplicates_exact"],
        "rejected": prepared["rejected_count"],
        "quarantined": 0,
        "limited": 0,
        "daily_limit": daily_limit,
        "daily_observations_already_stored": already_observed_today,
        "daily_capacity_remaining": remaining,
        "verified_candidates": prepared["verified_candidate_count"],
        "unverified_candidates": prepared["unverified_candidate_count"],
        "rejected_rows": prepared["rejected"],
        "network_called": False,
    }
    if not apply:
        return result

    affected: set[tuple[int, str, str]] = set()
    observations_added = 0
    with db:
        for rejected in prepared["rejected"]:
            if rejected["reason"] == "DUPLICATE_IN_INPUT":
                continue
            db.execute(
                """INSERT INTO listing_quarantine(run_id,imported_at,row_index,reason,raw_payload)
                   VALUES(?,?,?,?,?)""",
                (
                    run_id,
                    (collected_at or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                    rejected["row_index"],
                    rejected["reason"],
                    json.dumps(rejected["raw"], ensure_ascii=False, default=str),
                ),
            )
            result["quarantined"] += 1
        for item_index, candidate in enumerate(prepared["candidates"], start=1):
            existing_url = _existing_listing(db, candidate)
            existing_fingerprint = _fingerprint_listing(db, candidate)
            if existing_url and int(existing_url["administrative_unit_id"] or -1) != candidate["administrative_unit_id"]:
                rejected = {"row_index": item_index, "reason": "source URL already belongs to another administrative unit", "raw": candidate["raw_payload"]}
                result["rejected_rows"].append(rejected)
                result["rejected"] += 1
                result["quarantined"] += 1
                db.execute(
                    """INSERT INTO listing_quarantine(run_id,imported_at,row_index,reason,raw_payload)
                       VALUES(?,?,?,?,?)""",
                    (run_id, candidate["collected_at"], item_index, rejected["reason"], candidate["raw_payload"]),
                )
                continue
            existing = existing_url or existing_fingerprint
            has_today = existing and db.execute(
                """SELECT 1 FROM listing_observations WHERE listing_id=? AND observation_date=?""",
                (existing["listing_id"], candidate["observed_day"]),
            ).fetchone()
            if not has_today and observations_added >= remaining:
                result["limited"] += 1
                continue
            outcome = _upsert_listing(db, candidate, run_id=run_id)
            result["inserted" if outcome == "INSERTED" else "updated"] += 1
            if not has_today:
                observations_added += 1
            if existing:
                result["duplicates_existing"] += 1
            affected.add(
                (
                    candidate["administrative_unit_id"],
                    candidate["property_type"],
                    candidate["area_basis"],
                )
            )
    stats_result = recompute_statistics(
        db,
        keys=affected,
        snapshot_date=day,
        calculation_window_days=90,
    )
    result["statistics_updated"] = stats_result["statistics_written"]
    result["observations_added"] = observations_added
    return result


def recompute_statistics(
    db: sqlite3.Connection,
    *,
    keys: set[tuple[int, str, str]] | None = None,
    snapshot_date: str | None = None,
    calculation_window_days: int = 90,
) -> dict[str, Any]:
    """Aggregate only source-page-confirmed, independently operator-reviewed listings."""
    if calculation_window_days <= 0:
        raise ValueError("calculation_window_days must be positive")
    snapshot = snapshot_date or datetime.now(timezone.utc).astimezone().date().isoformat()
    date.fromisoformat(snapshot)
    start = date.fromisoformat(snapshot).fromordinal(
        date.fromisoformat(snapshot).toordinal() - calculation_window_days + 1
    ).isoformat()
    params: list[Any] = [start, snapshot]
    filters = "lo.observation_date BETWEEN ? AND ?"
    if keys:
        clauses = []
        for unit_id, property_type, area_basis in sorted(keys):
            clauses.append("(lo.administrative_unit_id=? AND l.property_type=? AND lo.area_basis=?)")
            params.extend((unit_id, property_type, area_basis))
        filters += " AND (" + " OR ".join(clauses) + ")"
    rows = db.execute(
        """SELECT lo.listing_id,lo.administrative_unit_id,lo.observation_date,
                  lo.observed_at,lo.price_per_m2,lo.area_basis,l.property_type,l.target_rank
           FROM listing_observations lo JOIN listings l ON l.listing_id=lo.listing_id
           WHERE """ + filters + """
             AND l.active=1 AND l.evidence_status='SOURCE_PAGE_CONFIRMED'
             AND l.validation_status='VALIDATED' AND lo.evidence_status='SOURCE_PAGE_CONFIRMED'
             AND lo.validation_status='VALIDATED'
           ORDER BY lo.listing_id,lo.observation_date DESC,lo.id DESC""",
        params,
    ).fetchall()
    latest_by_listing: dict[str, sqlite3.Row] = {}
    for row in rows:
        latest_by_listing.setdefault(row["listing_id"], row)
    grouped: dict[tuple[int, str, str], list[sqlite3.Row]] = {}
    for row in latest_by_listing.values():
        key = (row["administrative_unit_id"], row["property_type"], row["area_basis"])
        grouped.setdefault(key, []).append(row)
    written = 0
    with db:
        for key, samples in grouped.items():
            unit_id, property_type, area_basis = key
            prices = [float(row["price_per_m2"]) for row in samples]
            latest_at = max(row["observed_at"] for row in samples)
            target = db.execute(
                """SELECT target_rank FROM priority_target_mappings
                   WHERE administrative_unit_id=? AND mapping_status='REVIEWED_RESOLUTION'
                   ORDER BY target_rank LIMIT 1""",
                (unit_id,),
            ).fetchone()
            if not target:
                target = db.execute(
                    "SELECT target_rank FROM priority_targets WHERE administrative_unit_id=? ORDER BY target_rank LIMIT 1",
                    (unit_id,),
                ).fetchone()
            db.execute(
                """INSERT INTO ward_price_statistics(
                   administrative_unit_id,target_rank,property_type,area_basis,snapshot_date,
                   sample_count,mean_price_per_m2,median_price_per_m2,min_price_per_m2,
                   max_price_per_m2,calculation_window_days,latest_observation_at,
                   source_quality,calculation_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(administrative_unit_id,property_type,area_basis,snapshot_date)
                   DO UPDATE SET target_rank=excluded.target_rank,sample_count=excluded.sample_count,
                   mean_price_per_m2=excluded.mean_price_per_m2,
                   median_price_per_m2=excluded.median_price_per_m2,
                   min_price_per_m2=excluded.min_price_per_m2,
                   max_price_per_m2=excluded.max_price_per_m2,
                   calculation_window_days=excluded.calculation_window_days,
                   latest_observation_at=excluded.latest_observation_at,
                   source_quality=excluded.source_quality,
                   calculation_version=excluded.calculation_version""",
                (
                    unit_id,
                    target["target_rank"] if target else None,
                    property_type,
                    area_basis,
                    snapshot,
                    len(prices),
                    mean(prices),
                    median(prices),
                    min(prices),
                    max(prices),
                    calculation_window_days,
                    latest_at,
                    "SOURCE_PAGE_CONFIRMED_VALIDATED",
                    CALCULATION_VERSION,
                ),
            )
            written += 1
    return {"statistics_written": written, "verified_listings_used": len(latest_by_listing)}


def national_listing_rows(
    db: sqlite3.Connection, *, include_unverified: bool = True, limit: int = 10000
) -> list[dict[str, Any]]:
    """Return national listing rows with evidence labels; never expose raw payloads."""
    limit = max(1, min(int(limit), 50000))
    filters = ["l.administrative_unit_id IS NOT NULL", "l.active=1"]
    if not include_unverified:
        filters.extend(
            ["l.evidence_status='SOURCE_PAGE_CONFIRMED'", "l.validation_status='VALIDATED'"]
        )
    rows = db.execute(
        """SELECT l.listing_id,l.administrative_unit_id,l.target_rank,
                  u.administrative_code,u.administrative_name AS ward_name,u.province_name AS province,
                  l.title,l.property_type,l.price_vnd,l.area_m2,l.area_basis,l.price_per_m2,
                  l.address,l.source_website,l.source_url,l.source_domain,l.published_at,
                  l.collected_at,l.last_seen_at,l.evidence_status,l.validation_status,
                  l.included_in_stats
           FROM listings l JOIN administrative_units u ON u.id=l.administrative_unit_id
           WHERE """ + " AND ".join(filters)
        + " ORDER BY u.province_name,u.administrative_name,l.property_type,l.last_seen_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def national_statistics_rows(db: sqlite3.Connection, *, limit: int = 10000) -> list[dict[str, Any]]:
    """Return latest statistics separately by property type and area measurement basis."""
    limit = max(1, min(int(limit), 50000))
    rows = db.execute(
        """SELECT s.administrative_unit_id,u.administrative_code,
                  u.administrative_name AS ward_name,u.province_name AS province,
                  s.target_rank,s.property_type,s.area_basis,s.snapshot_date,s.sample_count,
                  s.mean_price_per_m2,s.median_price_per_m2,s.min_price_per_m2,
                  s.max_price_per_m2,s.calculation_window_days,s.latest_observation_at,
                  s.source_quality,s.calculation_version
           FROM ward_price_statistics s JOIN administrative_units u
             ON u.id=s.administrative_unit_id
           WHERE s.snapshot_date=(SELECT MAX(s2.snapshot_date) FROM ward_price_statistics s2
             WHERE s2.administrative_unit_id=s.administrative_unit_id
               AND s2.property_type=s.property_type AND s2.area_basis=s.area_basis)
           ORDER BY u.province_name,u.administrative_name,s.property_type,s.area_basis LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]

