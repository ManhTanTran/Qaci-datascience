"""FastAPI HTTP surface for national administrative search and local price lookup."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT
from .database import connect
from .national_registry import (
    WardLookupService,
    WardPriceLookupService,
    national_collection_priorities,
    national_coverage,
    normalize_admin_name,
)

DEFAULT_API_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_INGESTION_PILOT_DB = PROJECT_ROOT / "state" / "ward_prices.ingestion_pilot.sqlite3"
DEFAULT_SOURCE_REGISTRY = PROJECT_ROOT / "config" / "collector_sources.json"
UI_DIR = PROJECT_ROOT / "wardprice" / "static"


class ProvinceSearchRequest(BaseModel):
    province: str | None = Field(default=None, min_length=1, max_length=120)


def create_app(
    db_path: Path | str = DEFAULT_API_DB,
    *,
    demo_mode: bool = False,
    historical_pilot_db_path: Path | str | None = None,
    ingestion_pilot_db_path: Path | str | None = None,
    collector_source_registry_path: Path | str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="WardPriceDaily National Real Estate Knowledge Base",
        version="1.0.0",
        description=(
            "Local-first API for official administrative units, reviewed aliases, "
            "verified listing statistics and national coverage. External retrieval is disabled."
        ),
    )
    app.state.db_path = Path(db_path)
    app.state.demo_mode = demo_mode
    app.state.historical_pilot_db_path = Path(
        historical_pilot_db_path
        if historical_pilot_db_path is not None
        else PROJECT_ROOT / "state" / "ward_prices.historical_pilot.sqlite3"
    )
    app.state.ingestion_pilot_db_path = Path(
        ingestion_pilot_db_path
        if ingestion_pilot_db_path is not None
        else DEFAULT_INGESTION_PILOT_DB
    )
    app.state.collector_source_registry_path = Path(
        collector_source_registry_path
        if collector_source_registry_path is not None
        else DEFAULT_SOURCE_REGISTRY
    )
    production_db = (PROJECT_ROOT / "state" / "ward_prices.sqlite3").resolve()
    demo_db = (PROJECT_ROOT / "state" / "ward_prices.demo.sqlite3").resolve()
    resolved_db = app.state.db_path.resolve()
    if demo_mode and resolved_db == production_db:
        raise ValueError("DEMO_MODE API cannot use the production database.")
    if not demo_mode and resolved_db == demo_db:
        raise ValueError("The demo database requires demo_mode=True.")

    app.mount("/assets", StaticFiles(directory=UI_DIR), name="dashboard-assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        # The normal local lookup opens the isolated Top 50 historical lookup.
        # Demo mode keeps its own UI and database boundary.
        if not app.state.demo_mode and app.state.historical_pilot_db_path.is_file():
            return FileResponse(UI_DIR / "historical-pilot.html")
        return FileResponse(UI_DIR / "index.html")

    @contextmanager
    def database() -> Iterator[Any]:
        db = connect(app.state.db_path)
        try:
            yield db
        finally:
            db.close()

    @app.get("/api/v1/health", tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "external_provider_enabled": False,
            "demo_mode": app.state.demo_mode,
        }

    @app.get("/historical-pilot", include_in_schema=False)
    def historical_pilot_dashboard() -> FileResponse:
        if not app.state.historical_pilot_db_path.is_file():
            raise HTTPException(status_code=404, detail="Historical pilot database is not initialized")
        return FileResponse(UI_DIR / "historical-pilot.html")

    @app.get("/ingestion-pilot", include_in_schema=False)
    def ingestion_pilot_dashboard() -> FileResponse:
        if app.state.demo_mode:
            raise HTTPException(status_code=404, detail="Ingestion pilot is unavailable in DEMO_MODE")
        return FileResponse(UI_DIR / "ingestion-pilot.html")

    @app.get("/api/v1/ingestion/monitoring", tags=["ingestion-pilot"])
    def ingestion_pilot_monitoring() -> dict[str, Any]:
        if app.state.demo_mode:
            return {"status": "DISABLED_DEMO_MODE", "network_attempted": False}
        from .ingestion_pilot import monitoring_summary

        try:
            return monitoring_summary(app.state.ingestion_pilot_db_path)
        except FileNotFoundError:
            return {"status": "NOT_INITIALIZED", "network_attempted": False,
                    "production_database_written": False}

    @app.get("/api/v1/ingestion/listings", tags=["ingestion-pilot"])
    def ingestion_pilot_listings(
        target_rank: int | None = Query(default=None, ge=1, le=50),
        property_type: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        if app.state.demo_mode:
            return {"status": "DISABLED_DEMO_MODE", "listings": [], "network_attempted": False}
        from .ingestion_pilot import lookup_pilot

        try:
            return lookup_pilot(app.state.ingestion_pilot_db_path,
                                target_rank=target_rank, property_type=property_type,
                                limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/research/historical/overview", tags=["historical-research"])
    def historical_pilot_overview() -> dict[str, Any]:
        from .historical_dataset import pilot_overview

        try:
            return pilot_overview(app.state.historical_pilot_db_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/research/historical/targets", tags=["historical-research"])
    def historical_pilot_targets() -> dict[str, Any]:
        from .historical_dataset import pilot_targets

        try:
            return {"targets": pilot_targets(app.state.historical_pilot_db_path)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/research/historical/lookup", tags=["historical-research"])
    def historical_pilot_lookup(
        target_rank: int = Query(ge=1, le=50),
        property_type: str | None = Query(default=None),
    ) -> dict[str, Any]:
        from .historical_dataset import pilot_lookup

        try:
            return pilot_lookup(
                app.state.historical_pilot_db_path,
                target_rank,
                property_type=property_type,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if demo_mode:
        from .demo import demo_coverage, demo_database, demo_history, demo_lookup, demo_wards

        @app.get("/api/v1/demo/coverage", tags=["demo"])
        def demo_coverage_endpoint() -> dict[str, Any]:
            with demo_database(app.state.db_path) as db:
                return demo_coverage(db)

        @app.get("/api/v1/demo/wards", tags=["demo"])
        def demo_wards_endpoint() -> dict[str, Any]:
            with demo_database(app.state.db_path) as db:
                targets = demo_wards(db)
                counts = {
                    row["target_rank"]: int(row["listing_count"])
                    for row in db.execute(
                        """SELECT target_rank,COUNT(*) AS listing_count
                           FROM demo_listings WHERE active=1 GROUP BY target_rank"""
                    )
                }
                for target in targets:
                    target["listing_count"] = counts.get(target["target_rank"], 0)
                return {"targets": targets}

        @app.get("/api/v1/demo/lookup", tags=["demo"])
        def demo_lookup_endpoint(
            q: str = Query(default="", max_length=120),
            property_type: str | None = Query(default=None),
        ) -> dict[str, Any]:
            with demo_database(app.state.db_path) as db:
                try:
                    return demo_lookup(db, q, property_type=property_type)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

        @app.get("/api/v1/demo/history", tags=["demo"])
        def demo_history_endpoint(
            target_rank: int = Query(ge=1, le=50),
            property_type: str | None = Query(default=None),
        ) -> dict[str, Any]:
            with demo_database(app.state.db_path) as db:
                return demo_history(db, target_rank, property_type=property_type)

    @app.get("/api/v1/administrative-units/search", tags=["administrative"])
    def search_units(
        q: str = Query(default="", max_length=120),
        province: str | None = Query(default=None, max_length=120),
        legacy_district: str | None = Query(default=None, max_length=120),
        target_rank: int | None = Query(default=None, ge=1, le=50),
        include_historical: bool = True,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        with database() as db:
            results = WardLookupService(db).search(
                q,
                province=province,
                legacy_district=legacy_district,
                target_rank=target_rank,
                include_historical=include_historical,
                limit=limit,
            )
        return {"status": "FOUND" if results else "NOT_FOUND", "results": results}

    @app.get("/api/v1/administrative-units/{unit_id}", tags=["administrative"])
    def get_unit(unit_id: int) -> dict[str, Any]:
        with database() as db:
            result = WardLookupService(db).by_id(unit_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Administrative unit not found")
        return {"status": "FOUND", "administrative_unit": result}

    @app.get("/api/v1/ward-prices/lookup", tags=["prices"])
    def lookup_price(
        q: str = Query(default="", max_length=120),
        province: str | None = Query(default=None, max_length=120),
        legacy_district: str | None = Query(default=None, max_length=120),
        target_rank: int | None = Query(default=None, ge=1, le=50),
        property_type: str | None = Query(default=None),
        area_basis: str | None = Query(default=None),
        refresh: bool = False,
    ) -> dict[str, Any]:
        with database() as db:
            try:
                result = WardPriceLookupService(db).lookup(
                    q,
                    province=province,
                    legacy_district=legacy_district,
                    target_rank=target_rank,
                    property_type=property_type,
                    area_basis=area_basis,
                    refresh=refresh,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result

    @app.get("/api/v1/ward-prices/history", tags=["prices"])
    def get_price_history(
        unit_id: int = Query(ge=1),
        property_type: str | None = None,
        area_basis: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, Any]:
        with database() as db:
            unit = WardLookupService(db).by_id(unit_id)
            if unit is None:
                raise HTTPException(status_code=404, detail="Administrative unit not found")
            history = WardPriceLookupService(db).history(
                unit_id,
                property_type=property_type,
                area_basis=area_basis,
                limit=limit,
            )
        return {"status": "FOUND" if history else "NO_PRICE_DATA", "history": history}

    @app.get("/api/v1/coverage", tags=["coverage"])
    def coverage() -> dict[str, Any]:
        with database() as db:
            return national_coverage(db)

    @app.get("/api/v1/collection/monitoring", tags=["collection"])
    def collection_monitoring() -> dict[str, Any]:
        if app.state.demo_mode:
            return {
                "status": "DISABLED_DEMO_MODE",
                "message": "Production collection monitoring is unavailable in DEMO_MODE.",
            }
        with database() as db:
            initialized = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
            ).fetchone()
            if not initialized:
                return {
                    "status": "NOT_INITIALIZED",
                    "message": "Run `python -m wardprice collection-init` to create the monitoring tables.",
                    "network_attempted": False,
                }
            from .collectors.storage import monitoring_summary

            return monitoring_summary(db)

    def province_search_context(province: str | None) -> dict[str, Any]:
        from .collectors.source_registry import (
            configured_source_readiness,
            load_source_registry,
        )
        from .historical_dataset import pilot_targets

        try:
            targets = pilot_targets(app.state.historical_pilot_db_path)
            registry = load_source_registry(app.state.collector_source_registry_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Không đọc được cấu hình nguồn: {exc}") from exc

        if province is None:
            matching_targets = targets
        else:
            normalized_province = normalize_admin_name(province)
            matching_targets = [
                target for target in targets
                if normalize_admin_name(target["original_province"]) == normalized_province
            ]
        readiness = configured_source_readiness(registry)
        return {
            "province": province,
            "selection_mode": "ALL_TOP50" if province is None else "PROVINCE",
            "status": "READY_TO_CHECK" if matching_targets else "NO_TOP50_TARGETS",
            "target_count": len(matching_targets),
            "targets": [
                {
                    "target_rank": target["target_rank"],
                    "ward": target["original_ward"],
                    "district": target["original_district"],
                    "province": target["original_province"],
                }
                for target in matching_targets
            ],
            "global_live_enabled": readiness["global_live_enabled"],
            "configured_source_count": readiness["ready_count"],
            "sources": [
                *[
                    {**source, "status": "CONFIGURED"}
                    for source in readiness["ready_sources"]
                ],
                *[
                    {**source, "status": "BLOCKED"}
                    for source in readiness["blocked_sources"]
                ],
            ],
            "network_attempted": False,
        }

    @app.get("/api/v1/collection/province-search/readiness", tags=["collection"])
    def province_search_readiness(
        province: str = Query(min_length=1, max_length=120),
    ) -> dict[str, Any]:
        if app.state.demo_mode:
            return {
                "status": "DISABLED_DEMO_MODE",
                "province": province,
                "target_count": 0,
                "sources": [],
                "network_attempted": False,
            }
        return province_search_context(province)

    @app.get("/api/v1/collection/top50-search/readiness", tags=["collection"])
    def top50_search_readiness() -> dict[str, Any]:
        if app.state.demo_mode:
            return {
                "status": "DISABLED_DEMO_MODE",
                "selection_mode": "ALL_TOP50",
                "target_count": 0,
                "sources": [],
                "network_attempted": False,
            }
        return province_search_context(None)

    @app.post("/api/v1/collection/top50-search", tags=["collection"])
    @app.post("/api/v1/collection/province-search", tags=["collection"])
    def province_search(request: ProvinceSearchRequest) -> dict[str, Any]:
        if app.state.demo_mode:
            return {
                "status": "DISABLED_DEMO_MODE",
                "message": "Chế độ demo không được phép tìm kiếm hoặc thu thập web.",
                "network_attempted": False,
                "database_written": False,
            }

        context = province_search_context(request.province)
        if not context["target_count"]:
            return {
                **context,
                "status": "NO_TOP50_TARGETS",
                "message": "Không có địa bàn phù hợp trong danh sách Top 50.",
                "network_attempted": False,
                "database_written": False,
            }

        from .collectors.source_registry import (
            load_source_registry,
            source_readiness,
        )
        from .collectors.storage import collection_settings, collection_targets, source_rows

        registry = load_source_registry(app.state.collector_source_registry_path)
        configured_by_id = {
            item["source_id"]: item for item in registry.get("sources", [])
        }
        config_ready_ids = {
            item["source_id"]
            for item in context["sources"]
            if item["status"] in {"CONFIGURED", "READY"}
        }
        if not config_ready_ids:
            return {
                **context,
                "status": "BLOCKED_NO_AUTHORIZED_SOURCE",
                "message": "Chưa có nguồn nào được duyệt và bật; không gửi request ra website.",
                "network_attempted": False,
                "database_written": False,
            }

        if not app.state.db_path.is_file():
            return {
                **context,
                "status": "COLLECTION_NOT_INITIALIZED",
                "message": "Chưa có database collection. Chạy collection-init để tạo schema có backup trước khi thu thập.",
                "network_attempted": False,
                "database_written": False,
            }

        ranks = {int(target["target_rank"]) for target in context["targets"]}
        with database() as db:
            initialized = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
            ).fetchone()
            if not initialized:
                return {
                    **context,
                    "status": "COLLECTION_NOT_INITIALIZED",
                    "message": "Các bảng collection chưa được khởi tạo; chưa gửi request ra website.",
                    "network_attempted": False,
                    "database_written": False,
                }

            runtime_readiness = source_readiness(db)
            database_ready_ids = {
                item["source_id"] for item in runtime_readiness["ready_sources"]
            }
            eligible_source_ids = config_ready_ids & database_ready_ids
            combined_sources = []
            runtime_by_id = {
                item["source_id"]: item for item in runtime_readiness["blocked_sources"]
            }
            runtime_by_id.update({
                item["source_id"]: {**item, "reasons": []}
                for item in runtime_readiness["ready_sources"]
            })
            database_by_id = {
                item["source_id"]: item for item in source_rows(db)
            }
            persisted_settings = collection_settings(db)
            global_config_synced = (
                bool(persisted_settings.get("global_live_enabled"))
                == bool(registry.get("global_live_enabled"))
                and str(persisted_settings.get("user_agent") or "")
                == str(registry.get("user_agent") or "")
                and int(persisted_settings.get("global_daily_request_budget") or 0)
                == int(registry.get("global_daily_request_budget") or 0)
            )
            for source in context["sources"]:
                runtime = runtime_by_id.get(source["source_id"])
                configured = configured_by_id.get(source["source_id"])
                persisted = database_by_id.get(source["source_id"])
                reasons = list(source.get("reasons", []))
                if runtime is None or configured is None or persisted is None:
                    reasons.append("DATABASE_REGISTRY_NOT_SYNCED")
                else:
                    reasons.extend(
                        reason for reason in runtime.get("reasons", []) if reason not in reasons
                    )
                    if not global_config_synced:
                        reasons.append("DATABASE_REGISTRY_NOT_SYNCED")
                    for field in (
                        "base_url", "robots_url", "terms_url", "policy_status",
                        "permission_reference", "search_url_template", "detail_path_regex",
                    ):
                        if str(configured.get(field) or "") != str(persisted.get(field) or ""):
                            reasons.append("DATABASE_REGISTRY_NOT_SYNCED")
                            break
                    if bool(configured.get("enabled")) != bool(persisted.get("enabled")):
                        reasons.append("DATABASE_REGISTRY_NOT_SYNCED")
                    for field in ("crawl_delay_seconds", "daily_request_budget"):
                        if float(configured.get(field) or 0) != float(persisted.get(field) or 0):
                            reasons.append("DATABASE_REGISTRY_NOT_SYNCED")
                            break
                eligible = source["source_id"] in eligible_source_ids and not reasons
                combined_sources.append({
                    **source,
                    "status": "READY" if eligible else "BLOCKED",
                    "reasons": reasons,
                })
            eligible_source_ids = {
                item["source_id"] for item in combined_sources if item["status"] == "READY"
            }
            if not eligible_source_ids:
                return {
                    **context,
                    "sources": combined_sources,
                    "status": "BLOCKED_NO_AUTHORIZED_SOURCE",
                    "message": "Source registry trong SQLite chưa đồng bộ hoặc chưa có nguồn đủ điều kiện; không gửi request.",
                    "network_attempted": False,
                    "database_written": False,
                }

            available_ranks = {
                target.rank for target in collection_targets(db, ranks)
            }
            if available_ranks != ranks:
                return {
                    **context,
                    "sources": combined_sources,
                    "status": "TOP50_TARGETS_NOT_SYNCED",
                    "message": "Danh sách địa bàn Top 50 chưa đồng bộ với collector; chưa gửi request.",
                    "network_attempted": False,
                    "database_written": False,
                }

            from .collectors.orchestrator import local_now, run_live_collection

            search_started_at = local_now().isoformat(timespec="seconds")
            result = run_live_collection(
                db,
                ranks=ranks,
                limit=10,
                max_requests=20,
                source_ids=eligible_source_ids,
                allow_auto_ingest=False,
            )
            run_id = result.get("run_id")
            attempt_rows = db.execute(
                """SELECT source_id,COUNT(DISTINCT target_rank) AS targets_tried,
                          SUM(request_count) AS requests_made,
                          SUM(discovered_count) AS links_found,
                          SUM(candidate_count) AS candidates_found,
                          SUM(verified_count) AS verified_candidates,
                          GROUP_CONCAT(DISTINCT status) AS statuses
                   FROM collection_target_attempts WHERE run_id=? GROUP BY source_id
                   ORDER BY source_id""",
                (run_id,),
            ).fetchall() if run_id else []
            source_names = {row["source_id"]: row["display_name"] for row in source_rows(db)}
            source_results = [
                {
                    **dict(row),
                    "display_name": source_names.get(row["source_id"], row["source_id"]),
                }
                for row in attempt_rows
            ]
            placeholders = ",".join("?" for _ in ranks)
            candidate_rows = db.execute(
                f"""SELECT DISTINCT c.target_rank,c.original_ward,c.original_district,
                           c.original_province,c.property_type,c.price_vnd,c.area_m2,
                           c.price_per_m2,c.validity_status,c.evidence_status,c.last_seen_at,
                           s.display_name AS source_name
                    FROM collection_candidates c
                    JOIN collection_sources s ON s.source_id=c.source_id
                    WHERE c.target_rank IN ({placeholders}) AND c.source_id IN (
                        {','.join('?' for _ in eligible_source_ids)}
                    ) AND julianday(c.last_seen_at)>=julianday(?)
                    ORDER BY c.last_seen_at DESC LIMIT 100""",
                [*sorted(ranks), *sorted(eligible_source_ids), search_started_at],
            ).fetchall()

        return {
            **context,
            "sources": combined_sources,
            "status": result["status"],
            "run_id": run_id,
            "request_count": result.get("requests_made", 0),
            "link_count": result.get("listing_urls_discovered", 0),
            "candidate_count": result.get("candidates_discovered", 0),
            "verified_count": result.get("source_verified", 0),
            "source_results": source_results,
            "candidates": [dict(row) for row in candidate_rows],
            "network_attempted": bool(result.get("network_attempted")),
            "database_written": True,
            "production_database_written": False,
            "message": "Kết quả được lưu ở kho candidate; không tự nhập vào thống kê hiện hành.",
        }

    @app.get("/api/v1/collection-priorities", tags=["priority"])
    def collection_priorities(
        limit: int = Query(default=100, ge=0, le=5000),
    ) -> dict[str, Any]:
        with database() as db:
            return national_collection_priorities(db, limit=limit)

    @app.get("/api/v1/priority-targets", tags=["priority"])
    def priority_targets() -> dict[str, Any]:
        with database() as db:
            rows = db.execute(
                """SELECT pt.target_rank,pt.original_ward,pt.original_district,
                          pt.original_province,pt.current_ward,pt.current_province,
                          pt.administrative_unit_id,pt.mapping_status,pt.source_reference,
                          u.administrative_code
                   FROM priority_targets pt LEFT JOIN administrative_units u
                     ON u.id=pt.administrative_unit_id
                   ORDER BY pt.target_rank"""
            ).fetchall()
            mappings = db.execute(
                """SELECT pm.target_rank,pm.relationship_type,pm.mapping_status,
                          pm.source_reference,pm.effective_date,u.id AS unit_id,
                          u.administrative_code,u.administrative_name,u.province_name
                   FROM priority_target_mappings pm JOIN administrative_units u
                     ON u.id=pm.administrative_unit_id
                   WHERE u.is_current=1 ORDER BY pm.target_rank,u.province_name,u.administrative_name"""
            ).fetchall()
        by_rank: dict[int, list[dict[str, Any]]] = {}
        for mapping in mappings:
            item = dict(mapping)
            by_rank.setdefault(item["target_rank"], []).append(item)
        safe_rows = []
        for row in rows:
            item = dict(row)
            item["current_mappings"] = by_rank.get(item["target_rank"], [])
            safe_rows.append(item)
        return {"status": "FOUND" if safe_rows else "NOT_FOUND", "targets": safe_rows}

    return app


app = create_app()
