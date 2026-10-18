"""Whitelist-bounded collection and refresh of individual real-estate listings."""

import json
import uuid
from datetime import datetime, timezone

from .database import (
    active_wards,
    choose_listing_wards,
    listing_call_count,
    listings_for_ward,
    now_utc,
    record_listing,
    tracked_listing_count,
)
from .validate import normalize_listing


def _identity_exists(db, candidate):
    return db.execute(
        """SELECT 1 FROM listings l WHERE l.identity_key=? OR
           (l.ward_code=? AND l.identity_fingerprint=?) OR EXISTS(
             SELECT 1 FROM listing_sources s WHERE s.listing_id=l.listing_id
               AND s.canonical_url=?
           ) LIMIT 1""",
        (
            candidate["identity_key"],
            candidate["ward_code"],
            candidate["identity_fingerprint"],
            candidate["identity_key"],
        ),
    ).fetchone() is not None


def _reject(db, run_id, ward_code, payload, reason):
    db.execute(
        """INSERT INTO listing_rejections(run_id,ward_code,rejected_at,reason,raw_payload)
           VALUES(?,?,?,?,?)""",
        (
            run_id,
            ward_code,
            now_utc().isoformat(timespec="seconds"),
            str(reason)[:1000],
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )


def _is_http_429_error(exc):
    """Identify rate-limit/quota responses from Gemini SDK errors or their HTTP response."""
    response = getattr(exc, "response", None)
    for value in (
        getattr(exc, "code", None),
        getattr(exc, "status_code", None),
        getattr(response, "status_code", None),
    ):
        try:
            if int(value) == 429:
                return True
        except (TypeError, ValueError):
            continue
    return "429" in str(exc)


def preview_listing_selection(db, settings, selected_ward_codes=None):
    """Return the same whitelist and monthly-cap selection used by a real run, read-only."""
    whitelist = active_wards(db)
    if selected_ward_codes is not None:
        requested = set(selected_ward_codes)
        allowed = {ward.code for ward in whitelist}
        outside = requested - allowed
        if outside:
            raise ValueError(
                f"Ward codes are outside the imported whitelist: {', '.join(sorted(outside))}"
            )
        whitelist = [ward for ward in whitelist if ward.code in requested]

    calls_left = max(0, settings.max_calls_per_month - listing_call_count(db))
    capacity = min(settings.max_wards_per_run, calls_left)
    selected = choose_listing_wards(db, whitelist, limit=capacity)
    return {
        "whitelist": whitelist,
        "selected": selected,
        "calls_left": calls_left,
        "capacity": capacity,
    }


def run_listing_cycle(
    db,
    settings,
    researcher,
    *,
    selected_ward_codes=None,
    logger=print,
    progress_callback=None,
):
    """Search eligible whitelist wards once each, update tracked listings, and enforce caps."""
    def publish(stage, message, *, progress=None, ward_code=None, current=None, total=None):
        event = {
            "stage": stage,
            "message": message,
            "progress": progress,
            "ward_code": ward_code,
            "current": current,
            "total": total,
        }
        if progress_callback is not None:
            progress_callback(event)
        if logger is not None:
            logger(f"[{stage}] {message}")

    selection = preview_listing_selection(db, settings, selected_ward_codes)
    whitelist = selection["whitelist"]
    publish("preflight", f"Loaded {len(whitelist)} active whitelist wards", progress=0.02)
    calls_left = selection["calls_left"]
    selected = selection["selected"]
    publish(
        "selection",
        f"Selected {len(selected)} ward(s); {calls_left} monthly prompt slot(s) remain",
        progress=0.1 if selected else 1.0,
        total=len(selected),
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
    started = now_utc().isoformat(timespec="seconds")
    db.execute("INSERT INTO run_log(run_id,started_at) VALUES(?,?)", (run_id, started))
    db.commit()
    totals = {
        "run_id": run_id,
        "whitelist_wards": len(whitelist),
        "selected": len(selected),
        "inserted": 0,
        "updated": 0,
        "rejected": 0,
        "limit_skipped": 0,
        "no_listings": 0,
        "failed": 0,
        "search_queries": 0,
        "stopped_after_429": False,
        "not_attempted": 0,
    }

    for index, ward in enumerate(selected, start=1):
        location = ", ".join(
            part for part in (ward.name, ward.district, ward.province) if part
        )
        ward_progress = (index - 1) / max(1, len(selected))
        publish(
            "ward",
            f"[{index}/{len(selected)}] Starting {location}",
            progress=0.1 + ward_progress * 0.9,
            ward_code=ward.code,
            current=index - 1,
            total=len(selected),
        )
        started_at = now_utc().isoformat(timespec="seconds")
        search_id = db.execute(
            """INSERT INTO listing_search_runs(run_id,ward_code,started_at,status)
               VALUES(?,?,?,'RUNNING')""",
            (run_id, ward.code, started_at),
        ).lastrowid
        db.commit()
        accepted = updated = rejected = limit_skipped = 0
        grounding_used = False
        queries = 0
        usage = {}
        error = None
        status = "NO_LISTINGS"
        rate_limited = False
        try:
            tracked = listings_for_ward(db, ward.code)
            new_capacity = min(
                settings.max_new_listings_per_ward,
                max(0, settings.max_total_listings - tracked_listing_count(db)),
            )
            publish(
                "refresh",
                f"Found {len(tracked)} tracked listing(s); up to {new_capacity} new listing(s) can be added",
                progress=0.1 + (ward_progress + 0.2 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )
            publish(
                "gemini",
                "Sending listing-search prompt with Google Search grounding",
                progress=0.1 + (ward_progress + 0.35 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )
            payload, grounded_urls, usage = researcher.research_listings(
                ward, tracked, max_new_listings=new_capacity
            )
            grounding_used = bool(usage.get("grounding_used") or grounded_urls)
            queries = int(usage.get("search_queries") or 0)
            candidates = payload.get("listings") if isinstance(payload, dict) else None
            if not isinstance(candidates, list):
                raise TypeError("Gemini response must contain a listings array")
            if len(candidates) > 50:
                raise ValueError("response exceeded the 50-listing safety bound")
            publish(
                "response",
                f"Received {len(candidates)} candidate(s), {queries} Search query/queries, grounding={grounding_used}",
                progress=0.1 + (ward_progress + 0.62 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )
            publish(
                "validate",
                "Checking whitelist, evidence, fields, and duplicates",
                progress=0.1 + (ward_progress + 0.72 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )
            new_count = 0
            for raw in candidates:
                try:
                    candidate = normalize_listing(raw, ward, grounded_urls=grounded_urls)
                    exists = _identity_exists(db, candidate)
                    if not exists and new_count >= new_capacity:
                        limit_skipped += 1
                        _reject(db, run_id, ward.code, raw, "per-ward new-listing limit reached")
                        continue
                    outcome = record_listing(
                        db,
                        candidate,
                        run_id,
                        max_total=settings.max_total_listings,
                    )
                    if outcome == "LIMIT_REACHED":
                        limit_skipped += 1
                    elif outcome == "WARD_CONFLICT":
                        rejected += 1
                        _reject(db, run_id, ward.code, raw, "source URL already belongs to another ward")
                    elif outcome == "INSERTED":
                        accepted += 1
                        new_count += 1
                    elif outcome == "UPDATED":
                        updated += 1
                except (TypeError, ValueError) as exc:
                    rejected += 1
                    _reject(db, run_id, ward.code, raw, exc)
            db.commit()
            if accepted or updated:
                status = "SUCCESS"
            elif rejected:
                status = "REJECTED"
            elif not grounding_used:
                status = "NO_GROUNDING"
            else:
                status = "NO_LISTINGS"
            publish(
                "database",
                f"Saved {accepted} new, refreshed {updated}, rejected {rejected}, skipped by cap {limit_skipped}",
                progress=0.1 + (ward_progress + 0.9 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )
        except Exception as exc:  # noqa: BLE001 - record one ward error and keep the daily batch alive
            rate_limited = _is_http_429_error(exc)
            error = str(exc)
            if settings.api_key:
                error = error.replace(settings.api_key, "[redacted]")
            error = error[:1000]
            status = "ERROR"
            publish(
                "rate_limited" if rate_limited else "error",
                (
                    f"Gemini returned HTTP 429; remaining ward requests will be stopped. {error[:160]}"
                    if rate_limited
                    else f"Ward failed: {error[:200]}"
                ),
                progress=0.1
                + (ward_progress + 0.48 / max(1, len(selected))) * 0.9,
                ward_code=ward.code,
                current=index - 1,
                total=len(selected),
            )

        finished_at = now_utc().isoformat(timespec="seconds")
        db.execute(
            """UPDATE listing_search_runs SET finished_at=?,status=?,accepted_count=?,
               updated_count=?,rejected_count=?,limit_skipped_count=?,grounding_used=?,
               search_queries=?,prompt_tokens=?,output_tokens=?,error=? WHERE id=?""",
            (
                finished_at,
                status,
                accepted,
                updated,
                rejected,
                limit_skipped,
                int(grounding_used),
                queries,
                usage.get("prompt_tokens"),
                usage.get("output_tokens"),
                error,
                search_id,
            ),
        )
        db.execute(
            "UPDATE ward_registry SET last_search_at=? WHERE ward_code=?",
            (finished_at, ward.code),
        )
        db.commit()
        publish(
            "ward_complete",
            f"Ward finished with status {status}",
            progress=0.1 + (index / max(1, len(selected))) * 0.9,
            ward_code=ward.code,
            current=index,
            total=len(selected),
        )
        totals["inserted"] += accepted
        totals["updated"] += updated
        totals["rejected"] += rejected
        totals["limit_skipped"] += limit_skipped
        totals["search_queries"] += queries
        if status == "NO_LISTINGS":
            totals["no_listings"] += 1
        elif status == "ERROR":
            totals["failed"] += 1
        if rate_limited:
            totals["stopped_after_429"] = True
            pending = selected[index:]
            totals["not_attempted"] += len(pending)
            for pending_index, pending_ward in enumerate(pending, start=index + 1):
                publish(
                    "not_attempted",
                    f"[{pending_index}/{len(selected)}] Not sent after the HTTP 429 response",
                    progress=0.1 + (pending_index / max(1, len(selected))) * 0.9,
                    ward_code=pending_ward.code,
                    current=pending_index - 1,
                    total=len(selected),
                )
            break

    totals["tracked_listings"] = tracked_listing_count(db)
    totals["api_calls_this_month"] = listing_call_count(db)
    totals["api_calls_remaining_this_month"] = max(
        0, settings.max_calls_per_month - totals["api_calls_this_month"]
    )
    finished = now_utc().isoformat(timespec="seconds")
    db.execute(
        """UPDATE run_log SET finished_at=?,attempted=?,accepted=?,no_data=?,failed=?,details=?
           WHERE run_id=?""",
        (
            finished,
            len(selected) - totals["not_attempted"],
            totals["inserted"] + totals["updated"],
            totals["no_listings"],
            totals["failed"],
            json.dumps(totals, ensure_ascii=False),
            run_id,
        ),
    )
    db.commit()
    message = (
        f"Run complete: {totals['inserted']} new, {totals['updated']} refreshed, "
        f"{totals['rejected']} rejected; {totals['tracked_listings']}/{settings.max_total_listings} tracked"
    )
    if totals["stopped_after_429"]:
        message += f"; stopped after HTTP 429, {totals['not_attempted']} ward(s) not attempted"
    publish(
        "run_complete",
        message,
        progress=1.0,
        current=len(selected),
        total=len(selected),
    )
    return totals
