"""FastAPI surface of module 1: sourced Q&A research (Tavily search + OpenAI-compatible summary)."""

from __future__ import annotations

from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


UI_DIR = Path(__file__).resolve().parent / "static"


class ResearchAnswersPrepareRequest(BaseModel):
    period: str = Field(min_length=7, max_length=7)
    province: str | None = Field(default=None, min_length=1, max_length=120)
    administrative_code: str | None = Field(default=None, min_length=1, max_length=20)


class ResearchAnswersRunRequest(BaseModel):
    period: str = Field(min_length=7, max_length=7)
    limit: int = Field(default=5, ge=1, le=20)
    retry_failed: bool = False
    confirm_live: bool = False


def create_app() -> FastAPI:
    app = FastAPI(
        title="Module 1 - sourced real-estate Q&A research",
        version="1.0.0",
    )
    app.mount("/assets", StaticFiles(directory=UI_DIR), name="dashboard-assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(UI_DIR / "research-answers.html")

    @app.get("/research-answers", include_in_schema=False)
    def research_answers_dashboard() -> FileResponse:
        return FileResponse(UI_DIR / "research-answers.html")

    @app.get("/api/v1/research-answers/provinces", tags=["research-answers"])
    def research_answer_provinces() -> dict[str, Any]:
        from .research_answers import list_provinces

        try:
            return {"provinces": list_provinces()}
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/research-answers/config", tags=["research-answers"])
    def research_answers_config() -> dict[str, Any]:
        from .config import ResearchAPISettings

        settings = ResearchAPISettings.from_env()
        return {
            "model": settings.model,
            "model_api_configured": bool(settings.model_api_key),
            "base_url_configured": bool(settings.model_base_url),
            "search_api_configured": bool(settings.search_api_key),
            "ready": bool(
                settings.model_api_key and settings.model_base_url and settings.search_api_key
            ),
            "search_provider": "Tavily",
        }

    @app.get("/api/v1/research-answers/targets", tags=["research-answers"])
    def research_answer_targets(
        province: str | None = Query(default=None, max_length=120),
    ) -> dict[str, Any]:
        from .research_answers import load_administrative_units

        try:
            targets = load_administrative_units(province=province)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"count": len(targets), "targets": targets}

    @app.get("/api/v1/research-answers/status", tags=["research-answers"])
    def research_answers_status(
        period: str = Query(min_length=7, max_length=7),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        from .research_answers import DEFAULT_RESEARCH_DB, research_status

        try:
            return research_status(
                period,
                database_path=DEFAULT_RESEARCH_DB,
                offset=offset,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/research-answers/prepare", tags=["research-answers"])
    def prepare_research_answers(request: ResearchAnswersPrepareRequest) -> dict[str, Any]:
        from .research_answers import prepare_jobs

        try:
            return prepare_jobs(
                request.period,
                province=request.province,
                administrative_code=request.administrative_code,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/research-answers/run", tags=["research-answers"])
    def run_research_answers(request: ResearchAnswersRunRequest) -> dict[str, Any]:
        if not request.confirm_live:
            raise HTTPException(
                status_code=400,
                detail="Cần xác nhận rõ trước khi tìm web và gọi model tóm tắt.",
            )
        from .research_answers import run_batch

        try:
            return run_batch(
                request.period,
                limit=request.limit,
                retry_failed=request.retry_failed,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Lượt tìm kiếm và tóm tắt chưa hoàn tất; xem trạng thái job để đọc chẩn đoán đã ẩn thông tin nhạy cảm.",
            ) from exc

    @app.get("/api/v1/research-answers/export", tags=["research-answers"])
    def download_research_answers(period: str = Query(min_length=7, max_length=7)) -> FileResponse:
        from .research_answers import DEFAULT_JSONL_DIR, _validate_period

        try:
            period = _validate_period(period)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        path = DEFAULT_JSONL_DIR / f"gemma_answers_{period}.jsonl"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Chưa có file JSONL cho kỳ này.")
        return FileResponse(path, media_type="application/x-ndjson", filename=path.name)

    return app


app = create_app()
