"""Daily collection orchestration: dry-run is inert; live is permission and robots gated."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from wardprice.price_warehouse import canonicalize_source_url, import_listing_payload

from .html_collector import ConfiguredHTMLCollector
from .models import CollectionTarget
from .policy import CollectionBlocked, RobotsAwareClient
from .source_registry import cooldown_is_active, source_readiness
from .storage import (
    collection_settings,
    collection_targets,
    monitoring_summary,
    source_rows,
    store_candidate,
    store_discovered_url,
    store_rejection,
)

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PROPERTY_TYPES = ("DAT_O", "NHA_RIENG", "CHUNG_CU")
MAX_TARGET_OBSERVATIONS = 10
MAX_DAILY_OBSERVATIONS = 500


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def ranks_from_expression(value: str) -> set[int]:
    result: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start, end = int(left), int(right)
            if end < start:
                raise ValueError("rank ranges must be ascending")
            result.update(range(start, end + 1))
        else:
            result.add(int(token))
    if not result or min(result) < 1 or max(result) > 50:
        raise ValueError("ranks must be within 1..50")
    return result


def _public_source(source: dict) -> dict:
    return {
        "source_id": source["source_id"],
        "display_name": source["display_name"],
        "policy_status": source["policy_status"],
        "enabled": bool(source["enabled"]),
        "robots_status": source["robots_status"],
    }


def _run_row(db, run_id: str):
    return db.execute("SELECT * FROM collection_runs WHERE run_id=?", (run_id,)).fetchone()


def _prioritize_targets(db, targets: list[CollectionTarget]) -> list[CollectionTarget]:
    """Visit wards with the least verified coverage and oldest attempts first."""
    scored = []
    for target in targets:
        verified_count = 0
        if target.administrative_unit_id is not None:
            verified_count = int(db.execute(
                """SELECT COUNT(DISTINCT lo.listing_id) FROM listing_observations lo
                   JOIN listings l ON l.listing_id=lo.listing_id
                   WHERE lo.administrative_unit_id=? AND l.active=1
                     AND l.evidence_status='SOURCE_PAGE_CONFIRMED'
                     AND l.validation_status='VALIDATED' AND lo.validation_status='VALIDATED'
                     AND lo.evidence_status='SOURCE_PAGE_CONFIRMED'""",
                (target.administrative_unit_id,),
            ).fetchone()[0])
        last_attempt = db.execute(
            """SELECT MAX(a.finished_at) FROM collection_target_attempts a
               WHERE a.target_rank=?""",
            (target.rank,),
        ).fetchone()[0]
        scored.append(((verified_count, last_attempt is not None, last_attempt or "", target.rank), target))
    return [target for _score, target in sorted(scored, key=lambda row: row[0])]


def _begin_run(db, *, selected_ranks: list[int], run_date: str, resume: bool) -> tuple[str, bool]:
    db.execute("BEGIN IMMEDIATE")
    active = db.execute(
        "SELECT run_id,run_date,selection_json FROM collection_runs WHERE status='RUNNING' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    selection_json = json.dumps(selected_ranks)
    if active:
        db.rollback()
        raise RuntimeError(
            "COLLECTION_ALREADY_RUNNING; wait for the writer to stop before resuming an interrupted run"
        )
    if resume:
        previous = db.execute(
            """SELECT run_id,selection_json FROM collection_runs WHERE run_date=? AND mode='LIVE'
               AND status IN ('PARTIAL','INTERRUPTED') ORDER BY started_at DESC LIMIT 1""",
            (run_date,),
        ).fetchone()
        if previous:
            if previous["selection_json"] != selection_json:
                db.rollback()
                raise RuntimeError("RESUME_SELECTION_MISMATCH; target selection differs from interrupted run")
            db.execute("UPDATE collection_runs SET status='RUNNING',finished_at=NULL WHERE run_id=?", (previous["run_id"],))
            db.commit()
            return previous["run_id"], True
    run_id = "crawl_" + local_now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    db.execute(
        """INSERT INTO collection_runs(run_id,run_date,mode,status,started_at,selection_json,total_targets)
           VALUES(?,?,'LIVE','RUNNING',?,?,?)""",
        (run_id, run_date, local_now().isoformat(timespec="seconds"), selection_json, len(selected_ranks)),
    )
    db.commit()
    return run_id, False


def _record_attempt(db, *, run_id: str, source_id: str, target_rank: int, status: str,
                    request_count: int, discovered_count: int, candidate_count: int,
                    verified_count: int, duplicate_count: int, quarantine_count: int,
                    error_code: str | None = None, error: str | None = None,
                    retry_after: str | None = None, started_at: str | None = None,
                    increment: bool = False) -> None:
    now = local_now().isoformat(timespec="seconds")
    existing = db.execute(
        "SELECT id,attempt_count FROM collection_target_attempts WHERE run_id=? AND source_id=? AND target_rank=?",
        (run_id, source_id, target_rank),
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE collection_target_attempts SET finished_at=?,status=?,request_count=request_count+?,
               discovered_count=discovered_count+?,candidate_count=candidate_count+?,verified_count=verified_count+?,
               duplicate_count=duplicate_count+?,quarantine_count=quarantine_count+?,error_code=?,error=?,retry_after=?,
               attempt_count=attempt_count+? WHERE id=?""",
            (now, status, request_count, discovered_count, candidate_count, verified_count,
             duplicate_count, quarantine_count, error_code, error, retry_after, int(increment), existing["id"]),
        )
    else:
        db.execute(
            """INSERT INTO collection_target_attempts(run_id,source_id,target_rank,started_at,finished_at,status,
               request_count,discovered_count,candidate_count,verified_count,duplicate_count,quarantine_count,
               error_code,error,retry_after) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, source_id, target_rank, started_at or now, now, status, request_count, discovered_count,
             candidate_count, verified_count, duplicate_count, quarantine_count, error_code, error, retry_after),
        )
    db.commit()


def _log_http(db, run_id: str, source_id: str, target_rank: int | None, record: dict) -> None:
    at = local_now().isoformat(timespec="microseconds")
    status = record.get("status_code")
    outcome = "HTTP_OK" if status and 200 <= int(status) < 300 else "HTTP_ERROR" if status else "NETWORK_ERROR"
    error_code = "HTTP_429" if status == 429 else "HTTP_403" if status == 403 else record.get("error")
    db.execute(
        """INSERT OR IGNORE INTO collection_http_attempts(
           run_id,source_id,target_rank,requested_url,purpose,requested_at,http_status,outcome,retry_after,error_code
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (run_id, source_id, target_rank, record["url"], record["purpose"], at, status,
         outcome, record.get("retry_after"), error_code),
    )
    if status in {403, 429}:
        retry = record.get("retry_after")
        now = local_now()
        until_dt = now + timedelta(hours=24)
        if retry:
            if str(retry).strip().isdigit():
                until_dt = now + timedelta(seconds=min(86_400, int(str(retry).strip())))
            else:
                try:
                    parsed = parsedate_to_datetime(str(retry))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=now.tzinfo)
                    until_dt = min(parsed.astimezone(now.tzinfo), now + timedelta(hours=24))
                except (TypeError, ValueError, OverflowError):
                    pass
        until = until_dt.isoformat(timespec="seconds")
        db.execute("UPDATE collection_sources SET cooldown_until=? WHERE source_id=?", (until, source_id))
    db.commit()


def _promotion_payload(candidate: dict, target: CollectionTarget, source: dict, run_id: str) -> tuple[dict, str]:
    address = candidate["address"]
    evidence = candidate["evidence"]
    reference = f"source-page:{candidate['source_domain']}:{evidence['content_sha256']}"
    raw = {
        "target_rank": target.rank,
        "ward_name": target.current_ward or target.ward,
        "province": target.current_province or target.province,
        "property_type": candidate["property_type"],
        "title": candidate["title"],
        "address": address,
        "price_vnd": candidate["price_vnd"],
        "area_m2": candidate["area_m2"],
        "area_basis": candidate["area_basis"],
        "source_website": candidate["source_domain"],
        "source_url": candidate["source_url"],
        "listed_date": candidate["listed_date"],
        "published_at": candidate["listed_date"],
        "price_evidence": json.dumps(evidence["price"], ensure_ascii=False),
        "area_evidence": json.dumps(evidence["area_m2"], ensure_ascii=False),
        "address_evidence": address,
        "evidence_status": "SOURCE_PAGE_CONFIRMED",
        "_collector_source_page_proof": {
            "retrieved_direct": True,
            "detail_url": canonicalize_source_url(candidate["source_url"]),
            "content_sha256": evidence["content_sha256"],
            "visible_price_match": evidence["price"]["visible"] == evidence["price"]["structured"],
            "visible_area_match": evidence["area_m2"]["visible"] == evidence["area_m2"]["structured"],
            "address_verified": evidence["target_match"],
        },
        "collector_run_id": run_id,
        "collector_source_id": source["source_id"],
    }
    return raw, reference


def plan_collection(db, *, ranks: set[int] | None = None, batch: int | None = None,
                    limit: int = 10) -> dict:
    if batch is not None:
        if batch < 1 or batch > 10:
            raise ValueError("batch must be between 1 and 10")
        batch_ranks = set(range((batch - 1) * 5 + 1, batch * 5 + 1))
        if ranks is not None and ranks != batch_ranks:
            raise ValueError("use either --batch or --ranks, not both")
        ranks = batch_ranks
    if limit < 1 or limit > MAX_TARGET_OBSERVATIONS:
        raise ValueError(f"per-target limit must be between 1 and {MAX_TARGET_OBSERVATIONS}")
    targets = _prioritize_targets(db, collection_targets(db, ranks))
    sources = source_rows(db)
    readiness = source_readiness(db)
    return {
        "status": "DRY_RUN_ONLY",
        "mode": "DRY_RUN",
        "selected": len(targets),
        "target_limit_each": limit,
        "daily_observation_cap": MAX_DAILY_OBSERVATIONS,
        "selection_policy": "lowest_verified_coverage_then_least_recent_attempt",
        "targets": [target.as_public_dict() for target in targets],
        "sources": [_public_source(source) for source in sources],
        "source_readiness": readiness,
        "network_attempted": False,
        "database_written": False,
    }


def run_live_collection(db, *, ranks: set[int] | None = None, batch: int | None = None,
                        limit: int = 10, max_requests: int = MAX_DAILY_OBSERVATIONS,
                        resume: bool = False, source_id: str | None = None,
                        source_ids: set[str] | None = None,
                        allow_auto_ingest: bool = True,
                        transport=None, sleeper=None) -> dict:
    """Execute only after two explicit enable gates, with one host-bound client per source."""
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
    ).fetchone():
        raise RuntimeError("COLLECTION_NOT_INITIALIZED; run `python -m wardprice collection-init` first")
    plan = plan_collection(db, ranks=ranks, batch=batch, limit=limit)
    if max_requests < 1 or max_requests > MAX_DAILY_OBSERVATIONS:
        raise ValueError(f"max_requests must be between 1 and {MAX_DAILY_OBSERVATIONS}")
    targets = collection_targets(db, {item["rank"] for item in plan["targets"]})
    settings = collection_settings(db)
    sources = source_rows(db)
    if source_id:
        sources = [source for source in sources if source["source_id"] == source_id]
    if source_ids is not None:
        sources = [source for source in sources if source["source_id"] in source_ids]
    readiness = source_readiness(db)
    ready_ids = {item["source_id"] for item in readiness["ready_sources"]}
    selected_sources = [source for source in sources if source["source_id"] in ready_ids]
    today = local_now().date().isoformat()

    if not selected_sources:
        run_id = "crawl_blocked_" + local_now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
        reason = "No source has explicit permission, enablement, direct-listing rules and global live authorization."
        db.execute(
            """INSERT INTO collection_runs(run_id,run_date,mode,status,started_at,finished_at,
               selection_json,total_targets,summary_json) VALUES(?,?,'LIVE','BLOCKED_NO_AUTHORIZED_SOURCE',?,?,?,?,?)""",
            (run_id, today, local_now().isoformat(timespec="seconds"), local_now().isoformat(timespec="seconds"),
             json.dumps([target.rank for target in targets]), len(targets), json.dumps({"reason": reason})),
        )
        db.commit()
        return {"status": "BLOCKED_NO_AUTHORIZED_SOURCE", "run_id": run_id, "reason": reason,
                "network_attempted": False, "production_database_written": False,
                "sources": [_public_source(source) for source in sources],
                "target_count": len(targets)}

    run_id, resumed = _begin_run(db, selected_ranks=[target.rank for target in targets], run_date=today, resume=resume)
    counts = {key: 0 for key in (
        "requests_made", "listing_urls_discovered", "candidates_discovered",
        "candidates_inserted", "candidates_updated", "candidates_deduplicated",
        "observations_inserted", "observations_updated", "observations_deduplicated",
        "source_verified", "new_listings", "refreshed_listings", "expired_listings",
        "conflicts", "geo_mismatches", "duplicates", "quarantined", "errors",
    )}
    stop_sources: set[str] = set()
    attempt_summaries: list[dict[str, Any]] = []
    global_prior = int(db.execute(
        "SELECT COUNT(*) FROM collection_http_attempts WHERE substr(requested_at,1,10)=?", (today,)
    ).fetchone()[0])
    global_remaining = min(max_requests, max(0, int(settings["global_daily_request_budget"]) - global_prior))
    shared_budget = {"remaining": global_remaining}
    clients: dict[str, RobotsAwareClient] = {}
    source_runtimes = []

    for source in selected_sources:
        prior = int(db.execute(
            "SELECT COUNT(*) FROM collection_http_attempts WHERE source_id=? AND substr(requested_at,1,10)=?",
            (source["source_id"], today),
        ).fetchone()[0])
        source_remaining = max(0, int(source["daily_request_budget"]) - prior)
        runtime = dict(source)
        runtime["user_agent"] = settings["user_agent"]
        runtime["daily_request_budget"] = min(source_remaining, global_remaining)
        if cooldown_is_active(source.get("cooldown_until")):
            stop_sources.add(source["source_id"])
        source_runtimes.append(runtime)
        clients[source["source_id"]] = RobotsAwareClient(
            runtime,
            transport=transport,
            min_delay_seconds=max(1, float(source["crawl_delay_seconds"])),
            on_attempt=lambda record, sid=source["source_id"]: _log_http(db, run_id, sid, active_rank[0], record),
            shared_budget=shared_budget,
            sleeper=sleeper or time.sleep,
        )

    active_rank: list[int | None] = [None]
    try:
        for source in source_runtimes:
            sid = source["source_id"]
            if sid in stop_sources or shared_budget["remaining"] <= 0:
                counts["errors"] += 1
                continue
            client = clients[sid]
            for target in targets:
                collector = ConfiguredHTMLCollector(source, target, client)
                active_rank[0] = target.rank
                existing_attempt = db.execute(
                    "SELECT status,attempt_count FROM collection_target_attempts WHERE run_id=? AND source_id=? AND target_rank=?",
                    (run_id, sid, target.rank),
                ).fetchone()
                if existing_attempt and existing_attempt["status"] in {"SUCCESS", "NO_LISTINGS", "NO_CANDIDATES", "BLOCKED"}:
                    continue
                if client.requests_made >= source["daily_request_budget"] or shared_budget["remaining"] <= 0:
                    stop_sources.add(sid)
                    break
                attempt_requests = client.requests_made
                attempt_started_at = local_now().isoformat(timespec="seconds")
                found_urls = 0
                saved_candidates = 0
                inserted_candidates = 0
                updated_candidates = 0
                deduplicated_candidates = 0
                inserted_observations = 0
                updated_observations = 0
                deduplicated_observations = 0
                verified_candidates = 0
                duplicates = 0
                quarantined = 0
                error_code = error = retry_after = None
                status = "NO_LISTINGS"
                try:
                    current_listing_count = int(db.execute(
                        """SELECT COUNT(*) FROM collection_candidates WHERE target_rank=?
                           AND substr(last_seen_at,1,10)=?""",
                        (target.rank, today),
                    ).fetchone()[0])
                    observed_today = int(db.execute(
                        "SELECT COUNT(*) FROM collection_candidate_observations WHERE observation_date=?",
                        (today,),
                    ).fetchone()[0]) + int(db.execute(
                        """SELECT COUNT(*) FROM listing_observations WHERE observation_date=?
                           AND source_run_id NOT LIKE 'crawler:%'""",
                        (today,),
                    ).fetchone()[0])
                    for property_type in PROPERTY_TYPES:
                        if current_listing_count >= limit or shared_budget["remaining"] <= 0 or observed_today >= MAX_DAILY_OBSERVATIONS:
                            break
                        urls = collector.discover(target, property_type, limit=200)
                        for item in urls:
                            if not store_discovered_url(db, run_id=run_id, source_id=sid,
                                                        target_rank=target.rank, item=item,
                                                        at=local_now().isoformat(timespec="seconds")):
                                continue
                            found_urls += 1
                            if item.url_type != "DIRECT_LISTING":
                                continue
                            if current_listing_count >= limit or shared_budget["remaining"] <= 0 or observed_today >= MAX_DAILY_OBSERVATIONS:
                                continue
                            try:
                                candidate = collector.extract(item.url)
                            except (TypeError, ValueError, OverflowError) as exc:
                                store_rejection(
                                    db,
                                    run_id=run_id,
                                    source_id=sid,
                                    target_rank=target.rank,
                                    at=local_now().isoformat(timespec="seconds"),
                                    reason=f"EXTRACTION_{type(exc).__name__}: {str(exc)[:300]}",
                                    raw_payload={"source_url": item.url},
                                )
                                quarantined += 1
                                continue
                            candidate["administrative_unit_id"] = target.administrative_unit_id
                            candidate["administrative_code"] = target.administrative_code
                            if target.administrative_unit_id is None:
                                candidate["validity_status"] = "UNMAPPED_TARGET"
                                if candidate["evidence_status"] == "SOURCE_VERIFIED":
                                    candidate["evidence_status"] = "SOURCE_PARTIAL"
                            if not candidate.get("property_type") or not candidate.get("title") or not candidate.get("address"):
                                candidate["validity_status"] = "SOURCE_PARTIAL"
                            stored = store_candidate(db, run_id=run_id, source_id=sid,
                                                     candidate=candidate, at=candidate["collected_at"])
                            if not stored["was_seen_today"]:
                                current_listing_count += 1
                            if stored["observation_inserted"]:
                                observed_today += 1
                            counts["candidates_discovered"] += 1
                            saved_candidates += 1
                            if stored["inserted"]:
                                counts["candidates_inserted"] += 1
                                inserted_candidates += 1
                            if stored["updated"]:
                                counts["candidates_updated"] += 1
                                updated_candidates += 1
                            if stored["deduplicated"]:
                                counts["candidates_deduplicated"] += 1
                                deduplicated_candidates += 1
                            if stored["observation_inserted"]:
                                counts["observations_inserted"] += 1
                                inserted_observations += 1
                            if stored["observation_updated"]:
                                counts["observations_updated"] += 1
                                updated_observations += 1
                            if stored["observation_deduplicated"]:
                                counts["observations_deduplicated"] += 1
                                deduplicated_observations += 1
                            if not stored["inserted"] or stored["possible_duplicate"]:
                                duplicates += 1
                                counts["duplicates"] += 1
                            if stored["possible_duplicate"]:
                                quarantined += 1
                            if candidate["validity_status"] == "GEO_MISMATCH":
                                counts["geo_mismatches"] += 1
                                quarantined += 1
                            if candidate["validity_status"] == "SOURCE_CONFLICT":
                                counts["conflicts"] += 1
                                quarantined += 1
                            if candidate["validity_status"] == "EXPIRED":
                                counts["expired_listings"] += 1
                            if candidate["evidence_status"] == "SOURCE_VERIFIED" and candidate["validity_status"] == "SOURCE_VERIFIED":
                                verified_candidates += 1
                                counts["source_verified"] += 1
                                can_ingest = bool(
                                    allow_auto_ingest
                                    and settings.get("auto_ingest_verified")
                                    and source.get("auto_ingest_verified")
                                    and target.administrative_unit_id
                                    and candidate["area_basis"] in {"LAND_AREA", "FLOOR_AREA", "USABLE_AREA", "OTHER"}
                                    and not stored["possible_duplicate"]
                                )
                                if can_ingest:
                                    raw, ref = _promotion_payload(candidate, target, source, run_id)
                                    from datetime import datetime as DateTime
                                    collected_time = DateTime.fromisoformat(candidate["collected_at"])
                                    result = import_listing_payload(
                                        db, [raw], apply=True, run_id=f"crawler:{run_id}",
                                        verification_reference=ref, collected_at=collected_time,
                                        daily_limit=MAX_DAILY_OBSERVATIONS, source_page_verified=True,
                                    )
                                    if result["verified_candidates"] and not result["quarantined"]:
                                        db.execute("UPDATE collection_candidates SET review_status='PROMOTED' WHERE candidate_id=?",
                                                   (stored["candidate_id"],))
                                        if result["inserted"]:
                                            counts["new_listings"] += 1
                                        if result["updated"]:
                                            counts["refreshed_listings"] += 1
                                        db.commit()

                    status = "SUCCESS" if verified_candidates else "NO_CANDIDATES" if saved_candidates else "NO_LISTINGS"
                except CollectionBlocked as exc:
                    error_code, error, retry_after = exc.code, str(exc), exc.retry_after
                    status = "BLOCKED" if exc.code.startswith("ROBOTS") or exc.code in {"HTTP_403", "HTTP_429", "RETRY_AFTER"} else "ERROR"
                    counts["errors"] += 1
                    if exc.code in {"HTTP_403", "HTTP_429", "ROBOTS_DISALLOW"}:
                        stop_sources.add(sid)
                except Exception as exc:  # noqa: BLE001 - isolate one target and retain committed candidates
                    error_code, error, status = type(exc).__name__, str(exc)[:500], "ERROR"
                    counts["errors"] += 1
                finally:
                    attempt_request_count = client.requests_made - attempt_requests
                    counts["requests_made"] += attempt_request_count
                    counts["listing_urls_discovered"] += found_urls
                    counts["quarantined"] += quarantined
                    attempt_summaries.append({
                        "source_id": sid,
                        "target_rank": target.rank,
                        "status": status,
                        "listing_urls_discovered": found_urls,
                        "candidates_discovered": saved_candidates,
                        "candidates_inserted": inserted_candidates,
                        "candidates_updated": updated_candidates,
                        "candidates_deduplicated": deduplicated_candidates,
                        "observations_inserted": inserted_observations,
                        "observations_updated": updated_observations,
                        "observations_deduplicated": deduplicated_observations,
                        "source_verified": verified_candidates,
                        "duplicates": duplicates,
                        "quarantined": quarantined,
                    })
                    _record_attempt(
                        db, run_id=run_id, source_id=sid, target_rank=target.rank, status=status,
                        request_count=attempt_request_count, discovered_count=found_urls,
                        candidate_count=saved_candidates, verified_count=verified_candidates,
                        duplicate_count=duplicates, quarantine_count=quarantined,
                        error_code=error_code, error=error, retry_after=retry_after,
                        started_at=attempt_started_at,
                        increment=bool(existing_attempt),
                    )
                if sid in stop_sources:
                    break
        processed = int(db.execute(
            "SELECT COUNT(DISTINCT target_rank) FROM collection_target_attempts WHERE run_id=?",
            (run_id,),
        ).fetchone()[0])
        active_attempts = int(db.execute(
            "SELECT COUNT(*) FROM collection_target_attempts WHERE run_id=? AND status IN ('ERROR','BLOCKED')",
            (run_id,),
        ).fetchone()[0])
        run_status = "PARTIAL" if active_attempts or stop_sources or counts["errors"] else "COMPLETED"
        legacy_counts = {**counts, "candidates_found": counts["candidates_inserted"]}
        summary = {
            **legacy_counts,
            "candidate_metric_semantics": {
                "candidates_found": "deprecated alias for candidates_inserted",
                "candidates_discovered": "listing detail pages parsed into candidate records during this run",
                "candidates_inserted": "new unique candidate rows inserted",
                "candidates_updated": "existing candidate rows whose listing facts or evidence changed",
                "candidates_deduplicated": "candidate identities matched an existing row; may overlap with updated",
                "observations_inserted": "new candidate/date observations inserted",
                "observations_updated": "existing candidate/date observation whose measurements changed",
                "observations_deduplicated": "candidate/date observations matched without measurement changes",
            },
            "attempt_metrics": attempt_summaries,
            "resumed": resumed,
            "source_ids": [source["source_id"] for source in selected_sources],
        }
        finished = local_now().isoformat(timespec="seconds")
        db.execute(
            """UPDATE collection_runs SET status=?,finished_at=?,processed_targets=?,requests_made=?,
               candidates_found=?,source_verified=?,new_listings=?,refreshed_listings=?,expired_listings=?,
               conflicts=?,geo_mismatches=?,duplicates=?,quarantined=?,errors=?,summary_json=? WHERE run_id=?""",
            (run_status, finished, processed, counts["requests_made"], counts["candidates_inserted"],
             counts["source_verified"], counts["new_listings"], counts["refreshed_listings"],
             counts["expired_listings"], counts["conflicts"], counts["geo_mismatches"],
             counts["duplicates"], counts["quarantined"], counts["errors"],
             json.dumps(summary, ensure_ascii=False), run_id),
        )
        db.execute(
            """INSERT INTO collection_daily_statistics(
               run_date,latest_run_id,target_count,processed_target_count,requests_made,candidates_found,
               source_verified,new_listings,refreshed_listings,expired_listings,conflicts,geo_mismatches,
               duplicates,quarantined,errors,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(run_date) DO UPDATE SET latest_run_id=excluded.latest_run_id,
               target_count=excluded.target_count,processed_target_count=excluded.processed_target_count,
               requests_made=excluded.requests_made,candidates_found=excluded.candidates_found,
               source_verified=excluded.source_verified,new_listings=excluded.new_listings,
               refreshed_listings=excluded.refreshed_listings,expired_listings=excluded.expired_listings,
               conflicts=excluded.conflicts,geo_mismatches=excluded.geo_mismatches,
               duplicates=excluded.duplicates,quarantined=excluded.quarantined,errors=excluded.errors,
               updated_at=excluded.updated_at""",
            (today, run_id, len(targets), processed, counts["requests_made"], counts["candidates_inserted"],
             counts["source_verified"], counts["new_listings"], counts["refreshed_listings"],
             counts["expired_listings"], counts["conflicts"], counts["geo_mismatches"],
             counts["duplicates"], counts["quarantined"], counts["errors"], finished),
        )
        db.commit()
        return {"status": run_status, "run_id": run_id, **legacy_counts, "processed_targets": processed,
                "selected_targets": len(targets), "resumed": resumed, "network_attempted": counts["requests_made"] > 0,
                "production_database_written": counts["new_listings"] + counts["refreshed_listings"] > 0,
                "source_readiness": readiness}
    except KeyboardInterrupt:
        db.execute("UPDATE collection_runs SET status='INTERRUPTED',finished_at=? WHERE run_id=?",
                   (local_now().isoformat(timespec="seconds"), run_id))
        db.commit()
        raise


def collection_report(db, *, run_date: str | None = None) -> dict:
    return monitoring_summary(db, run_date=run_date)
