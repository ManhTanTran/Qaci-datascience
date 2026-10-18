"""Versioned national administrative registry and local-first lookup services.

The importer accepts official NSO SOAP XML snapshots or normalized CSV files.
It never manufactures administrative codes, and historical records remain
separate snapshots until an explicit source-backed crosswalk is imported.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

OFFICIAL_NSO_REFERENCE = "https://danhmuchanhchinh.nso.gov.vn/WebService.aspx"
PROPERTY_TYPES = {"DAT_O", "NHA_RIENG", "CHUNG_CU"}
AREA_BASES = {"LAND_AREA", "FLOOR_AREA", "USABLE_AREA", "OTHER"}
CURRENT_DATA_STATUS = "NATIONWIDE_REGISTRY_LOADED"
AWAITING_DATA_STATUS = "NATIONWIDE_READY_AWAITING_DATA"


def normalize_admin_name(value: Any) -> str:
    """Normalize Vietnamese names for exact, accent-insensitive matching."""
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _unit_record(
    *,
    code: str | None,
    name: str,
    level: str,
    unit_type: str,
    province_code: str | None,
    province_name: str,
    district_code: str | None,
    district_name: str | None,
    version: str,
    source_reference: str,
    parent_code: str | None = None,
    parent_level: str | None = None,
) -> dict[str, Any]:
    return {
        "administrative_code": code or None,
        "administrative_name": _clean(name),
        "normalized_name": normalize_admin_name(name),
        "administrative_level": level,
        "administrative_type": _clean(unit_type) or level,
        "parent_unit_code": parent_code or None,
        "parent_unit_level": parent_level or None,
        "province_code": province_code or None,
        "province_name": _clean(province_name),
        "district_code_legacy": district_code or None,
        "district_name_legacy": _clean(district_name) or None,
        "administrative_version": version,
        "valid_from": None,
        "valid_to": None,
        "is_current": 0,
        "mapping_status": "UNRESOLVED",
        "source_reference": source_reference,
    }


def parse_nso_soap_xml(
    path: Path,
    *,
    as_of_date: str,
    source_reference: str = OFFICIAL_NSO_REFERENCE,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Parse one official NSO ``DanhMucPhuongXa`` SOAP response offline.

    The date is supplied by the operator from the request metadata; it is not
    inferred from names or codes. The response includes actual official codes.
    """
    as_of = date.fromisoformat(as_of_date).isoformat()
    version = f"nso-as-of-{as_of}"
    root = ElementTree.parse(path).getroot()
    source_rows: list[dict[str, str]] = []
    required = {"MaTinh", "TenTinh", "MaQuanHuyen", "TenQuanHuyen", "MaPhuongXa", "TenPhuongXa"}
    for element in root.iter():
        fields = {
            _local_name(child.tag): _clean(child.text)
            for child in list(element)
            if len(child) == 0
        }
        if required.issubset(fields) and fields["MaPhuongXa"] and fields["TenPhuongXa"]:
            source_rows.append(fields)
    if not source_rows:
        raise ValueError("No NSO commune rows found in XML; expected a SOAP DataSet response")

    province_records: dict[tuple[str, str], dict[str, Any]] = {}
    district_records: dict[tuple[str, str, str], dict[str, Any]] = {}
    communes: list[dict[str, Any]] = []
    seen_codes: set[tuple[str, str]] = set()
    for row_number, row in enumerate(source_rows, start=1):
        province_code = row["MaTinh"].strip()
        province_name = row["TenTinh"]
        district_code = row["MaQuanHuyen"].strip()
        district_name = row["TenQuanHuyen"]
        commune_code = row["MaPhuongXa"].strip() or None
        commune_name = row["TenPhuongXa"]
        commune_type = row.get("LoaiHinh", "")
        if not province_name or not commune_name:
            raise ValueError(f"NSO row {row_number} is missing a name")
        if not re.fullmatch(r"\d{2,5}", province_code):
            raise ValueError(f"NSO row {row_number} has an invalid province code")
        if commune_code and not re.fullmatch(r"\d{4,5}", commune_code):
            raise ValueError(f"NSO row {row_number} has an invalid commune code")

        province_key = (province_code, normalize_admin_name(province_name))
        previous_province = province_records.get(province_key)
        if not previous_province:
            province_records[province_key] = _unit_record(
                code=province_code,
                name=province_name,
                level="PROVINCE",
                unit_type="PROVINCE",
                province_code=province_code,
                province_name=province_name,
                district_code=None,
                district_name=None,
                version=version,
                source_reference=source_reference,
            )

        has_district = district_code != province_code or normalize_admin_name(district_name) != normalize_admin_name(province_name)
        parent_code = province_code
        parent_level = "PROVINCE"
        if has_district:
            district_key = (province_code, district_code, normalize_admin_name(district_name))
            previous_district = district_records.get(district_key)
            if not previous_district:
                district_records[district_key] = _unit_record(
                    code=district_code,
                    name=district_name,
                    level="DISTRICT_HISTORIC",
                    unit_type="DISTRICT_HISTORIC",
                    province_code=province_code,
                    province_name=province_name,
                    district_code=district_code,
                    district_name=district_name,
                    version=version,
                    source_reference=source_reference,
                    parent_code=province_code,
                    parent_level="PROVINCE",
                )
            parent_code = district_code
            parent_level = "DISTRICT_HISTORIC"

        if commune_type and normalize_admin_name(commune_type) not in {
            "xa", "phuong", "thi tran", "dac khu"
        }:
            raise ValueError(f"Unknown administrative type in NSO row {row_number}: {commune_type}")
        identity = ("COMMUNE", commune_code or "")
        if commune_code and identity in seen_codes:
            raise ValueError(f"Duplicate commune code in NSO snapshot: {commune_code}")
        if commune_code:
            seen_codes.add(identity)
        communes.append(
            _unit_record(
                code=commune_code,
                name=commune_name,
                level="COMMUNE",
                unit_type=commune_type or "UNKNOWN",
                province_code=province_code,
                province_name=province_name,
                district_code=district_code if has_district else None,
                district_name=district_name if has_district else None,
                version=version,
                source_reference=source_reference,
                parent_code=parent_code,
                parent_level=parent_level,
            )
        )

    records = list(province_records.values()) + list(district_records.values()) + communes
    stats = {
        "source_commune_rows": len(source_rows),
        "commune_count": len(communes),
        "province_count": len(province_records),
        "district_count": len(district_records),
        "record_count": len(records),
    }
    return records, stats


def load_admin_csv(path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Load a normalized administrative CSV without generating absent codes."""
    required = {
        "administrative_name",
        "administrative_level",
        "administrative_version",
        "province_name",
        "source_reference",
    }
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Administrative CSV must include {sorted(required)}")
        for row_number, row in enumerate(reader, start=2):
            level = _clean(row.get("administrative_level")).upper()
            if level not in {"PROVINCE", "DISTRICT_HISTORIC", "COMMUNE"}:
                raise ValueError(f"CSV row {row_number}: unsupported administrative_level")
            name = _clean(row.get("administrative_name"))
            province = _clean(row.get("province_name"))
            if not name or not province:
                raise ValueError(f"CSV row {row_number}: administrative_name and province_name are required")
            code = _clean(row.get("administrative_code")) or None
            version = _clean(row.get("administrative_version"))
            if not version:
                raise ValueError(f"CSV row {row_number}: administrative_version is required")
            records.append(
                {
                    "administrative_code": code,
                    "administrative_name": name,
                    "normalized_name": normalize_admin_name(row.get("normalized_name") or name),
                    "normalized_province": normalize_admin_name(row.get("normalized_province") or province),
                    "administrative_level": level,
                    "administrative_type": _clean(row.get("administrative_type")) or level,
                    "parent_unit_code": _clean(row.get("parent_unit_code")) or None,
                    "parent_unit_level": _clean(row.get("parent_unit_level")).upper() or None,
                    "province_code": _clean(row.get("province_code")) or None,
                    "province_name": province,
                    "district_code_legacy": _clean(row.get("district_code_legacy")) or None,
                    "district_name_legacy": _clean(row.get("district_name_legacy")) or None,
                    "administrative_version": version,
                    "valid_from": _clean(row.get("valid_from")) or None,
                    "valid_to": _clean(row.get("valid_to")) or None,
                    "is_current": int(_clean(row.get("is_current")) in {"1", "true", "True"}),
                    "mapping_status": _clean(row.get("mapping_status")) or "UNRESOLVED",
                    "source_reference": _clean(row.get("source_reference")),
                }
            )
    if not records:
        raise ValueError("Administrative CSV is empty")
    counts = Counter(row["administrative_level"] for row in records)
    return records, {
        "record_count": len(records),
        "province_count": counts["PROVINCE"],
        "district_count": counts["DISTRICT_HISTORIC"],
        "commune_count": counts["COMMUNE"],
    }


def write_admin_csv(records: list[dict[str, Any]], path: Path) -> Path:
    """Write a normalized, inspectable snapshot file from parsed source data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "administrative_code",
        "administrative_name",
        "administrative_level",
        "administrative_type",
        "parent_unit_code",
        "parent_unit_level",
        "province_code",
        "province_name",
        "district_code_legacy",
        "district_name_legacy",
        "administrative_version",
        "valid_from",
        "valid_to",
        "is_current",
        "mapping_status",
        "source_reference",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    return path


def _validate_records(records: list[dict[str, Any]], dataset_version: str) -> None:
    if not records:
        raise ValueError("Administrative snapshot is empty")
    seen_codes: set[tuple[str, str]] = set()
    for index, row in enumerate(records, start=1):
        if row.get("administrative_version") != dataset_version:
            raise ValueError(f"Row {index} version does not match {dataset_version}")
        if row.get("administrative_level") not in {"PROVINCE", "DISTRICT_HISTORIC", "COMMUNE"}:
            raise ValueError(f"Row {index} has unsupported administrative level")
        if not row.get("administrative_name") or not row.get("province_name"):
            raise ValueError(f"Row {index} lacks a name or province")
        if not row.get("source_reference"):
            raise ValueError(f"Row {index} lacks source provenance")
        code = row.get("administrative_code")
        if code is not None:
            code = str(code).strip()
            if not code:
                row["administrative_code"] = None
                continue
            row["administrative_code"] = code
            row["normalized_name"] = normalize_admin_name(row["administrative_name"])
            row["normalized_province"] = normalize_admin_name(row["province_name"])
            key = (
                row["administrative_level"],
                row.get("province_code") or "",
                code,
                row["normalized_name"],
            )
            if key in seen_codes:
                raise ValueError(f"Duplicate code {code} at {row['administrative_level']} level")
            seen_codes.add(key)
        row["normalized_name"] = normalize_admin_name(row["administrative_name"])
        row["normalized_province"] = normalize_admin_name(row["province_name"])


def _record_hash(records: list[dict[str, Any]]) -> str:
    canonical = [
        {
            key: row.get(key)
            for key in (
                "administrative_code",
                "administrative_name",
                "administrative_level",
                "administrative_type",
                "parent_unit_code",
                "province_code",
                "province_name",
                "district_code_legacy",
                "district_name_legacy",
                "administrative_version",
                "valid_from",
                "valid_to",
                "source_reference",
            )
        }
        for row in sorted(
            records,
            key=lambda item: (
                item.get("administrative_level", ""),
                item.get("administrative_code") or "",
                item.get("administrative_name", ""),
            ),
        )
    ]
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _upsert_alias(
    db: sqlite3.Connection,
    *,
    unit_id: int | None,
    alias_name: str,
    alias_type: str,
    source_reference: str,
    mapping_status: str,
    target_rank: int | None,
    source_version: str,
    now: str,
    province_name: str | None = None,
    district_name_legacy: str | None = None,
) -> None:
    normalized = normalize_admin_name(alias_name)
    existing = db.execute(
        """SELECT id FROM administrative_aliases
           WHERE COALESCE(administrative_unit_id,-1)=COALESCE(?,-1)
             AND normalized_alias=? AND alias_type=?
             AND COALESCE(target_rank,-1)=COALESCE(?,-1)
             AND source_reference=?""",
        (unit_id, normalized, alias_type, target_rank, source_reference),
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE administrative_aliases SET alias_name=?,mapping_status=?,
               source_version=?,province_name=?,district_name_legacy=?,created_at=? WHERE id=?""",
            (
                alias_name,
                mapping_status,
                source_version,
                province_name,
                district_name_legacy,
                now,
                existing["id"],
            ),
        )
    else:
        db.execute(
            """INSERT INTO administrative_aliases(
               administrative_unit_id,alias_name,normalized_alias,alias_type,
               source_reference,mapping_status,province_name,district_name_legacy,
               target_rank,source_version,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                unit_id,
                alias_name,
                normalized,
                alias_type,
                source_reference,
                mapping_status,
                province_name,
                district_name_legacy,
                target_rank,
                source_version,
                now,
            ),
        )


def _refresh_priority_targets(
    db: sqlite3.Connection, *, current_version: str, now: str
) -> dict[str, int]:
    """Copy safe public target labels, leaving the legacy table untouched."""
    legacy = db.execute(
        """SELECT rank,old_ward,old_district,old_province,current_ward,
                  current_province,current_ward_code,status
           FROM ward_target_legacy ORDER BY rank"""
    ).fetchall()
    if not legacy:
        return {"target_count": 0, "mapped_count": 0, "pending_count": 0}

    mapped = pending = 0
    for row in legacy:
        unit = None
        current_name = _clean(row["current_ward"])
        current_province = _clean(row["current_province"])
        if row["current_ward_code"]:
            unit = db.execute(
                """SELECT id FROM administrative_units
                   WHERE is_current=1 AND administrative_level='COMMUNE'
                     AND administrative_code=? LIMIT 2""",
                (str(row["current_ward_code"]),),
            ).fetchall()
            unit = unit[0] if len(unit) == 1 else None
        elif row["status"] == "REVIEWED_RESOLUTION" and current_name and current_province:
            matches = db.execute(
                """SELECT id FROM administrative_units
                   WHERE is_current=1 AND administrative_level='COMMUNE'
                     AND normalized_name=? AND normalized_province=? LIMIT 2""",
                (normalize_admin_name(current_name), normalize_admin_name(current_province)),
            ).fetchall()
            unit = matches[0] if len(matches) == 1 else None

        if unit:
            mapping_status = "REVIEWED_RESOLUTION"
            mapped += 1
        elif row["status"] == "PENDING_ADMIN_MAPPING":
            mapping_status = "PENDING_ADMIN_MAPPING"
            pending += 1
        else:
            mapping_status = "REVIEWED_RESOLUTION_NEEDS_UNIT_MATCH"
            pending += 1

        db.execute(
            """INSERT INTO priority_targets(
               target_rank,original_ward,original_district,original_province,
               current_ward,current_province,administrative_unit_id,mapping_status,
               source_reference,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(target_rank) DO UPDATE SET
               original_ward=excluded.original_ward,
               original_district=excluded.original_district,
               original_province=excluded.original_province,
               current_ward=excluded.current_ward,
               current_province=excluded.current_province,
               administrative_unit_id=excluded.administrative_unit_id,
               mapping_status=excluded.mapping_status,
               source_reference=excluded.source_reference,
               updated_at=excluded.updated_at""",
            (
                row["rank"],
                row["old_ward"],
                row["old_district"],
                row["old_province"],
                current_name,
                current_province,
                unit["id"] if unit else None,
                mapping_status,
                f"ward_target_legacy:rank:{row['rank']}",
                now,
            ),
        )
        _upsert_alias(
            db,
            unit_id=unit["id"] if unit else None,
            alias_name=row["old_ward"],
            alias_type="LEGACY_TARGET_NAME",
            source_reference=f"ward_target_legacy:rank:{row['rank']}",
            mapping_status=mapping_status,
            target_rank=int(row["rank"]),
            source_version="legacy-top50-review",
            province_name=row["old_province"],
            district_name_legacy=row["old_district"],
            now=now,
        )
        if unit:
            db.execute(
                """INSERT INTO priority_target_mappings(
                   target_rank,administrative_unit_id,relationship_type,mapping_status,
                   source_reference,effective_date,created_at
                   ) VALUES(?,?,'UNRESOLVED','REVIEWED_RESOLUTION',?,NULL,?)
                   ON CONFLICT(target_rank,administrative_unit_id,source_reference)
                   DO UPDATE SET mapping_status=excluded.mapping_status,
                   created_at=excluded.created_at""",
                (
                    row["rank"],
                    unit["id"],
                    f"ward_target_legacy:rank:{row['rank']}",
                    now,
                ),
            )
    return {"target_count": len(legacy), "mapped_count": mapped, "pending_count": pending}


def import_administrative_records(
    db: sqlite3.Connection,
    records: list[dict[str, Any]],
    *,
    dataset_version: str,
    as_of_date: str,
    source_reference: str,
    source_name: str = "NSO administrative directory",
    source_type: str = "OFFICIAL_GOVERNMENT_DATA",
    source_quality: str = "OFFICIAL_SOURCE",
    file_sha256: str | None = None,
    is_current: bool = False,
    dataset_status: str = "IMPORTED",
    retrieved_at: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Idempotently import one versioned snapshot without deleting old versions."""
    date.fromisoformat(as_of_date)
    records = [dict(row) for row in records]
    _validate_records(records, dataset_version)
    if is_current:
        current_codes: set[tuple[str, str]] = set()
        for row in records:
            code = row.get("administrative_code")
            if code:
                key = (row["administrative_level"], str(code))
                if key in current_codes:
                    raise ValueError(
                        f"Current snapshot has duplicate {row['administrative_level']} code {code}"
                    )
                current_codes.add(key)
    computed_hash = _record_hash(records)
    source_hash = file_sha256 or computed_hash
    source_id = "nso-" + hashlib.sha256(
        f"{source_reference}|{dataset_version}|{source_hash}".encode()
    ).hexdigest()[:20]
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = Counter(row["administrative_level"] for row in records)

    if is_current:
        newest = db.execute(
            "SELECT MAX(as_of_date) FROM administrative_dataset_versions WHERE is_current=1"
        ).fetchone()[0]
        if newest and as_of_date < newest:
            raise ValueError(
                f"Snapshot {as_of_date} is older than the current registry ({newest}); "
                "import it as historical instead"
            )

    db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(
            """INSERT INTO data_sources(
               source_id,source_name,source_type,source_reference,retrieved_at,
               data_version,quality_status,file_sha256,record_count,metadata_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET
               source_name=excluded.source_name,source_type=excluded.source_type,
               source_reference=excluded.source_reference,retrieved_at=excluded.retrieved_at,
               data_version=excluded.data_version,quality_status=excluded.quality_status,
               file_sha256=excluded.file_sha256,record_count=excluded.record_count,
               metadata_json=excluded.metadata_json""",
            (
                source_id,
                source_name,
                source_type,
                source_reference,
                retrieved_at,
                dataset_version,
                source_quality,
                source_hash,
                len(records),
                json.dumps({"is_current": is_current}, ensure_ascii=False),
            ),
        )
        if is_current:
            db.execute("UPDATE administrative_units SET is_current=0 WHERE is_current=1")
            db.execute("UPDATE administrative_dataset_versions SET is_current=0 WHERE is_current=1")

        for row in records:
            values = (
                row.get("administrative_code"),
                row["administrative_name"],
                row["normalized_name"],
                row["normalized_province"],
                row["administrative_level"],
                row.get("administrative_type") or row["administrative_level"],
                row.get("parent_unit_code"),
                row.get("parent_unit_level"),
                row.get("province_code"),
                row["province_name"],
                row.get("district_code_legacy"),
                row.get("district_name_legacy"),
                dataset_version,
                row.get("valid_from"),
                row.get("valid_to"),
                int(is_current),
                "OFFICIAL_CURRENT" if is_current else "HISTORICAL_SNAPSHOT_UNMAPPED",
                row["source_reference"],
                source_id,
                now,
                now,
            )
            code = row.get("administrative_code")
            if code:
                db.execute(
                    """INSERT INTO administrative_units(
                       administrative_code,administrative_name,normalized_name,
                       normalized_province,administrative_level,administrative_type,
                       parent_unit_code,parent_unit_level,province_code,province_name,
                       district_code_legacy,district_name_legacy,administrative_version,
                       valid_from,valid_to,is_current,mapping_status,source_reference,
                       source_id,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(
                           administrative_version,administrative_level,province_code,
                           administrative_code,normalized_name
                       )
                       WHERE administrative_code IS NOT NULL DO UPDATE SET
                       administrative_name=excluded.administrative_name,
                       normalized_name=excluded.normalized_name,
                       normalized_province=excluded.normalized_province,
                       administrative_type=excluded.administrative_type,
                       parent_unit_code=excluded.parent_unit_code,
                       parent_unit_level=excluded.parent_unit_level,
                       province_code=excluded.province_code,
                       province_name=excluded.province_name,
                       district_code_legacy=excluded.district_code_legacy,
                       district_name_legacy=excluded.district_name_legacy,
                       valid_from=excluded.valid_from,valid_to=excluded.valid_to,
                       is_current=excluded.is_current,mapping_status=excluded.mapping_status,
                       source_reference=excluded.source_reference,source_id=excluded.source_id,
                       updated_at=excluded.updated_at""",
                    values,
                )
            else:
                existing = db.execute(
                    """SELECT id FROM administrative_units WHERE administrative_version=?
                       AND administrative_level=? AND normalized_name=? AND province_code IS ?
                       AND district_code_legacy IS ?""",
                    (
                        dataset_version,
                        row["administrative_level"],
                        row["normalized_name"],
                        row.get("province_code"),
                        row.get("district_code_legacy"),
                    ),
                ).fetchall()
                if len(existing) > 1:
                    raise ValueError(
                        "Cannot idempotently import duplicate no-code rows; provide an official "
                        "administrative code or a source-specific crosswalk"
                    )
                if existing:
                    db.execute(
                        """UPDATE administrative_units SET administrative_name=?,
                           normalized_province=?,administrative_type=?,parent_unit_code=?,
                           parent_unit_level=?,province_name=?,is_current=?,mapping_status=?,
                           source_reference=?,source_id=?,updated_at=? WHERE id=?""",
                        (
                            row["administrative_name"],
                            row["normalized_province"],
                            row.get("administrative_type") or row["administrative_level"],
                            row.get("parent_unit_code"),
                            row.get("parent_unit_level"),
                            row["province_name"],
                            int(is_current),
                            "OFFICIAL_CURRENT" if is_current else "HISTORICAL_SNAPSHOT_UNMAPPED",
                            row["source_reference"],
                            source_id,
                            now,
                            existing[0]["id"],
                        ),
                    )
                else:
                    db.execute(
                        """INSERT INTO administrative_units(
                           administrative_code,administrative_name,normalized_name,
                           normalized_province,administrative_level,administrative_type,
                           parent_unit_code,parent_unit_level,province_code,province_name,
                           district_code_legacy,district_name_legacy,administrative_version,
                           valid_from,valid_to,is_current,mapping_status,source_reference,
                           source_id,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        values,
                    )

        if is_current:
            codes = [row.get("administrative_code") for row in records if row.get("administrative_code")]
            if codes:
                placeholders = ",".join("?" for _ in codes)
                db.execute(
                    f"""UPDATE administrative_units SET is_current=0
                        WHERE administrative_version=? AND administrative_code IS NOT NULL
                          AND administrative_code NOT IN ({placeholders})""",
                    (dataset_version, *codes),
                )

        # Link parent rows only inside the same version. Codes remain source data;
        # the local integer primary key is never presented as an admin code.
        for row in records:
            if not row.get("parent_unit_code") or not row.get("parent_unit_level"):
                continue
            child_code = row.get("administrative_code")
            if not child_code:
                continue
            db.execute(
                """UPDATE administrative_units SET parent_unit_id=(
                     SELECT CASE WHEN COUNT(*)=1 THEN MAX(parent.id) END
                     FROM administrative_units AS parent
                     WHERE parent.administrative_version=?
                       AND parent.administrative_level=?
                       AND parent.administrative_code=?
                       AND parent.province_code=?
                   ) WHERE administrative_version=? AND administrative_level=?
                     AND administrative_code=?""",
                (
                    dataset_version,
                    row["parent_unit_level"],
                    row["parent_unit_code"],
                    row.get("province_code"),
                    dataset_version,
                    row["administrative_level"],
                    child_code,
                ),
            )

        # Historical names are searchable as historical records, never as a
        # silently resolved current alias.
        for row in records:
            code = row.get("administrative_code")
            unit = None
            if code:
                unit = db.execute(
                    """SELECT id FROM administrative_units WHERE administrative_version=?
                       AND administrative_level=? AND administrative_code=? LIMIT 1""",
                    (dataset_version, row["administrative_level"], code),
                ).fetchone()
            if unit:
                _upsert_alias(
                    db,
                    unit_id=unit["id"],
                    alias_name=row["administrative_name"],
                    alias_type="OFFICIAL_NAME" if is_current else "HISTORICAL_SNAPSHOT_NAME",
                    source_reference=row["source_reference"],
                    mapping_status="OFFICIAL_CURRENT" if is_current else "UNRESOLVED",
                    target_rank=None,
                    source_version=dataset_version,
                    province_name=row["province_name"],
                    district_name_legacy=row.get("district_name_legacy"),
                    now=now,
                )

        db.execute(
            """INSERT INTO administrative_dataset_versions(
               dataset_version,as_of_date,source_id,source_hash,record_count,
               province_count,district_count,commune_count,imported_at,status,is_current,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(dataset_version) DO UPDATE SET
               as_of_date=excluded.as_of_date,source_id=excluded.source_id,
               source_hash=excluded.source_hash,record_count=excluded.record_count,
               province_count=excluded.province_count,district_count=excluded.district_count,
               commune_count=excluded.commune_count,imported_at=excluded.imported_at,
               status=excluded.status,is_current=excluded.is_current,notes=excluded.notes""",
            (
                dataset_version,
                as_of_date,
                source_id,
                source_hash,
                len(records),
                counts["PROVINCE"],
                counts["DISTRICT_HISTORIC"],
                counts["COMMUNE"],
                now,
                dataset_status,
                int(is_current),
                notes,
            ),
        )
        target_counts = {"target_count": 0, "mapped_count": 0, "pending_count": 0}
        if is_current:
            target_counts = _refresh_priority_targets(
                db, current_version=dataset_version, now=now
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "dataset_version": dataset_version,
        "as_of_date": as_of_date,
        "is_current": is_current,
        "source_id": source_id,
        "source_sha256": source_hash,
        "record_count": len(records),
        "province_count": counts["PROVINCE"],
        "district_count": counts["DISTRICT_HISTORIC"],
        "commune_count": counts["COMMUNE"],
        "priority_targets": target_counts,
    }


def import_admin_file(
    db: sqlite3.Connection,
    path: Path,
    *,
    as_of_date: str,
    is_current: bool = False,
    dataset_status: str = "IMPORTED",
    source_quality: str = "OFFICIAL_SOURCE",
    source_reference: str = OFFICIAL_NSO_REFERENCE,
    source_name: str = "NSO administrative directory",
) -> dict[str, Any]:
    """Import one XML or normalized CSV file; no network operation is performed."""
    path = Path(path)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix.casefold() == ".xml":
        records, parsed = parse_nso_soap_xml(
            path, as_of_date=as_of_date, source_reference=source_reference
        )
        notes = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    elif path.suffix.casefold() == ".csv":
        records, parsed = load_admin_csv(path)
        versions = {row["administrative_version"] for row in records}
        if len(versions) != 1:
            raise ValueError("CSV import must contain exactly one administrative_version")
        notes = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    else:
        raise ValueError("Administrative importer accepts official NSO XML or normalized CSV")
    versions = {row["administrative_version"] for row in records}
    if len(versions) != 1:
        raise ValueError("Import must contain exactly one administrative version")
    dataset_version = next(iter(versions))
    return import_administrative_records(
        db,
        records,
        dataset_version=dataset_version,
        as_of_date=as_of_date,
        source_reference=source_reference,
        source_name=source_name,
        source_type="OFFICIAL_GOVERNMENT_DATA",
        source_quality=source_quality,
        file_sha256=file_hash,
        is_current=is_current,
        dataset_status=dataset_status,
        notes=notes,
    )


def import_crosswalk_csv(
    db: sqlite3.Connection,
    path: Path,
    *,
    source_reference: str,
) -> dict[str, Any]:
    """Import explicit, source-backed historical relations without guessing names."""
    required = {
        "alias_name",
        "relationship_type",
        "mapping_status",
        "source_reference",
        "effective_date",
    }
    path = Path(path)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Crosswalk CSV must include {sorted(required)}")
        rows = list(reader)
    if not rows:
        raise ValueError("Crosswalk CSV is empty")
    source_id = "crosswalk-" + file_hash[:20]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted_relations = mapped_aliases = unresolved_aliases = 0
    allowed_relationships = {"MERGED", "RENAMED", "SPLIT", "PARTIAL_TRANSFER", "UNRESOLVED"}
    allowed_mapping_statuses = {
        "OFFICIAL_CROSSWALK_VERIFIED",
        "PARTIAL_TRANSFER_UNRESOLVED",
        "ONE_TO_MANY_REVIEW_REQUIRED",
        "PENDING_ADMIN_MAPPING",
        "REVIEW_REQUIRED",
        "UNRESOLVED",
    }
    with db:
        db.execute(
            """INSERT INTO data_sources(
               source_id,source_name,source_type,source_reference,retrieved_at,
               data_version,quality_status,file_sha256,record_count,metadata_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET retrieved_at=excluded.retrieved_at,
               record_count=excluded.record_count,metadata_json=excluded.metadata_json""",
            (
                source_id,
                "NSO administrative crosswalk",
                "OFFICIAL_GOVERNMENT_CROSSWALK",
                source_reference,
                now,
                f"crosswalk-{now[:10]}",
                "OFFICIAL_SOURCE_REVIEWED_ROWS",
                file_hash,
                len(rows),
                json.dumps({"source_file": path.name}, ensure_ascii=False),
            ),
        )
        for index, row in enumerate(rows, start=2):
            alias_name = _clean(row.get("alias_name"))
            relationship_type = _clean(row.get("relationship_type")).upper()
            mapping_status = _clean(row.get("mapping_status")).upper()
            row_reference = _clean(row.get("source_reference")) or source_reference
            effective_date = _clean(row.get("effective_date")) or None
            province_name = _clean(row.get("province_name")) or None
            district_name = _clean(row.get("district_name_legacy")) or None
            target_code = _clean(row.get("target_code")) or None
            source_code = _clean(row.get("source_code")) or None
            source_version = _clean(row.get("source_version")) or None
            if (
                not alias_name
                or relationship_type not in allowed_relationships
                or mapping_status not in allowed_mapping_statuses
            ):
                raise ValueError(f"Crosswalk row {index} has an invalid alias or relationship type")
            if not row_reference:
                raise ValueError(f"Crosswalk row {index} has no source reference")
            target = None
            if target_code:
                targets = db.execute(
                    """SELECT id FROM administrative_units WHERE administrative_level='COMMUNE'
                       AND is_current=1 AND administrative_code=? LIMIT 2""",
                    (target_code,),
                ).fetchall()
                if len(targets) != 1:
                    raise ValueError(f"Crosswalk row {index} target_code is not a unique current unit")
                target = targets[0]
            source = None
            if source_code and source_version:
                sources = db.execute(
                    """SELECT id FROM administrative_units WHERE administrative_level='COMMUNE'
                       AND administrative_version=? AND administrative_code=?
                       AND (? IS NULL OR normalized_province=?) LIMIT 2""",
                    (
                        source_version,
                        source_code,
                        normalize_admin_name(province_name) if province_name else None,
                        normalize_admin_name(province_name) if province_name else None,
                    ),
                ).fetchall()
                source = sources[0] if len(sources) == 1 else None
            mapping_is_verified = (
                mapping_status == "OFFICIAL_CROSSWALK_VERIFIED"
                and relationship_type in {"MERGED", "RENAMED"}
                and target is not None
            )
            alias_unit_id = target["id"] if mapping_is_verified else None
            alias_type = "OFFICIAL_CROSSWALK" if mapping_is_verified else "UNRESOLVED_HISTORICAL"
            _upsert_alias(
                db,
                unit_id=alias_unit_id,
                alias_name=alias_name,
                alias_type=alias_type,
                source_reference=row_reference,
                mapping_status=("OFFICIAL_ALIAS" if mapping_is_verified else mapping_status),
                target_rank=None,
                source_version=source_version or f"crosswalk-{now[:10]}",
                now=now,
                province_name=province_name,
                district_name_legacy=district_name,
            )
            if mapping_is_verified:
                mapped_aliases += 1
            else:
                unresolved_aliases += 1
            exists = db.execute(
                """SELECT 1 FROM administrative_relationships
                   WHERE source_unit_id IS ? AND target_unit_id IS ?
                     AND relationship_type=? AND effective_date IS ?
                     AND source_reference=? LIMIT 1""",
                (
                    source["id"] if source else None,
                    target["id"] if target else None,
                    relationship_type,
                    effective_date,
                    row_reference,
                ),
            ).fetchone()
            if not exists:
                db.execute(
                    """INSERT INTO administrative_relationships(
                       source_unit_id,target_unit_id,relationship_type,effective_date,
                       mapping_status,source_reference,source_id,raw_payload,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        source["id"] if source else None,
                        target["id"] if target else None,
                        relationship_type,
                        effective_date,
                        mapping_status,
                        row_reference,
                        source_id,
                        json.dumps(dict(row), ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
                inserted_relations += 1
    return {
        "source_id": source_id,
        "source_sha256": file_hash,
        "records_received": len(rows),
        "relationships_inserted": inserted_relations,
        "verified_aliases": mapped_aliases,
        "unresolved_aliases": unresolved_aliases,
    }


def _public_unit(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": row["id"],
        "administrative_code": row["administrative_code"],
        "name": row["administrative_name"],
        "administrative_level": row["administrative_level"],
        "administrative_type": row["administrative_type"],
        "province_code": row["province_code"],
        "province": row["province_name"],
        "legacy_district": row["district_name_legacy"],
        "version": row["administrative_version"],
        "is_current": bool(row["is_current"]),
        "mapping_status": row["mapping_status"],
        "source_reference": row["source_reference"],
    }


def _alias_target(row: sqlite3.Row) -> dict[str, Any]:
    if row["administrative_unit_id"] is None:
        return {
            "unit_id": None,
            "administrative_code": None,
            "name": row["alias_name"],
            "administrative_level": "COMMUNE",
            "administrative_type": "LEGACY_TARGET",
            "province_code": None,
            "province": row["original_province"],
            "legacy_district": row["original_district"],
            "version": row["source_version"],
            "is_current": False,
            "mapping_status": row["mapping_status"],
            "source_reference": row["source_reference"],
            "target_rank": row["target_rank"],
        }
    unit = row
    result = _public_unit(unit)
    result["target_rank"] = row["target_rank"]
    result["matched_alias"] = row["alias_name"]
    result["mapping_status"] = row["mapping_status"]
    return result


def search_administrative_units(
    db: sqlite3.Connection,
    query: str = "",
    *,
    province: str | None = None,
    legacy_district: str | None = None,
    target_rank: int | None = None,
    include_historical: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search current units and explicit aliases; fuzzy matches are never auto-selected."""
    limit = max(1, min(int(limit), 100))
    normalized_query = normalize_admin_name(query)
    normalized_province = normalize_admin_name(province) if province else ""
    normalized_district = normalize_admin_name(legacy_district) if legacy_district else ""
    if target_rank is not None:
        mapped_targets = db.execute(
            """SELECT DISTINCT pt.target_rank,pt.original_ward,pt.original_province,
                      pt.original_district,pt.mapping_status AS target_mapping_status,
                      pt.source_reference AS target_source_reference,u.*
               FROM priority_target_mappings pm
               JOIN priority_targets pt ON pt.target_rank=pm.target_rank
               JOIN administrative_units u ON u.id=pm.administrative_unit_id
               WHERE pm.target_rank=? AND u.is_current=1
               ORDER BY u.province_name,u.administrative_name""",
            (target_rank,),
        ).fetchall()
        if mapped_targets:
            output = []
            for target in mapped_targets:
                item = _public_unit(target)
                item.update(
                    {
                        "target_rank": target["target_rank"],
                        "original_ward": target["original_ward"],
                        "matched_alias": target["original_ward"],
                        "mapping_status": target["target_mapping_status"],
                        "source_reference": target["target_source_reference"],
                    }
                )
                output.append(item)
            return output
        target = db.execute(
            """SELECT pt.target_rank,pt.original_ward AS alias_name,
                      pt.original_district,pt.original_province,
                      pt.administrative_unit_id,pt.mapping_status,
                      'legacy-top50-review' AS source_version,
                      pt.source_reference,u.*
               FROM priority_targets pt LEFT JOIN administrative_units u
                 ON u.id=pt.administrative_unit_id
               WHERE pt.target_rank=?""",
            (target_rank,),
        ).fetchone()
        if not target:
            return []
        return [_alias_target(target)]

    rows: list[dict[str, Any]] = []
    params: list[Any] = []
    query_sql = "SELECT * FROM administrative_units WHERE administrative_level='COMMUNE'"
    if not include_historical:
        query_sql += " AND is_current=1"
    if normalized_province:
        query_sql += " AND normalized_province=?"
        params.append(normalized_province)
    if normalized_district:
        query_sql += " AND COALESCE(district_name_legacy,'')<>''"
    units = db.execute(query_sql, params).fetchall()
    if normalized_query:
        code_matches = [
            unit for unit in units
            if str(unit["administrative_code"] or "") == str(query).strip()
        ]
        if code_matches:
            return [_public_unit(unit) for unit in code_matches[:limit]]

        # Prefix removal lets users omit or include the administrative type
        # without matching unrelated units that merely contain the same word.
        search_terms = {normalized_query}
        type_prefixes = {
            "phuong ": "phuong",
            "xa ": "xa",
            "dac khu ": "dac khu",
            "thi tran ": "thi tran",
        }
        required_type = None
        for prefix in ("phuong ", "xa ", "dac khu ", "thi tran "):
            if normalized_query.startswith(prefix):
                search_terms.add(normalized_query[len(prefix):])
                required_type = type_prefixes[prefix]
        for unit in units:
            name = unit["normalized_name"]
            district_name = normalize_admin_name(unit["district_name_legacy"])
            if required_type and normalize_admin_name(unit["administrative_type"]) != required_type:
                continue
            if not any(term and (term in name or term in district_name) for term in search_terms):
                continue
            if normalized_district and normalized_district not in district_name:
                continue
            rows.append(_public_unit(unit))
    else:
        rows = [_public_unit(unit) for unit in units]
        if normalized_district:
            rows = [
                row for row in rows
                if normalized_district in normalize_admin_name(row["legacy_district"])
            ]

    # Aliases are evidence-backed lookups, not automatic geographic decisions.
    # Unresolved aliases stay visible as unresolved candidates.
    if normalized_query:
        alias_rows = db.execute(
            """SELECT a.alias_name,a.province_name AS alias_province_name,
                      a.district_name_legacy AS alias_district_name,
                      a.administrative_unit_id AS alias_unit_id,
                      a.mapping_status,a.target_rank,a.source_version,a.source_reference,
                      pt.original_district,pt.original_province,
                      u.id,u.administrative_code,u.administrative_name,
                      u.administrative_level,u.administrative_type,u.province_code,
                      u.province_name,u.district_name_legacy,u.administrative_version,
                      u.is_current,u.source_reference AS unit_source_reference
               FROM administrative_aliases a
               LEFT JOIN priority_targets pt ON pt.target_rank=a.target_rank
               LEFT JOIN administrative_units u ON u.id=a.administrative_unit_id
               WHERE a.normalized_alias LIKE ?
                 AND ((a.target_rank IS NOT NULL AND ?=1)
                      OR (a.target_rank IS NULL AND
                          (a.mapping_status IN ('OFFICIAL_ALIAS','OFFICIAL_CROSSWALK_VERIFIED')
                           OR ?=1)))
               ORDER BY a.target_rank,a.alias_name LIMIT ?""",
            (f"%{normalized_query}%", int(include_historical), int(include_historical), limit),
        ).fetchall()
        for alias in alias_rows:
            if alias["target_rank"] is not None:
                if normalized_province and normalize_admin_name(
                    alias["original_province"]
                ) != normalized_province:
                    continue
                item = _alias_target(
                    {
                        **dict(alias),
                        "administrative_unit_id": alias["alias_unit_id"],
                        "source_reference": alias["source_reference"],
                        "source_version": alias["source_version"],
                    }
                )
                if item.get("unit_id") is not None:
                    item["source_reference"] = (
                        alias["unit_source_reference"] or alias["source_reference"]
                    )
            elif alias["alias_unit_id"] is not None:
                if normalized_province and normalize_admin_name(alias["province_name"]) != normalized_province:
                    continue
                item = _public_unit(alias)
                item["matched_alias"] = alias["alias_name"]
                item["mapping_status"] = alias["mapping_status"]
                item["source_reference"] = alias["source_reference"]
                item["is_current"] = bool(alias["is_current"])
            else:
                item = {
                    "unit_id": None,
                    "administrative_code": None,
                    "name": alias["alias_name"],
                    "administrative_level": "COMMUNE",
                    "administrative_type": "HISTORICAL_ALIAS",
                    "province_code": None,
                    "province": alias["original_province"] or alias["alias_province_name"] or "",
                    "legacy_district": alias["original_district"] or alias["alias_district_name"] or "",
                    "version": alias["source_version"],
                    "is_current": False,
                    "mapping_status": alias["mapping_status"],
                    "source_reference": alias["source_reference"],
                }
                if normalized_province and normalize_admin_name(item["province"]) != normalized_province:
                    continue
            rows.append(item)

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("unit_id"), row.get("target_rank"), row.get("name"))
        unique.setdefault(key, row)
    results = list(unique.values())
    results.sort(
        key=lambda row: (
            not row.get("is_current", False),
            normalize_admin_name(row.get("name")),
            normalize_admin_name(row.get("province")),
            row.get("target_rank") or 0,
        )
    )
    return results[:limit]


def _verified_statistics(
    db: sqlite3.Connection,
    unit_id: int,
    property_type: str | None,
    area_basis: str | None,
) -> list[dict[str, Any]]:
    filters = ["administrative_unit_id=?", "sample_count>0"]
    params: list[Any] = [unit_id]
    if property_type:
        filters.append("property_type=?")
        params.append(property_type)
    if area_basis:
        filters.append("area_basis=?")
        params.append(area_basis)
    rows = db.execute(
        """SELECT property_type,area_basis,snapshot_date,sample_count,
                  mean_price_per_m2,median_price_per_m2,min_price_per_m2,
                  max_price_per_m2,latest_observation_at,source_quality,
                  calculation_window_days,calculation_version
           FROM ward_price_statistics WHERE """ + " AND ".join(filters)
        + " ORDER BY snapshot_date DESC,property_type,area_basis",
        params,
    ).fetchall()
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["property_type"], row["area_basis"])
        if key not in latest:
            latest[key] = dict(row)
    return list(latest.values())


def lookup_ward_price(
    db: sqlite3.Connection,
    query: str = "",
    *,
    province: str | None = None,
    legacy_district: str | None = None,
    target_rank: int | None = None,
    property_type: str | None = None,
    area_basis: str | None = None,
    refresh: bool = False,
    stale_after_days: int = 30,
) -> dict[str, Any]:
    """Return local verified data first, with clear no-data and mapping states."""
    if property_type and property_type not in PROPERTY_TYPES:
        raise ValueError(f"property_type must be one of {sorted(PROPERTY_TYPES)}")
    if area_basis and area_basis not in AREA_BASES:
        raise ValueError(f"area_basis must be one of {sorted(AREA_BASES)}")
    matches = search_administrative_units(
        db,
        query,
        province=province,
        legacy_district=legacy_district,
        target_rank=target_rank,
        include_historical=True,
        limit=25,
    )
    if not matches:
        return {
            "status": "NOT_FOUND",
            "administrative_unit": None,
            "statistics": [],
            "provider_status": "NOT_REQUESTED",
        }
    unit_ids = {row.get("unit_id") for row in matches if row.get("unit_id") is not None}
    pending = [row for row in matches if row.get("unit_id") is None]
    if len(unit_ids) > 1 or (pending and unit_ids):
        return {
            "status": "AMBIGUOUS",
            "administrative_unit": None,
            "candidates": matches,
            "statistics": [],
            "provider_status": "NOT_REQUESTED",
        }
    if pending:
        return {
            "status": "NO_PRICE_DATA",
            "administrative_status": pending[0].get("mapping_status", "UNRESOLVED"),
            "administrative_unit": pending[0],
            "statistics": [],
            "provider_status": "NOT_REQUESTED",
        }

    unit_id = next(iter(unit_ids))
    unit = db.execute("SELECT * FROM administrative_units WHERE id=?", (unit_id,)).fetchone()
    if not unit:
        return {"status": "NOT_FOUND", "administrative_unit": None, "statistics": []}
    public_unit = _public_unit(unit)
    if not unit["is_current"]:
        return {
            "status": "NO_PRICE_DATA",
            "administrative_status": "HISTORICAL_UNMAPPED",
            "administrative_unit": public_unit,
            "statistics": [],
            "provider_status": "NOT_REQUESTED",
        }

    statistics = _verified_statistics(db, unit_id, property_type, area_basis)
    if statistics:
        newest = max(
            (entry.get("latest_observation_at") or entry["snapshot_date"])[:10]
            for entry in statistics
        )
        try:
            today = datetime.now(timezone.utc).astimezone().date()
            age_days = (today - date.fromisoformat(newest)).days
        except ValueError:
            age_days = stale_after_days + 1
        status = "STALE_DATA" if age_days > stale_after_days else "FOUND"
        return {
            "status": status,
            "source": "LOCAL_DB",
            "administrative_unit": public_unit,
            "property_type": property_type,
            "area_basis": area_basis,
            "statistics": statistics,
            "sample_count": statistics[0]["sample_count"] if len(statistics) == 1 else None,
            "sample_counts_by_group": [
                {
                    "property_type": entry["property_type"],
                    "area_basis": entry["area_basis"],
                    "sample_count": entry["sample_count"],
                }
                for entry in statistics
            ],
            "source_quality": sorted({entry["source_quality"] for entry in statistics}),
            "snapshot_date": max(entry["snapshot_date"] for entry in statistics),
            "last_updated": newest,
            "provider_status": "NOT_REQUESTED",
        }

    candidate_count = db.execute(
        """SELECT COUNT(DISTINCT l.listing_id) FROM listings l
           WHERE l.administrative_unit_id=? AND l.active=1
             AND (l.evidence_status!='SOURCE_PAGE_CONFIRMED'
                  OR COALESCE(l.validation_status,'')!='VALIDATED')
             AND (? IS NULL OR l.property_type=?)""",
        (unit_id, property_type, property_type),
    ).fetchone()[0]
    if candidate_count:
        status = "UNVERIFIED_ONLY"
    else:
        status = "NO_PRICE_DATA"
    provider_status = "NOT_REQUESTED"
    if refresh:
        provider_status = "EXTERNAL_PROVIDER_NOT_CONFIGURED"
        status = "EXTERNAL_PROVIDER_NOT_CONFIGURED"
    return {
        "status": status,
        "source": "LOCAL_DB",
        "administrative_unit": public_unit,
        "property_type": property_type,
        "statistics": [],
        "candidate_count": candidate_count,
        "provider_status": provider_status,
        "provider_network_called": False,
    }


def price_history(
    db: sqlite3.Connection,
    unit_id: int,
    *,
    property_type: str | None = None,
    area_basis: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    filters = ["lo.administrative_unit_id=?"]
    params: list[Any] = [unit_id]
    if property_type:
        filters.append("l.property_type=?")
        params.append(property_type)
    if area_basis:
        filters.append("lo.area_basis=?")
        params.append(area_basis)
    params.append(max(1, min(int(limit), 1000)))
    rows = db.execute(
        """SELECT lo.listing_id,l.property_type,lo.area_basis,lo.observation_date,
                  lo.observed_price_vnd,lo.observed_area_m2,lo.price_per_m2,
                  lo.evidence_status,lo.validation_status,lo.source_url,
                  lo.source_run_id
           FROM listing_observations lo JOIN listings l ON l.listing_id=lo.listing_id
           WHERE """ + " AND ".join(filters)
        + " ORDER BY lo.observation_date DESC,lo.id DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def national_collection_priorities(
    db: sqlite3.Connection,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Build a deterministic P0/P1/P2 refresh queue from reviewed local data.

    P0 contains current units linked to a Top 50 target by an explicit reviewed
    mapping. P1 contains other current units with at least one active listing,
    including unverified candidates that need review or refresh. P2 contains
    current units without active listings. Unmapped Top 50 targets remain in a
    separate list and are never assigned to a current unit by name similarity.
    """
    limit = max(0, min(int(limit), 5000))
    version = db.execute(
        "SELECT dataset_version FROM administrative_dataset_versions WHERE is_current=1 "
        "ORDER BY as_of_date DESC LIMIT 1"
    ).fetchone()
    if not version:
        current_units: list[sqlite3.Row] = []
    else:
        current_units = db.execute(
            """SELECT id,administrative_code,administrative_name,province_name,
                      administrative_type
               FROM administrative_units
               WHERE administrative_version=? AND is_current=1
                 AND administrative_level='COMMUNE'
               ORDER BY province_name,administrative_name""",
            (version["dataset_version"],),
        ).fetchall()

    target_ranks_by_unit: dict[int, set[int]] = defaultdict(set)
    for row in db.execute(
        """SELECT DISTINCT pm.target_rank,pm.administrative_unit_id
           FROM priority_target_mappings pm JOIN administrative_units u
             ON u.id=pm.administrative_unit_id
           WHERE u.is_current=1
             AND pm.mapping_status IN ('REVIEWED_RESOLUTION','OFFICIAL_CROSSWALK_VERIFIED')
           UNION
           SELECT pt.target_rank,pt.administrative_unit_id
           FROM priority_targets pt JOIN administrative_units u
             ON u.id=pt.administrative_unit_id
           WHERE u.is_current=1
             AND pt.mapping_status IN ('REVIEWED_RESOLUTION','OFFICIAL_CROSSWALK_VERIFIED')"""
    ):
        target_ranks_by_unit[int(row["administrative_unit_id"])].add(int(row["target_rank"]))

    listing_state: dict[int, dict[str, Any]] = {}
    for row in db.execute(
        """SELECT l.administrative_unit_id,
                  COUNT(DISTINCT l.listing_id) AS active_listing_count,
                  COUNT(DISTINCT CASE WHEN l.included_in_stats=1
                    AND l.evidence_status='SOURCE_PAGE_CONFIRMED'
                    AND l.validation_status='VALIDATED' THEN l.listing_id END)
                    AS verified_listing_count,
                  MAX(COALESCE(obs.latest_observed_at,l.last_seen_at)) AS last_observed_at
           FROM listings l
           LEFT JOIN (
               SELECT listing_id,MAX(observed_at) AS latest_observed_at
               FROM listing_observations GROUP BY listing_id
           ) obs ON obs.listing_id=l.listing_id
           WHERE l.active=1 AND l.administrative_unit_id IS NOT NULL
           GROUP BY l.administrative_unit_id"""
    ):
        listing_state[int(row["administrative_unit_id"])] = {
            "active_listing_count": int(row["active_listing_count"]),
            "verified_listing_count": int(row["verified_listing_count"]),
            "last_observed_at": row["last_observed_at"],
        }

    units = []
    for unit in current_units:
        state = listing_state.get(unit["id"], {})
        target_ranks = sorted(target_ranks_by_unit.get(unit["id"], set()))
        listing_count = state.get("active_listing_count", 0)
        tier = "P0" if target_ranks else "P1" if listing_count else "P2"
        units.append(
            {
                "priority": tier,
                "priority_reason": (
                    "TOP50_REVIEWED_MAPPING" if target_ranks
                    else "ACTIVE_LISTING_NEEDS_REFRESH" if listing_count
                    else "NO_LISTING_DATA"
                ),
                "administrative_unit_id": unit["id"],
                "administrative_code": unit["administrative_code"],
                "name": unit["administrative_name"],
                "administrative_type": unit["administrative_type"],
                "province": unit["province_name"],
                "target_ranks": target_ranks,
                "active_listing_count": listing_count,
                "verified_listing_count": state.get("verified_listing_count", 0),
                "last_observed_at": state.get("last_observed_at"),
            }
        )
    tier_order = {"P0": 0, "P1": 1, "P2": 2}
    units.sort(
        key=lambda row: (
            tier_order[row["priority"]],
            row["target_ranks"][0] if row["target_ranks"] else 0,
            row["last_observed_at"] or "",
            normalize_admin_name(row["province"]),
            normalize_admin_name(row["name"]),
        )
    )

    mapped_target_ranks = {rank for ranks in target_ranks_by_unit.values() for rank in ranks}
    unmapped_targets = [
        dict(row)
        for row in db.execute(
            """SELECT target_rank,original_ward,original_district,original_province,
                      mapping_status,source_reference
               FROM priority_targets ORDER BY target_rank"""
        )
        if int(row["target_rank"]) not in mapped_target_ranks
    ]
    tier_counts = {
        tier: {
            "unit_count": sum(row["priority"] == tier for row in units),
            "active_listing_count": sum(
                row["active_listing_count"] for row in units if row["priority"] == tier
            ),
        }
        for tier in ("P0", "P1", "P2")
    }
    return {
        "policy": {
            "P0": "Top 50 targets with reviewed current-unit mapping",
            "P1": "Other current units with active listings that need refresh or review",
            "P2": "Current units with no active listings",
            "unmapped_target_policy": "Keep separate; do not infer a current unit",
        },
        "tier_counts": tier_counts,
        "unmapped_priority_target_count": len(unmapped_targets),
        "unmapped_priority_targets": unmapped_targets,
        "units": units[:limit] if limit else [],
        "unit_count": len(units),
    }


def national_coverage(db: sqlite3.Connection, *, stale_after_days: int = 30) -> dict[str, Any]:
    version = db.execute(
        """SELECT dataset_version,as_of_date,source_id,record_count,province_count,
                  commune_count,imported_at
           FROM administrative_dataset_versions WHERE is_current=1
           ORDER BY as_of_date DESC LIMIT 1"""
    ).fetchone()
    if not version:
        return {
            "registry_status": AWAITING_DATA_STATUS,
            "current_dataset": None,
            "administrative_coverage": {
                "province_count": 0,
                "commune_count": 0,
                "historical_commune_count": db.execute(
                    "SELECT COUNT(*) FROM administrative_units WHERE administrative_level='COMMUNE'"
                ).fetchone()[0],
            },
            "price_coverage": {
                "units_with_verified_price": 0,
                "units_with_fresh_verified_price": 0,
                "units_with_stale_price": 0,
                "units_with_unverified_candidates": 0,
                "units_without_price_data": 0,
                "last_updated": None,
            },
            "by_province": [],
            "priority_targets": {"total": 0, "mapped": 0, "with_price_data": 0},
            "collection_priority_counts": national_collection_priorities(db, limit=0)["tier_counts"],
        }

    current_units = db.execute(
        """SELECT id,administrative_code,administrative_name,normalized_name,
                  province_code,province_name,administrative_type
           FROM administrative_units
           WHERE administrative_version=? AND is_current=1 AND administrative_level='COMMUNE'
           ORDER BY province_name,administrative_name""",
        (version["dataset_version"],),
    ).fetchall()
    today = datetime.now(timezone.utc).astimezone().date()
    freshness_cutoff = (today - timedelta(days=stale_after_days)).isoformat()
    unit_by_id = {row["id"]: row for row in current_units}
    latest_by_unit: dict[int, str] = {}
    for row in db.execute(
        """SELECT administrative_unit_id,MAX(latest_observation_at) AS latest
           FROM ward_price_statistics WHERE sample_count>0
           GROUP BY administrative_unit_id"""
    ):
        if row["administrative_unit_id"] in unit_by_id and row["latest"]:
            latest_by_unit[row["administrative_unit_id"]] = str(row["latest"])[:10]
    candidate_units = {
        row[0]
        for row in db.execute(
            """SELECT DISTINCT administrative_unit_id FROM listings
               WHERE active=1 AND administrative_unit_id IS NOT NULL
                 AND (evidence_status!='SOURCE_PAGE_CONFIRMED'
                      OR COALESCE(validation_status,'')!='VALIDATED')"""
        )
        if row[0] in unit_by_id
    }
    verified_ids = set(latest_by_unit)
    stale_ids = {
        unit_id for unit_id, day in latest_by_unit.items() if day < freshness_cutoff
    }
    fresh_ids = verified_ids - stale_ids
    candidate_only = candidate_units - verified_ids
    no_data = set(unit_by_id) - verified_ids - candidate_only
    last_updated = max(latest_by_unit.values()) if latest_by_unit else None

    by_province: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"administrative_units": 0, "with_verified_price": 0,
                 "with_fresh_price": 0, "with_stale_price": 0,
                 "with_unverified_candidates": 0, "without_price_data": 0}
    )
    for unit_id, unit in unit_by_id.items():
        key = (unit["province_code"], unit["province_name"])
        stats = by_province[key]
        stats["administrative_units"] += 1
        if unit_id in verified_ids:
            stats["with_verified_price"] += 1
        if unit_id in fresh_ids:
            stats["with_fresh_price"] += 1
        if unit_id in stale_ids:
            stats["with_stale_price"] += 1
        if unit_id in candidate_only:
            stats["with_unverified_candidates"] += 1
        if unit_id in no_data:
            stats["without_price_data"] += 1

    priority_rows = db.execute(
        """SELECT pt.target_rank,pt.administrative_unit_id,pt.mapping_status
           FROM priority_targets pt ORDER BY pt.target_rank"""
    ).fetchall()
    mapping_rows = db.execute(
        """SELECT DISTINCT pm.target_rank,pm.administrative_unit_id
           FROM priority_target_mappings pm JOIN administrative_units u
             ON u.id=pm.administrative_unit_id
           WHERE u.is_current=1"""
    ).fetchall()
    mapped_target_ranks = {row["target_rank"] for row in mapping_rows}
    targets_with_price = {
        row["target_rank"] for row in mapping_rows
        if row["administrative_unit_id"] in verified_ids
    }
    mapped_target_ranks.update(
        row["target_rank"]
        for row in priority_rows
        if row["administrative_unit_id"] and row["administrative_unit_id"] in unit_by_id
    )
    targets_with_price.update(
        row["target_rank"] for row in priority_rows
        if row["administrative_unit_id"] in verified_ids
    )
    return {
        "registry_status": CURRENT_DATA_STATUS,
        "current_dataset": {
            "dataset_version": version["dataset_version"],
            "as_of_date": version["as_of_date"],
            "source_id": version["source_id"],
            "record_count": version["record_count"],
            "province_count": version["province_count"],
            "commune_count": version["commune_count"],
            "imported_at": version["imported_at"],
        },
        "administrative_coverage": {
            "province_count": len({(row["province_code"], row["province_name"]) for row in current_units}),
            "commune_count": len(current_units),
            "historical_commune_count": db.execute(
                """SELECT COUNT(*) FROM administrative_units
                   WHERE administrative_level='COMMUNE' AND is_current=0"""
            ).fetchone()[0],
            "commune_types": dict(Counter(row["administrative_type"] for row in current_units)),
        },
        "price_coverage": {
            "units_with_verified_price": len(verified_ids),
            "units_with_fresh_verified_price": len(fresh_ids),
            "units_with_stale_price": len(stale_ids),
            "units_with_unverified_candidates": len(candidate_only),
            "units_without_price_data": len(no_data),
            "freshness_threshold_days": stale_after_days,
            "last_updated": last_updated,
        },
        "by_province": [
            {
                "province_code": province_code,
                "province": province_name,
                **values,
            }
            for (province_code, province_name), values in sorted(by_province.items(), key=lambda item: item[0][1])
        ],
        "priority_targets": {
            "total": len(priority_rows),
            "mapped": len(mapped_target_ranks),
            "with_price_data": len(targets_with_price),
            "mapping_status_counts": dict(Counter(row["mapping_status"] for row in priority_rows)),
        },
        "collection_priority_counts": national_collection_priorities(db, limit=0)["tier_counts"],
    }


class WardLookupService:
    """Local-first administrative search facade."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def search(self, query: str = "", **filters: Any) -> list[dict[str, Any]]:
        return search_administrative_units(self.db, query, **filters)

    def by_id(self, unit_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM administrative_units WHERE id=?", (int(unit_id),)
        ).fetchone()
        return _public_unit(row) if row else None


class WardPriceLookupService:
    """Local verified-price lookup facade with external fallback disabled by default."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def lookup(self, query: str = "", **filters: Any) -> dict[str, Any]:
        return lookup_ward_price(self.db, query, **filters)

    def history(self, unit_id: int, **filters: Any) -> list[dict[str, Any]]:
        return price_history(self.db, unit_id, **filters)
