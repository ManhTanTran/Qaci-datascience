"""Command-line entry point for the listing-based WardPriceDaily pipeline."""

import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .database import (
    active_wards,
    backup_database_before_collection_migration,
    choose_listing_wards,
    connect,
    legacy_target_rows,
    listing_call_count,
    listing_rows,
    listing_statistics,
    stats,
    tracked_listing_count,
)
from .database import (
    import_legacy_targets as save_legacy_targets,
)
from .database import (
    import_wards as save_ward_whitelist,
)
from .gemini import GeminiResearcher
from .listing_pipeline import run_listing_cycle
from .mailer import dry_run_report, send_report
from .registry import load_ward_whitelist
from .reports import export
from .target_registry import load_legacy_targets, target_summary

DEFAULT_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs"
DEFAULT_WARDS = PROJECT_ROOT / "config" / "wards.csv"
DEFAULT_SOURCE_REGISTRY = PROJECT_ROOT / "config" / "collector_sources.json"
COLLECTION_COMMANDS = {
    "collection-init",
    "collection-sources",
    "collect-daily",
    "collection-status",
    "collection-report",
}


def _parse_codes(value):
    if not value:
        return None
    codes = [part.strip() for part in value.split(",") if part.strip()]
    if not codes:
        raise ValueError("--wards must contain one or more comma-separated ward codes")
    return codes


def _common_options(parser):
    parser.add_argument("--registry", default=DEFAULT_WARDS, type=Path)
    parser.add_argument("--db", default=None, type=Path)
    parser.add_argument("--output", default=None, type=Path)


def _print_gemini_check(settings, *, live):
    result = {
        "model": settings.model,
        "google_genai_sdk": "installed" if _sdk_available() else "missing",
        "api_key_configured": bool(settings.api_key),
        "monthly_request_cap": settings.max_calls_per_month,
        "requests_already_used_this_month": None,
        "request_is_search_query": False,
        "search_grounding_supported": "model/project dependent; verify official model docs",
        "account_quota_check": "not available to the local app; inspect Google AI Studio for the API project",
        "cost_check": "not available to the local app; inspect current pricing and billing tier before live use",
        "paid_tier_upgrade": "never performed by this command",
        "live_metadata_check": "not requested",
    }
    if not live:
        result["network_request"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not settings.api_key:
        raise SystemExit("GEMINI_API_KEY is not configured; no API request was made.")
    from google import genai

    client = genai.Client(api_key=settings.api_key)
    model = client.models.get(model=settings.model)
    result["live_metadata_check"] = (
        "model endpoint is accessible; Search grounding entitlement/quota was not tested"
    )
    result["resolved_model_name"] = getattr(model, "name", settings.model)
    result["network_request"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _sdk_available():
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def _launch_ui(port):
    if importlib.util.find_spec("streamlit") is None:
        raise SystemExit(
            'The UI dependency is missing. Install it with: python -m pip install -e ".[ui]"'
        )
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(PROJECT_ROOT / "wardprice" / "ui.py"),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]
    return subprocess.call(command, cwd=PROJECT_ROOT)


def _connect_read_only(path: Path):
    if not path.is_file():
        raise SystemExit(f"Database does not exist: {path}; run `python -m wardprice collection-init` first.")
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _collection_schema_ready(db) -> bool:
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
    ).fetchone())


def _run_collection_command(args) -> None:
    from .collectors.orchestrator import (
        collection_report,
        plan_collection,
        ranks_from_expression,
        run_live_collection,
    )
    from .collectors.source_registry import source_readiness, sync_registry
    from .collectors.storage import (
        collection_targets,
        ensure_collection_schema,
        source_rows,
    )

    if args.command == "collection-init":
        backup = backup_database_before_collection_migration(args.db)
        db = connect(args.db)
        try:
            ensure_collection_schema(db)
            registry = sync_registry(db, args.source_registry)
            target_count = len(collection_targets(db))
            print(json.dumps({
                "status": "INITIALIZED",
                "database": str(args.db),
                "backup": str(backup) if backup else None,
                "source_registry": registry,
                "top50_targets_loaded": target_count,
                "live_enabled": False,
                "network_attempted": False,
            }, ensure_ascii=False, indent=2))
        finally:
            db.close()
        return

    if args.command == "collect-daily" and args.live:
        db = connect(args.db)
    else:
        db = _connect_read_only(args.db)
    try:
        if not _collection_schema_ready(db):
            raise SystemExit("Collection tables are not initialized; run `python -m wardprice collection-init` first.")
        registered_sources = source_rows(db)
        if args.source and args.source not in {source["source_id"] for source in registered_sources}:
            raise SystemExit(f"Unknown collection source_id: {args.source}")
        if args.command == "collection-sources":
            print(json.dumps({
                "source_readiness": source_readiness(db),
                "sources": [source for source in registered_sources if not args.source or source["source_id"] == args.source],
                "network_attempted": False,
            }, ensure_ascii=False, indent=2))
        elif args.command == "collection-status":
            print(json.dumps(collection_report(db), ensure_ascii=False, indent=2))
        elif args.command == "collection-report":
            report = collection_report(db)
            args.output.mkdir(parents=True, exist_ok=True)
            report_path = args.output / f"collection_report_{report['run_date']}.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"report": report, "report_file": str(report_path)}, ensure_ascii=False, indent=2))
        elif args.command == "collect-daily":
            try:
                ranks = {args.rank} if args.rank is not None else (
                    ranks_from_expression(args.ranks) if args.ranks else None
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            if args.live:
                result = run_live_collection(
                    db,
                    ranks=ranks,
                    batch=args.batch,
                    limit=args.limit,
                    max_requests=args.max_requests,
                    resume=args.resume,
                    source_id=args.source,
                )
            else:
                result = plan_collection(db, ranks=ranks, batch=args.batch, limit=args.limit)
                if args.source:
                    result["sources"] = [
                        source for source in result["sources"] if source["source_id"] == args.source
                    ]
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Collect and summarize property listings by ward")
    parser.add_argument(
        "command",
        choices=[
            "run",
            "status",
            "export",
            "validate-registry",
            "import-wards",
            "import-targets",
            "import-gemini-web",
            "targets",
            "gemini-check",
            "listings",
            "email-dry-run",
            "ui",
            "admin-import",
            "import-crosswalk",
            "admin-search",
            "lookup",
            "coverage",
            "collection-priorities",
            "price-history",
            "ingest-listings",
            "recompute-stats",
            "api",
            "collection-init",
            "collection-sources",
            "collect-daily",
            "collection-status",
            "collection-report",
        ],
    )
    parser.add_argument(
        "--file",
        type=Path,
        help=(
            "Input file; ingest-listings accepts JSON, CSV, or XLSX. "
            "import-targets also accepts the Top50 ZIP."
        ),
    )
    parser.add_argument(
        "--wards", help="Comma-separated ward codes, all of which must be whitelisted"
    )
    parser.add_argument(
        "--live", action="store_true", help="Make an explicitly requested live provider or collection call"
    )
    parser.add_argument(
        "--send-email", action="store_true", help="Send Gmail after a live collection run"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write eligible import-gemini-web rows into canonical listings",
    )
    parser.add_argument(
        "--ui-port", type=int, default=8501, help="Local dashboard port (default: 8501)"
    )
    parser.add_argument("--api-host", default="127.0.0.1", help="Local API bind address")
    parser.add_argument("--api-port", type=int, default=8765, help="Local API port")
    parser.add_argument("--as-of-date", help="Official administrative snapshot date, YYYY-MM-DD")
    parser.add_argument("--current", action="store_true", help="Promote imported admin snapshot to current")
    parser.add_argument("--dataset-status", default="IMPORTED")
    parser.add_argument("--source-quality", default="OFFICIAL_SOURCE")
    parser.add_argument("--source-reference")
    parser.add_argument("--query", default="", help="Ward name or administrative code")
    parser.add_argument("--province")
    parser.add_argument("--legacy-district")
    parser.add_argument("--target-rank", type=int)
    parser.add_argument("--unit-id", type=int)
    parser.add_argument("--property-type")
    parser.add_argument("--area-basis")
    parser.add_argument("--include-historical", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Ask the disabled provider fallback")
    parser.add_argument("--operator-verified", action="store_true")
    parser.add_argument("--verified-by")
    parser.add_argument("--verification-reference")
    parser.add_argument("--daily-limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="Explicitly select offline collection planning")
    parser.add_argument("--rank", type=int, help="One Top 50 target rank")
    parser.add_argument("--ranks", help="Comma-separated ranks and ranges, for example 1-5,8")
    parser.add_argument("--batch", type=int, help="Five-target daily batch, numbered 1 through 10")
    parser.add_argument("--all", dest="all_targets", action="store_true", help="Select all Top 50 targets")
    parser.add_argument("--limit", type=int, default=10, help="Maximum candidates per target (1..10)")
    parser.add_argument("--max-requests", type=int, default=500, help="Maximum HTTP requests in this run")
    parser.add_argument("--resume", action="store_true", help="Resume the same interrupted live selection")
    parser.add_argument("--source", help="Limit collection to one registered source_id")
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    _common_options(parser)
    args = parser.parse_args()
    if args.ui_port < 1024 or args.ui_port > 65535:
        parser.error("--ui-port must be between 1024 and 65535")
    if args.api_port < 1024 or args.api_port > 65535:
        parser.error("--api-port must be between 1024 and 65535")
    if args.send_email and (args.command != "run" or not args.live):
        parser.error("--send-email requires the run command and --live")
    if args.apply and args.command not in {"import-gemini-web", "ingest-listings"}:
        parser.error("--apply is only available for import-gemini-web or ingest-listings")
    if args.operator_verified and args.command != "ingest-listings":
        parser.error("--operator-verified is only available for ingest-listings")
    if args.command == "admin-import" and not args.as_of_date:
        parser.error("admin-import requires --as-of-date YYYY-MM-DD")
    if args.current and args.command != "admin-import":
        parser.error("--current is only available for admin-import")
    if args.operator_verified and (not args.verified_by or not args.verification_reference):
        parser.error("--operator-verified requires --verified-by and --verification-reference")
    collector_options_used = any((
        args.dry_run, args.rank is not None, args.ranks, args.batch is not None,
        args.all_targets, args.resume, args.source,
        args.max_requests != 500, args.limit != 10,
    ))
    if collector_options_used and args.command not in COLLECTION_COMMANDS:
        parser.error("collection selection options are only available for collection commands")
    if args.command in COLLECTION_COMMANDS and args.send_email:
        parser.error("Gmail is not part of the automatic web collection commands")
    if args.command in COLLECTION_COMMANDS - {"collect-daily"} and args.live:
        parser.error("--live is only available with collect-daily")
    if args.command == "collect-daily":
        if args.live and args.dry_run:
            parser.error("choose either --live or --dry-run; offline dry-run is the default")
        if args.rank is not None and not 1 <= args.rank <= 50:
            parser.error("--rank must be within 1..50")
        if args.batch is not None and not 1 <= args.batch <= 10:
            parser.error("--batch must be within 1..10")
        if args.limit < 1 or args.limit > 10:
            parser.error("--limit must be within 1..10")
        if args.max_requests < 1 or args.max_requests > 500:
            parser.error("--max-requests must be within 1..500")
        if args.resume and not args.live:
            parser.error("--resume requires --live")
        if args.batch is not None and (args.rank is not None or args.ranks):
            parser.error("use either --batch or --rank/--ranks")
        if args.rank is not None and args.ranks:
            parser.error("use either --rank or --ranks")
        if args.all_targets and any((args.rank is not None, args.ranks, args.batch is not None)):
            parser.error("--all cannot be combined with --rank, --ranks or --batch")
    elif any((
        args.dry_run,
        args.rank is not None,
        args.ranks,
        args.batch is not None,
        args.all_targets,
        args.resume,
        args.limit != 10,
        args.max_requests != 500,
    )):
        parser.error("collection selection options require collect-daily")
    if args.source and args.command not in {"collect-daily", "collection-sources"}:
        parser.error("--source is only available with collect-daily or collection-sources")
    if args.command != "collection-init" and args.source_registry != DEFAULT_SOURCE_REGISTRY:
        parser.error("--source-registry is only available with collection-init")

    settings = Settings.from_env()
    try:
        expected_db = settings.database_path if settings.demo_mode else DEFAULT_DB
        expected_output = settings.output_path if settings.demo_mode else DEFAULT_OUTPUT
    except ValueError as exc:
        parser.error(str(exc))
    if args.db is not None and settings.demo_mode and args.db.resolve() != expected_db.resolve():
        parser.error("DEMO_MODE only permits state/ward_prices.demo.sqlite3.")
    if args.db is not None and not settings.demo_mode and args.db.resolve() == (
        PROJECT_ROOT / "state" / "ward_prices.demo.sqlite3"
    ).resolve():
        parser.error("The demo database requires WARDPRICE_DEMO_MODE=1.")
    if args.output is not None and settings.demo_mode and args.output.resolve() != expected_output.resolve():
        parser.error("DEMO_MODE only permits the isolated outputs/demo directory.")
    args.db = args.db or expected_db
    args.output = args.output or expected_output
    if settings.demo_mode and (args.live or args.send_email):
        parser.error("Gemini live calls and Gmail are disabled in DEMO_MODE.")
    if settings.demo_mode and args.command not in {"ui", "api"}:
        parser.error(
            "In DEMO_MODE use `python -m wardprice.demo ...`; only the demo UI/API "
            "are available through this command."
        )
    if settings.demo_mode and args.command in COLLECTION_COMMANDS:
        parser.error("Web collection is disabled in DEMO_MODE; the demo database is isolated.")
    if args.command in COLLECTION_COMMANDS:
        _run_collection_command(args)
        return
    if args.command == "ui":
        return _launch_ui(args.ui_port)
    if args.command == "gemini-check":
        try:
            _print_gemini_check(settings, live=args.live)
        except Exception as exc:
            raise SystemExit(f"Gemini model check failed: {exc}") from exc
        return

    if args.command == "api":
        try:
            import uvicorn

            from .api import create_app
        except ImportError as exc:
            raise SystemExit('Install API dependencies with: python -m pip install -e ".[api]"') from exc
        uvicorn.run(
            create_app(args.db, demo_mode=settings.demo_mode),
            host=args.api_host,
            port=args.api_port,
        )
        return

    if args.command == "validate-registry":
        wards = load_ward_whitelist(args.registry)
        print(
            json.dumps(
                {"whitelist_wards": len(wards), "ward_codes": [w.code for w in wards]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    db = connect(args.db)
    try:
        if args.command == "import-gemini-web":
            if args.file is None:
                raise SystemExit("import-gemini-web requires --file <Web pilot handoff JSON>")
            from wardprice_webpilot.pipeline_bridge import (
                import_webpilot_handoff,
                preview_webpilot_handoff,
            )

            payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
            report = (
                import_webpilot_handoff(db, payload)
                if args.apply
                else preview_webpilot_handoff(db, payload)
            )
            print(json.dumps({**report, "source_file": str(args.file)}, ensure_ascii=False, indent=2))
            return

        if args.command == "import-wards":
            source = args.file or args.registry
            wards = load_ward_whitelist(source)
            save_ward_whitelist(db, wards)
            print(
                json.dumps(
                    {"imported_active_wards": len(wards), "source": str(source)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        if args.command == "import-targets":
            if args.file is None:
                raise SystemExit("import-targets requires --file <Top50 CSV or ZIP>")
            targets = load_legacy_targets(args.file)
            save_legacy_targets(db, targets)
            print(
                json.dumps(
                    {**target_summary(targets), "source": str(args.file)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        if args.command == "admin-import":
            if args.file is None:
                raise SystemExit("admin-import requires --file <official XML or normalized CSV>")
            from .national_registry import import_admin_file

            result = import_admin_file(
                db,
                args.file,
                as_of_date=args.as_of_date,
                is_current=args.current,
                dataset_status=args.dataset_status,
                source_quality=args.source_quality,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.command == "import-crosswalk":
            if args.file is None or not args.source_reference:
                raise SystemExit("import-crosswalk requires --file <CSV> and --source-reference <URL>")
            from .national_registry import import_crosswalk_csv

            result = import_crosswalk_csv(db, args.file, source_reference=args.source_reference)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.command == "admin-search":
            from .national_registry import search_administrative_units

            results = search_administrative_units(
                db,
                args.query,
                province=args.province,
                legacy_district=args.legacy_district,
                target_rank=args.target_rank,
                include_historical=args.include_historical,
            )
            print(json.dumps({"status": "FOUND" if results else "NOT_FOUND", "results": results}, ensure_ascii=False, indent=2))
            return

        if args.command == "lookup":
            from .national_registry import lookup_ward_price

            result = lookup_ward_price(
                db,
                args.query,
                province=args.province,
                legacy_district=args.legacy_district,
                target_rank=args.target_rank,
                property_type=args.property_type,
                area_basis=args.area_basis,
                refresh=args.refresh,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.command == "coverage":
            from .national_registry import national_coverage

            print(json.dumps(national_coverage(db), ensure_ascii=False, indent=2))
            return

        if args.command == "collection-priorities":
            from .national_registry import national_collection_priorities

            print(json.dumps(national_collection_priorities(db), ensure_ascii=False, indent=2))
            return

        if args.command == "price-history":
            if args.unit_id is None:
                raise SystemExit("price-history requires --unit-id")
            from .national_registry import price_history

            rows = price_history(
                db,
                args.unit_id,
                property_type=args.property_type,
                area_basis=args.area_basis,
            )
            print(json.dumps({"count": len(rows), "history": rows}, ensure_ascii=False, indent=2))
            return

        if args.command == "ingest-listings":
            if args.file is None:
                raise SystemExit("ingest-listings requires --file <JSON, CSV, or XLSX>")
            from .price_warehouse import import_listing_payload, load_listing_payload

            payload = load_listing_payload(args.file)
            report = import_listing_payload(
                db,
                payload,
                apply=args.apply,
                operator_verified=args.operator_verified,
                verified_by=args.verified_by,
                verification_reference=args.verification_reference,
                daily_limit=args.daily_limit,
            )
            print(json.dumps({**report, "source_file": str(args.file)}, ensure_ascii=False, indent=2))
            return

        if args.command == "recompute-stats":
            from .price_warehouse import recompute_statistics

            result = recompute_statistics(db)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.command == "targets":
            rows = legacy_target_rows(db)
            print(
                json.dumps(
                    {"target_count": len(rows), "targets": rows}, ensure_ascii=False, indent=2
                )
            )
            return

        if args.command == "status":
            all_stats = stats(db)
            result = {
                "tracked_listings": all_stats["tracked_listings"],
                "eligible_listings_in_active_whitelist": all_stats["eligible_listings"],
                "listing_api_calls_this_month": all_stats["listing_api_calls_this_month"],
                "active_whitelist_wards": [
                    {
                        "ward_code": ward.code,
                        "ward_name": ward.name,
                        "district": ward.district,
                        "province": ward.province,
                    }
                    for ward in active_wards(db)
                ],
                "legacy_valuation_data_excluded_from_listing_statistics": {
                    key: all_stats[key]
                    for key in (
                        "wards_with_any_research_price",
                        "price_rows_latest",
                        "ai_estimate_rows",
                        "market_reference_unverified_rows",
                        "market_verified_rows",
                        "api_calls_this_month",
                        "attempts_total",
                    )
                },
            }
            result["ward_type_statistics"] = listing_statistics(db)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.command == "listings":
            print(
                json.dumps(
                    {
                        "tracked_listings": tracked_listing_count(db),
                        "listings": listing_rows(db),
                        "ward_type_statistics": listing_statistics(db),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        if args.command == "export":
            files = export(db, args.output)
            print("Exported " + ", ".join(f"{key}={path}" for key, path in files.items()))
            return

        if args.command == "email-dry-run":
            files = export(db, args.output)
            preview = dry_run_report(
                settings,
                files,
                f"WardPriceDaily — daily listing report {files['daily_html'].stem.removeprefix('daily_report_')}",
            )
            preview.pop("message")
            print(json.dumps({"smtp_called": False, **preview}, ensure_ascii=False, indent=2))
            return

        wards = active_wards(db)
        requested_codes = _parse_codes(args.wards)
        if not wards:
            print("No ward whitelist has been imported; no Gemini request was made.")
            if args.live:
                raise SystemExit("Import the fixed ward list before a live run.")
            return
        if requested_codes is not None:
            known = {ward.code for ward in wards}
            unknown = set(requested_codes) - known
            if unknown:
                raise SystemExit(
                    f"Ward codes are outside the imported whitelist: {', '.join(sorted(unknown))}"
                )

        if not args.live:
            calls_left = max(0, settings.max_calls_per_month - listing_call_count(db))
            selected = choose_listing_wards(
                db,
                [ward for ward in wards if requested_codes is None or ward.code in requested_codes],
                limit=min(settings.max_wards_per_run, calls_left),
            )
            print("DRY RUN — no Gemini calls and no emails")
            print(f"tracked_listings={tracked_listing_count(db)}/{settings.max_total_listings}")
            for ward in selected:
                location = ", ".join(
                    part for part in (ward.name, ward.district, ward.province) if part
                )
                print(f"{ward.code} {location}")
            if not selected:
                print("No wards are currently eligible or the monthly request cap is reached.")
            return

        if not settings.api_key:
            raise SystemExit("GEMINI_API_KEY is missing; no API request was made.")
        if args.send_email:
            if not settings.email_enabled:
                raise SystemExit("--send-email requires ENABLE_EMAIL=true")
            missing = [
                name
                for name, value in (
                    ("GMAIL_ADDRESS", settings.gmail_address),
                    ("GMAIL_APP_PASSWORD", settings.gmail_app_password),
                    ("REPORT_TO", settings.report_to),
                )
                if not value
            ]
            if missing:
                raise SystemExit("--send-email requires " + ", ".join(missing))

        result = run_listing_cycle(
            db,
            settings,
            GeminiResearcher(settings.api_key, settings.model),
            selected_ward_codes=requested_codes,
        )
        files = export(db, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.send_email:
            report_date = files["daily_html"].stem.removeprefix("daily_report_")
            send_report(settings, files, f"WardPriceDaily — daily listing report {report_date}")
            print("Email sent")
    finally:
        db.close()


if __name__ == "__main__":
    main()
