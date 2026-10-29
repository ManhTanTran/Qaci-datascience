"""One FastAPI app for both modules (one port).

Module 1 keeps its own routes (`/`, `/research-answers`, `/api/v1/research-answers/*`); module 2 is
added next to them as `/extract-claims` (page) and `/api/v1/extract-claims/*` (API). Binds to
127.0.0.1 by default and has no login: do not expose it to a network.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from claims_extractor import stats
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common.config import Config

from ..runner import Runner, WorkerBusy
from ..service import OpsService

log = logging.getLogger("pipeline.web")
STATIC = Path(__file__).parent / "static"
_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
API_PREFIX = "/api/v1/extract-claims"


class RunBody(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=100000)
    rescan: bool = False


class ReprocessBody(BaseModel):
    statuses: list[Literal["ok", "empty", "failed"]] = []
    answer_ids: list[str] = Field(default=[], max_length=500)
    target_month: str | None = Field(default=None, pattern=_MONTH)
    crawl_run_id: str | None = None
    stale: bool = False
    run: bool = True


class AutoBody(BaseModel):
    enabled: bool


def require_ui_header(x_requested_with: str | None = Header(default=None)) -> None:
    """State-changing calls must come from our own page (a custom header blocks cross-site forms)."""
    if x_requested_with != "ops-ui":
        raise HTTPException(403, "Thiếu header X-Requested-With.")


def _guarded(fn):
    try:
        return fn()
    except WorkerBusy as busy:
        raise HTTPException(409, str(busy)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        log.exception("request failed")
        raise HTTPException(500, "Lỗi nội bộ; xem logs/pipeline.log.") from None


def build_router(service: OpsService) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["extract-claims"])
    post = APIRouter(dependencies=[Depends(require_ui_header)])

    def store_call(fn):
        def run():
            with service.runner.open_store() as store:
                return fn(store)
        return _guarded(run)

    @router.get("/status")
    def status():
        return _guarded(service.status)

    @router.get("/quality")
    def quality():
        return _guarded(service.quality)

    @router.get("/usage")
    def usage():
        return _guarded(service.usage)

    @router.get("/answers")
    def answers(status: str | None = None, month: str | None = None, chatbot: str | None = None,
                q: str | None = None, limit: int = 50, offset: int = 0):
        if status and status not in {"pending", "processing", "ok", "empty", "failed"}:
            raise HTTPException(400, "status không hợp lệ")
        return store_call(lambda s: stats.list_answers(
            s, status=status, target_month=month, chatbot=chatbot, search=q, limit=limit, offset=offset))

    @router.get("/answers/{answer_id}")
    def answer(answer_id: str):
        detail = store_call(lambda s: stats.answer_detail(s, answer_id))
        if detail is None:
            raise HTTPException(404, "Không có answer này.")
        return detail

    @router.get("/claims")
    def claims(month: str | None = None, flag: str | None = None, property_type: str | None = None,
               q: str | None = None, limit: int = 50, offset: int = 0):
        return store_call(lambda s: stats.list_claims(
            s, target_month=month, flag=flag, property_type=property_type, search=q,
            limit=limit, offset=offset))

    @router.get("/runs")
    def runs(limit: int = 30):
        return store_call(lambda s: stats.list_runs(s, max(1, min(limit, 200))))

    @router.get("/input-errors")
    def input_errors(limit: int = 100):
        return store_call(lambda s: stats.list_input_errors(s, max(1, min(limit, 500))))

    @router.get("/export")
    def export(format: Literal["csv", "jsonl"] = "csv", month: str | None = None):
        path = _guarded(lambda: service.export(format, month))
        return FileResponse(path, filename=path.name)

    @post.post("/run")
    def run(body: RunBody):
        return _guarded(lambda: service.run_async("ui", limit=body.limit, rescan=body.rescan))

    @post.post("/stop")
    def stop():
        return service.stop_run()

    @post.post("/retry-failed")
    def retry_failed():
        return _guarded(service.retry_failed)

    @post.post("/reprocess")
    def reprocess(body: ReprocessBody):
        return _guarded(lambda: service.reprocess(
            statuses=list(body.statuses), answer_ids=body.answer_ids, target_month=body.target_month,
            crawl_run_id=body.crawl_run_id, stale=body.stale, run=body.run))

    @post.post("/auto")
    def auto(body: AutoBody):
        if not service.config.ui.allow_mode_switch:
            raise HTTPException(403, "Config không cho đổi chế độ từ UI (ui.allow_mode_switch=false).")
        return service.set_auto(body.enabled)

    router.include_router(post)
    return router


def mount_module2(app: FastAPI, config: Config, runner: Runner | None = None) -> OpsService:
    """Add module 2 (page, assets, API) and the module 1 usage endpoint to `app`."""
    service = OpsService(config, runner)
    app.state.service = service
    app.include_router(build_router(service))
    app.mount("/extract-assets", StaticFiles(directory=STATIC), name="extract-assets")

    @app.get("/extract-claims", include_in_schema=False)
    def extract_claims_page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/v1/research-answers/usage", tags=["research-answers"])
    def research_usage(period: str | None = Query(default=None, pattern=_MONTH)):
        return _guarded(lambda: service.module1_usage(period))

    service.start()
    return service


def create_app(config: Config, runner: Runner | None = None) -> FastAPI:
    """The combined app served by `python -m pipeline ui` (module 1 UI + module 2 tab)."""
    from wardprice.api import create_app as create_module1_app

    app = create_module1_app()
    mount_module2(app, config, runner)
    return app
