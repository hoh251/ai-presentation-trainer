import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from .config import Settings
from .contract import check
from .coverage_service import CoverageService
from .db import Store
from .errors import APIError
from .gemini_service import GeminiService
from .pdf_service import extract_pages
from .question_service import QuestionService
from .session_service import SessionService


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    deck_id: str = Field(min_length=1)
    difficulty: Literal["basic", "standard", "challenge"]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question_id: str = Field(min_length=1)
    attempt_id: str
    state_version: StrictInt = Field(ge=0)
    answer: str = Field(min_length=1)

    @field_validator("attempt_id")
    @classmethod
    def uuid_value(cls, value):
        UUID(value)
        return value  # Preserve exact request for idempotent replay.

    @field_validator("answer")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Answer cannot be blank")
        return value


def create_app(settings=None, *, model=None, questions=None, provider_transport=None, frontend_dist=None):
    settings = settings or Settings.from_env()
    store = Store(settings.storage)
    coverage = model or CoverageService(settings)

    @asynccontextmanager
    async def lifespan(app):
        try:
            store.migrate()
        except (sqlite3.Error, OSError):
            pass  # /ready remains available with database_ready=false.
        await asyncio.to_thread(coverage.load)
        async with httpx.AsyncClient(timeout=settings.provider_timeout, transport=provider_transport, follow_redirects=False) as client:
            gemini = GeminiService(settings, client)
            question_service = questions or QuestionService(settings, store, gemini, coverage)
            app.state.store, app.state.model, app.state.questions = store, coverage, question_service
            app.state.service = SessionService(store, coverage, question_service)
            yield

    app = FastAPI(title="AI Presentation Trainer Backend", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(APIError)
    async def api_error(_, exc):
        return JSONResponse(status_code=exc.status, content=dict(status="error", error=dict(code=exc.code, message=exc.message)), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_, exc):
        return JSONResponse(status_code=422, content=dict(status="error", error=dict(code="REQUEST_INVALID", message="รูปแบบคำขอไม่ถูกต้อง")))

    @app.exception_handler(HTTPException)
    async def http_error(_, exc):
        return JSONResponse(status_code=exc.status_code, content=dict(status="error", error=dict(code=f"HTTP_{exc.status_code}", message="ไม่พบเส้นทางหรือไม่รองรับคำขอนี้")))

    @app.exception_handler(sqlite3.Error)
    async def database_error(_, exc):
        return JSONResponse(status_code=503, content=dict(status="error", error=dict(code="DATABASE_UNAVAILABLE", message="ฐานข้อมูลยังไม่พร้อม กรุณาลองใหม่")))

    async def bounded(coroutine):
        try:
            async with asyncio.timeout(settings.deadline_seconds):
                return await coroutine
        except TimeoutError as exc:
            raise APIError(503, "AI_TIMEOUT", "AI ใช้เวลานานเกินกำหนด กรุณาลองใหม่ด้วยคำขอเดิม") from exc

    @app.get("/api/ready")
    async def ready(request: Request):
        db_ready = request.app.state.store.ready()
        model_ready = request.app.state.model.ready
        q_ready = request.app.state.questions.ready
        ok = db_ready and model_ready and q_ready
        body = dict(status="ok" if ok else "unavailable", contract_version=1, database_ready=db_ready,
                    model_ready=model_ready, question_service_ready=q_ready, model_source=coverage.source,
                    model_version=coverage.version)
        check(body, "readiness")
        code = getattr(coverage, "load_error_code", None)
        return JSONResponse(status_code=200 if ok else 503, content=body, headers={"X-Model-Error": code} if not model_ready and code else {})

    @app.post("/api/decks")
    async def upload(file: UploadFile = File(...)):
        try:
            content = await file.read(settings.max_pdf_bytes + 1)
        finally:
            await file.close()
        if len(content) > settings.max_pdf_bytes:
            raise APIError(413, "PDF_TOO_LARGE", "รองรับไฟล์ PDF ไม่เกิน 15 MB")
        pages = await asyncio.to_thread(extract_pages, content)
        deck_id = str(uuid4())
        path = settings.storage / "pdfs" / f"{deck_id}.pdf"
        filename = Path((file.filename or "slides.pdf").replace("\\", "/")).name or "slides.pdf"
        try:
            path.write_bytes(content)
            store.save_deck(deck_id, filename, pages, path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        result = dict(status="ok", contract_version=1, deck_id=deck_id, filename=filename, page_count=len(pages))
        check(result, "deck_upload")
        return result

    @app.get("/api/decks/{deck_id}/file")
    async def pdf_file(deck_id: str):
        deck = store.deck(deck_id)
        path = Path(deck["pdf_path"])
        if not path.is_file():
            raise APIError(404, "PDF_NOT_FOUND", "ไม่พบไฟล์ PDF")
        return FileResponse(path, media_type="application/pdf", filename=deck["filename"], content_disposition_type="inline")

    @app.post("/api/sessions")
    async def start(body: StartRequest, request: Request):
        return await bounded(request.app.state.service.start(body.model_dump()))

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        state, _ = store.session(session_id)
        return state

    @app.post("/api/sessions/{session_id}/answers")
    async def answer(session_id: str, body: AnswerRequest, request: Request):
        return await bounded(request.app.state.service.answer(session_id, body.model_dump()))

    @app.get("/api/sessions/{session_id}/report")
    async def report(session_id: str, request: Request):
        return request.app.state.service.report(session_id)

    # API catch-all is registered before static hosting, keeping API errors JSON.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def unknown_api(path: str):
        raise APIError(404, "ROUTE_NOT_FOUND", "ไม่พบ API นี้")

    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=Path(frontend_dist), html=True), name="frontend")
    return app


app = create_app()
