"""Legacy ward-aggregate cycle, retained for old valuation data and compatibility tests."""

import uuid
from datetime import datetime, timezone

from .database import choose_wards, log_attempt, month_call_count, now_utc, save_results, stats
from .validate import normalize_result


def run_cycle(db, registry, settings, researcher, logger=print):
    """Legacy flow with a 500-ward cap; the CLI now runs listing_pipeline.run_listing_cycle."""
    remaining_calls = max(0, settings.max_calls_per_month - month_call_count(db))
    capacity = min(settings.max_wards_per_run, remaining_calls)
    selected = choose_wards(
        db,
        registry,
        limit=capacity,
        target=settings.max_total_wards,
        refresh_days=settings.refresh_days,
        retry_days=settings.retry_days,
        max_attempts=settings.max_attempts_per_ward,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
    db.execute(
        "INSERT INTO run_log(run_id,started_at) VALUES(?,?)",
        (run_id, now_utc().isoformat(timespec="seconds")),
    )
    db.commit()
    totals = {
        "run_id": run_id,
        "selected": len(selected),
        "accepted_rows": 0,
        "successful_wards": 0,
        "no_data": 0,
        "failed": 0,
    }
    for idx, ward in enumerate(selected, 1):
        logger(f"[{idx}/{len(selected)}] {ward.name}, {ward.province}")
        try:
            payload, grounded, usage = researcher.research(ward)
            if settings.require_search and not grounded:
                raise ValueError("no observed Google Search grounding (REQUIRE_SEARCH=true)")
            raws = payload.get("results") or []
            if len(raws) > 3:
                raise ValueError("more than three property types")
            normalized = [
                normalize_result(item, ward, grounding_used=grounded, model=settings.model)
                for item in raws
            ]
            if len({item["property_type"] for item in normalized}) != len(normalized):
                raise ValueError("duplicate property_type for same ward")
            save_results(db, run_id, normalized)
            log_attempt(
                db,
                run_id,
                ward.code,
                "SUCCESS" if normalized else "NO_DATA",
                grounding_used=grounded,
                usage=usage,
            )
            if normalized:
                totals["successful_wards"] += 1
                totals["accepted_rows"] += len(normalized)
            else:
                totals["no_data"] += 1
        except Exception as exc:  # noqa: BLE001 - record this ward failure and continue the batch
            log_attempt(db, run_id, ward.code, "ERROR", str(exc))
            totals["failed"] += 1
            logger(f"  ERROR: {str(exc)[:200]}")
    db.execute(
        """UPDATE run_log SET finished_at=?,attempted=?,accepted=?,no_data=?,failed=?,details=? WHERE run_id=?""",
        (
            now_utc().isoformat(timespec="seconds"),
            len(selected),
            totals["accepted_rows"],
            totals["no_data"],
            totals["failed"],
            str(totals),
            run_id,
        ),
    )
    db.commit()
    totals["cumulative"] = stats(db)
    return totals
