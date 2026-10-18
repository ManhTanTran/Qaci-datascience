"""CLI for the optional, offline-first Gemini Web pilot."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .candidate_batch import (
    apply_batch,
    assert_isolated_audit_database,
    backup_before_candidate_schema,
    open_existing_readonly,
    prepare_batch,
    preview_against_database,
)
from .candidate_batch import (
    ensure_schema as ensure_candidate_batch_schema,
)
from .core import (
    connect,
    export,
    import_response,
    load_targets,
    make_prompt,
    plan_slot,
    process_response_for_run,
    start_run,
    status,
)
from .research import (
    analyze_research_document,
    fail_research_run,
    initialize_research_schema,
    make_deep_research_prompt,
    research_status,
    save_research_result,
    serialize_sources,
    start_research_run,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_AUDIT_DB = PROJECT_ROOT / "state" / "wardprice_webpilot.sqlite3"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "webpilot"
DEFAULT_INBOX = PROJECT_ROOT / "inbox" / "webpilot"
DEFAULT_MAX_DAILY_CALLS = 3
HARD_MAX_DAILY_CALLS = 3


def _print(data: Any) -> None:
    # PowerShell may launch Python with a legacy code page that cannot print
    # Vietnamese. Force UTF-8 for the structured output and keep a safe fallback.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _today_in_vietnam() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def _safe_error(error: Exception) -> str:
    message = str(error)
    for name in ("GEMINI_SECURE_1PSID", "GEMINI_SECURE_1PSIDTS"):
        secret = os.environ.get(name)
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:1000]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WardPriceDaily Gemini Web pilot")
    parser.add_argument("--targets-db", type=Path, default=DEFAULT_TARGETS_DB)
    parser.add_argument("--db", type=Path, default=DEFAULT_AUDIT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    subs = parser.add_subparsers(dest="cmd", required=True)

    subs.add_parser("doctor", help="Check local prerequisites; never uses the network")
    plan = subs.add_parser("plan", help="Preview the 10-day target rotation")
    plan.add_argument("--slot", type=int, choices=range(1, 6), required=True)
    plan.add_argument("--date", type=date.fromisoformat)
    plan.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 10, 13))

    imported = subs.add_parser("import-json", help="Audit a saved JSON response offline")
    imported.add_argument("--file", type=Path, required=True)

    batch_import = subs.add_parser(
        "import-batch",
        help="Preview or import a saved Gemini JSON batch into the isolated candidate warehouse",
    )
    batch_import.add_argument("--file", type=Path, required=True)
    batch_import.add_argument("--rank", type=int, choices=range(1, 51), dest="expected_rank")
    batch_mode = batch_import.add_mutually_exclusive_group()
    batch_mode.add_argument(
        "--apply", action="store_true", help="Write after the dry-run is reviewed"
    )
    batch_mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")

    collect = subs.add_parser("collect", help="Prompt preview by default; live calls are opt-in")
    collect.add_argument("--rank", type=int, choices=range(1, 51))
    collect.add_argument("--slot", type=int, choices=range(1, 6))
    collect.add_argument("--date", type=date.fromisoformat)
    collect.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 10, 13))
    collect.add_argument("--count", type=int, default=5)
    collect.add_argument("--model", type=str)
    collect.add_argument("--live", action="store_true", help="Attempt one Gemini Web request")
    collect.add_argument(
        "--confirm-single-live-call",
        action="store_true",
        help="Confirm permission for exactly one non-retried account request in this invocation",
    )
    collect.add_argument(
        "--max-daily-calls",
        type=int,
        choices=range(1, HARD_MAX_DAILY_CALLS + 1),
        default=DEFAULT_MAX_DAILY_CALLS,
        help="Local daily safety cap (1..3); cannot raise the provider/account quota",
    )
    collect.add_argument("--target-total", type=int, default=500)
    collect.add_argument("--save-to-inbox", type=Path, default=DEFAULT_INBOX)

    research = subs.add_parser(
        "research",
        help="Deep Research pilot; dry-run by default, live requires separate confirmation",
    )
    research.add_argument("--rank", type=int, choices=range(1, 51), required=True)
    research.add_argument("--count", type=int, choices=range(1, 6), default=5)
    research.add_argument("--model", type=str)
    research.add_argument("--poll-interval", type=float, default=10.0)
    research.add_argument("--timeout", type=float, default=600.0)
    research.add_argument("--live", action="store_true", help="Start one Deep Research workflow")
    research.add_argument(
        "--confirm-single-live-deep-research",
        action="store_true",
        help="Confirm account permission for one Deep Research workflow today",
    )
    research.add_argument("--save-to-inbox", type=Path, default=DEFAULT_INBOX / "deep_research")

    research_import = subs.add_parser(
        "research-import",
        help="Parse a saved report offline into the sidecar audit database",
    )
    research_import.add_argument("--rank", type=int, choices=range(1, 51), required=True)
    research_import.add_argument("--count", type=int, choices=range(1, 6), default=5)
    research_import.add_argument(
        "--file", type=Path, required=True, help="Raw report Markdown/text"
    )
    research_import.add_argument(
        "--sources-file", type=Path, required=True, help="JSON citation array"
    )
    research_import.add_argument(
        "--source-text-json",
        type=Path,
        help="Optional permitted page text map keyed by citation ID; no network retrieval",
    )

    subs.add_parser("research-status", help="Show Deep Research sidecar audit runs")

    subs.add_parser("status", help="Show sidecar candidate counts")
    subs.add_parser("export", help="Export audit candidates without unverified aggregates")
    return parser


def _rank_and_prompt(
    args: argparse.Namespace, targets: dict[int, dict[str, str]]
) -> tuple[int, str]:
    if (args.rank is None) == (args.slot is None):
        raise ValueError("Provide exactly one of --rank or --slot")
    day = args.date or _today_in_vietnam()
    rank = args.rank if args.rank is not None else plan_slot(args.start_date, day, args.slot)
    if not 1 <= args.count <= 50:
        raise ValueError("--count must be 1..50")
    return rank, make_prompt(targets[rank], args.count)


def _doctor(targets_db: Path) -> None:
    dependency_available = importlib.util.find_spec("gemini_webapi") is not None
    deep_research_methods: dict[str, bool] = {}
    if dependency_available:
        try:
            from gemini_webapi import GeminiClient

            deep_research_methods = {
                name: callable(getattr(GeminiClient, name, None))
                for name in (
                    "deep_research",
                    "create_deep_research_plan",
                    "start_deep_research",
                    "wait_for_deep_research",
                )
            }
        except (ImportError, OSError):
            deep_research_methods = {}
    try:
        targets = load_targets(targets_db)
        target_status = {"available": True, "count": len(targets)}
    except (FileNotFoundError, ValueError):
        target_status = {"available": False, "count": 0}
    _print(
        {
            "python": sys.version.split()[0],
            "gemini_webapi_installed": dependency_available,
            "deep_research_api_available": bool(deep_research_methods)
            and all(deep_research_methods.values()),
            "deep_research_methods": deep_research_methods,
            # Presence only: never read, display, or log either secret.
            "local_web_session_available": bool(os.environ.get("GEMINI_SECURE_1PSID")),
            "target_registry": target_status,
            "target_database": str(targets_db),
            "network_attempted": False,
            "production_database_written": False,
            "warning": "Unofficial adapter; Gemini Web policies and account permissions apply.",
        }
    )


def _ensure_sidecar_database(targets_db: Path, audit_db: Path) -> None:
    if targets_db.resolve() == audit_db.resolve():
        raise ValueError(
            "Refusing to write Deep Research audit into the target/production database"
        )


def _check_deep_research_prerequisites() -> None:
    if not os.environ.get("GEMINI_SECURE_1PSID"):
        raise ValueError("Missing local GEMINI_SECURE_1PSID; no web request made")
    if importlib.util.find_spec("gemini_webapi") is None:
        raise ValueError("Optional gemini_webapi package is not installed; no web request made")
    try:
        from gemini_webapi import GeminiClient
    except (ImportError, OSError) as exc:
        raise ValueError(f"Could not load gemini_webapi; no web request made: {exc}") from None
    required = (
        "start_chat",
        "create_deep_research_plan",
        "start_deep_research",
        "wait_for_deep_research",
    )
    missing = [name for name in required if not callable(getattr(GeminiClient, name, None))]
    if missing:
        raise ValueError(
            "Installed gemini_webapi does not expose required Deep Research methods; "
            "no web request made: " + ", ".join(missing)
        )


def _deep_research_files(
    directory: Path,
    rank: int,
    run_id: int,
    document_text: str,
    sources: list[dict[str, Any]],
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    stem = f"deep_research_rank{rank:02d}_run{run_id}_{stamp}"
    raw_path = directory / f"{stem}.md"
    sources_path = directory / f"{stem}.sources.json"
    raw_path.write_text(document_text, encoding="utf-8")
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw_path, sources_path


def _live_research(
    args: argparse.Namespace,
    target: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    _ensure_sidecar_database(args.targets_db, args.db)
    _check_deep_research_prerequisites()
    if args.poll_interval <= 0 or args.timeout <= 0 or args.timeout > 1800:
        raise ValueError("--poll-interval must be positive and --timeout must be 1..1800 seconds")

    from zoneinfo import ZoneInfo

    usage_day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    db = connect(args.db)
    try:
        initialize_research_schema(db)
        db.execute("BEGIN IMMEDIATE")
        daily_workflows = db.execute(
            """SELECT COUNT(*) FROM webpilot_research_runs
               WHERE status LIKE 'LIVE_%' AND occurred_at LIKE ?""",
            (usage_day + "%",),
        ).fetchone()[0]
        if daily_workflows >= 1:
            db.rollback()
            raise ValueError(
                f"Deep Research daily workflow cap reached ({daily_workflows}/1 for {usage_day}); "
                "no web request made"
            )
        run_id = start_research_run(
            db,
            target_rank=args.rank,
            requested_count=args.count,
            prompt_text=prompt,
        )
        prompt_path = args.save_to_inbox / "latest_deep_research_prompt.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")

        try:
            from .research_webclient import run_deep_research

            live_result = asyncio.run(
                run_deep_research(
                    prompt,
                    model=args.model,
                    poll_interval=args.poll_interval,
                    timeout=args.timeout,
                )
            )
        except Exception as exc:  # noqa: BLE001 - preserve a single failed pilot attempt
            error_text = _safe_error(exc)
            fail_research_run(db, run_id, error_text)
            raise RuntimeError(f"Deep Research workflow failed: {error_text}") from None

        document_text = str(live_result.get("document_text") or "")
        raw_sources = live_result.get("sources") or []
        normalized_sources = serialize_sources(raw_sources)
        analysis = analyze_research_document(
            document_text,
            raw_sources,
            target,
            requested_count=args.count,
        )
        document_present = bool(document_text.strip())
        status_value = "LIVE_COMPLETE" if document_present else "LIVE_NO_DOCUMENT"
        try:
            raw_path, sources_path = _deep_research_files(
                args.save_to_inbox,
                args.rank,
                run_id,
                document_text,
                raw_sources,
            )
        except OSError as exc:
            raw_path, sources_path = None, None
            file_error = f"Could not save report artifact: {exc}"
        else:
            file_error = None

        save_research_result(
            db,
            run_id,
            status=status_value,
            web_search_status=analysis["web_search_status"],
            analysis=analysis,
            plan=live_result.get("plan"),
            document_id=live_result.get("document_id"),
            document_title=live_result.get("document_title"),
            raw_document_text=document_text,
            result_metadata={
                "done": bool(live_result.get("done")),
                "workflow": "plan_start_poll",
                "internal_wrapper_retries_controlled_by_library": True,
                "network_attempted": True,
                "source_text_independently_retrieved": False,
            },
            raw_document_path=str(raw_path) if raw_path else None,
            sources_path=str(sources_path) if sources_path else None,
            error_text=file_error,
        )
        return {
            "run_id": run_id,
            "status": status_value,
            "target": target,
            "requested_count": args.count,
            "document_received": document_present,
            "source_count": len(normalized_sources),
            "source_kind_counts": analysis["source_kind_counts"],
            "candidate_count": analysis["candidate_count"],
            "invalid_candidate_count": analysis["invalid_candidate_count"],
            "candidate_evidence_counts": analysis["candidate_evidence_counts"],
            "source_verified_count": analysis["source_verified_count"],
            "sources": normalized_sources,
            "raw_document_file": str(raw_path) if raw_path else None,
            "sources_file": str(sources_path) if sources_path else None,
            "file_error": file_error,
            "network_attempted": True,
            "production_database_written": False,
            "source_pages_independently_retrieved": False,
            "source_verified_requires_independent_page_text": True,
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        _doctor(args.targets_db)
        return 0

    targets = load_targets(args.targets_db)
    if args.cmd == "plan":
        day = args.date or _today_in_vietnam()
        rank = plan_slot(args.start_date, day, args.slot)
        _print({"date": day.isoformat(), "target": targets[rank], "dry_run": True})
        return 0

    if args.cmd == "import-batch":
        raw_text = args.file.read_text(encoding="utf-8-sig")
        prepared = prepare_batch(raw_text, targets, expected_rank=args.expected_rank)
        existing_db = open_existing_readonly(args.db)
        try:
            preview = preview_against_database(prepared, existing_db)
        finally:
            if existing_db is not None:
                existing_db.close()

        if not args.apply:
            _print(
                {
                    "status": "DRY_RUN",
                    "source_file": str(args.file.resolve()),
                    "batch_sha256": preview["batch_sha256"],
                    "target": preview["target"],
                    "run_date": preview["run_date"],
                    "target_count": preview["target_count"],
                    "actual_collected": preview["actual_collected"],
                    "received": preview["received"],
                    "accepted": preview["accepted_count"],
                    "quarantined": preview["quarantined_count"],
                    "duplicates": preview["duplicate_count"],
                    "rejected": preview["rejected_count"],
                    "source_url_type_counts": preview["source_url_type_counts"],
                    "evidence_status_counts": preview["evidence_status_counts"],
                    "review_status_counts": preview["review_status_counts"],
                    "records": [
                        {
                            "row": row["row_index"],
                            "title": row.get("title"),
                            "disposition": row["disposition"],
                            "reason": row.get("reason"),
                            "source_url_type": row.get("source_url_type"),
                            "evidence_status": row.get("evidence_status"),
                            "review_status": row.get("review_status"),
                        }
                        for row in preview["rows"]
                    ],
                    "statistics_eligible_count": 0,
                    "network_attempted": False,
                    "production_database_written": False,
                    "demo_database_written": False,
                }
            )
            return 0

        _ensure_sidecar_database(args.targets_db, args.db)
        assert_isolated_audit_database(args.db, args.targets_db)
        backup_file = backup_before_candidate_schema(args.db)
        db = connect(args.db)
        try:
            ensure_candidate_batch_schema(db)
            result = apply_batch(db, prepared, source_file=str(args.file.resolve()))
            result["backup_file"] = str(backup_file) if backup_file else None
            result["statistics_eligible_count"] = 0
            result["network_attempted"] = False
            result["production_database_written"] = False
            result["demo_database_written"] = False
            # Raw source bytes and per-row payloads are retained in SQLite, not printed.
            result.pop("raw_batch_json", None)
            result.pop("batch_metadata", None)
            result.pop("batch_warnings", None)
            result.pop("rows", None)
            _print(result)
            return 0
        finally:
            db.close()

    if args.cmd == "collect":
        rank, prompt = _rank_and_prompt(args, targets)
        if not args.live:
            _print(
                {
                    "status": "DRY_RUN_ONLY",
                    "target": targets[rank],
                    "requested_count": args.count,
                    "prompt": prompt,
                    "network_attempted": False,
                    "database_written": False,
                }
            )
            return 0
        if not args.confirm_single_live_call:
            raise ValueError(
                "Live request blocked: add --confirm-single-live-call after reviewing consent"
            )
        if not os.environ.get("GEMINI_SECURE_1PSID"):
            raise ValueError("Missing local GEMINI_SECURE_1PSID; no web request made")
        if importlib.util.find_spec("gemini_webapi") is None:
            raise ValueError("Optional gemini_webapi package is not installed; no web request made")
        db = connect(args.db)
        try:
            count = db.execute("SELECT COUNT(*) FROM webpilot_candidates").fetchone()[0]
            if count >= args.target_total:
                raise ValueError("Candidate cap reached; no web request made")
            usage_day = _today_in_vietnam()
            # Serialize quota check + reservation so concurrent CLI processes
            # cannot each observe the same remaining daily slot.
            db.execute("BEGIN IMMEDIATE")
            try:
                daily_attempts = db.execute(
                    """SELECT COUNT(*) FROM webpilot_runs
                       WHERE origin='gemini_web_attempt' AND date(occurred_at,'+7 hours')=?""",
                    (usage_day.isoformat(),),
                ).fetchone()[0]
                if daily_attempts >= args.max_daily_calls:
                    db.rollback()
                    raise ValueError(
                        f"Daily live call cap reached ({daily_attempts}/{args.max_daily_calls}); "
                        "no web request made"
                    )

                prompt_file = args.save_to_inbox / "latest_live_prompt.txt"
                args.save_to_inbox.mkdir(parents=True, exist_ok=True)
                prompt_file.write_text(prompt, encoding="utf-8")
                run_id = start_run(
                    db,
                    origin="gemini_web_attempt",
                    requested_rank=rank,
                    prompt_text=prompt,
                    request_metadata={
                        "model": args.model,
                        "requested_count": args.count,
                        "adapter": "gemini_webapi",
                        "retry_policy": "none",
                        "daily_call_cap": args.max_daily_calls,
                        "daily_call_number": daily_attempts + 1,
                        "usage_day_vietnam": usage_day.isoformat(),
                        "prompt_file": str(prompt_file),
                    },
                )
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
            try:
                from .webclient import collect_from_web

                raw_text, citations = asyncio.run(collect_from_web(prompt, model=args.model))
            except Exception as exc:  # noqa: BLE001 - audit and report one failed live attempt
                with db:
                    db.execute(
                        "UPDATE webpilot_runs SET status='FAILED',result_json=? WHERE run_id=?",
                        (json.dumps({"error": _safe_error(exc)}, ensure_ascii=False), run_id),
                    )
                raise RuntimeError(f"Gemini Web call failed: {_safe_error(exc)}") from None

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            raw_file = args.save_to_inbox / f"gemini_web_rank{rank:02d}_{stamp}.txt"
            raw_file.write_text(raw_text, encoding="utf-8")
            with db:
                db.execute(
                    """UPDATE webpilot_runs SET status='RECEIVED',raw_response_text=?,
                       citation_count=?,citations_json=? WHERE run_id=?""",
                    (
                        raw_text,
                        len(citations),
                        json.dumps(citations, ensure_ascii=False),
                        run_id,
                    ),
                )
            result = process_response_for_run(
                db,
                run_id,
                raw_text,
                targets,
                requested_rank=rank,
                citations=citations,
            )
            result["raw_response_file"] = str(raw_file)
            result["prompt_file"] = str(prompt_file)
            result["network_attempted"] = True
            _print(result)
            return 0
        finally:
            db.close()

    if args.cmd == "research":
        target = targets[args.rank]
        prompt = make_deep_research_prompt(target, args.count)
        if not args.live:
            _print(
                {
                    "status": "DRY_RUN_ONLY",
                    "target": target,
                    "requested_count": args.count,
                    "prompt": prompt,
                    "network_attempted": False,
                    "database_written": False,
                    "production_database_written": False,
                }
            )
            return 0
        if not args.confirm_single_live_deep_research:
            raise ValueError(
                "Deep Research blocked: add --confirm-single-live-deep-research only "
                "after reviewing account permission and consent"
            )
        _print(_live_research(args, target, prompt))
        return 0

    if args.cmd == "research-import":
        _ensure_sidecar_database(args.targets_db, args.db)
        target = targets[args.rank]
        report_text = args.file.read_text(encoding="utf-8-sig")
        sources = json.loads(args.sources_file.read_text(encoding="utf-8-sig"))
        if not isinstance(sources, list):
            raise ValueError("--sources-file must contain a JSON array")
        source_text_by_id: dict[str, str] = {}
        if args.source_text_json:
            loaded_source_text = json.loads(args.source_text_json.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded_source_text, dict):
                raise ValueError("--source-text-json must be a JSON object keyed by citation ID")
            source_text_by_id = {
                str(key): value
                for key, value in loaded_source_text.items()
                if isinstance(value, str)
            }
        analysis = analyze_research_document(
            report_text,
            sources,
            target,
            source_text_by_id=source_text_by_id,
            requested_count=args.count,
        )
        prompt = make_deep_research_prompt(target, args.count)
        db = connect(args.db)
        try:
            initialize_research_schema(db)
            run_id = start_research_run(
                db,
                target_rank=args.rank,
                requested_count=args.count,
                prompt_text=prompt,
                status="OFFLINE_IMPORTED",
            )
            save_research_result(
                db,
                run_id,
                status="OFFLINE_IMPORTED",
                web_search_status=analysis["web_search_status"],
                analysis=analysis,
                plan=None,
                document_id=None,
                document_title=None,
                raw_document_text=report_text,
                result_metadata={
                    "network_attempted": False,
                    "source_text_file": str(args.source_text_json)
                    if args.source_text_json
                    else None,
                    "source_text_independently_retrieved": bool(source_text_by_id),
                    "input_file": str(args.file),
                    "sources_file": str(args.sources_file),
                },
                raw_document_path=str(args.file.resolve()),
                sources_path=str(args.sources_file.resolve()),
            )
            _print(
                {
                    "run_id": run_id,
                    "status": "OFFLINE_IMPORTED",
                    "target": target,
                    "source_count": analysis["source_count"],
                    "source_kind_counts": analysis["source_kind_counts"],
                    "candidate_count": analysis["candidate_count"],
                    "invalid_candidate_count": analysis["invalid_candidate_count"],
                    "candidate_evidence_counts": analysis["candidate_evidence_counts"],
                    "source_verified_count": analysis["source_verified_count"],
                    "report_parse_status": analysis["report_parse_status"],
                    "network_attempted": False,
                    "production_database_written": False,
                }
            )
            return 0
        finally:
            db.close()

    db = connect(args.db)
    try:
        if args.cmd == "research-status":
            initialize_research_schema(db)
            _print(research_status(db))
            return 0
        if args.cmd == "status":
            _print(status(db))
            return 0
        if args.cmd == "export":
            _print(export(db, args.output))
            return 0
        if args.cmd == "import-json":
            raw_text = args.file.read_text(encoding="utf-8-sig")
            result = import_response(
                db,
                raw_text,
                targets,
                origin=str(args.file),
                request_metadata={"source_file": str(args.file)},
            )
            _print(result)
            return 0
        parser.error("Unknown command")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
        raise SystemExit(1) from None
