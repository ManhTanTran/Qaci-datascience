"""FastAPI HTTP surface for national administrative search and local price lookup."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT
from .database import connect
from .national_registry import (
    WardLookupService,
    WardPriceLookupService,
    national_collection_priorities,
    national_coverage,
)

DEFAULT_API_DB = PROJECT_ROOT / "state" / "ward_prices.sqlite3"
DEFAULT_INGESTION_PILOT_DB = PROJECT_ROOT / "state" / "ward_prices.ingestion_pilot.sqlite3"
UI_DIR = PROJECT_ROOT / "wardprice" / "static"


def create_app(
    db_path: Path | str = DEFAULT_API_DB,
    *,
    demo_mode: bool = False,
    historical_pilot_db_path: Path | str | None = None,
    ingestion_pilot_db_path: Path | str | None = None,
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
