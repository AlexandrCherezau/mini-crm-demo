"""FastAPI app: REST API for leads + static single-page frontend."""
from __future__ import annotations

import hmac
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import repo
from .db import BASE_DIR, MANAGERS, SOURCES, STATUSES, init_db, session
from .schemas import CommentCreate, LeadCreate, LeadPatch, Source, Status, StatusChange, WebhookLead
from .stats import compute_stats

STATIC_DIR = BASE_DIR / "static"
WEBHOOK_LIMIT_PER_MIN = int(os.environ.get("WEBHOOK_LIMIT_PER_MIN", "30"))
MAX_WEBHOOK_BODY = 16_384

_hits: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Мини-CRM для заявок", version="1.0.0", lifespan=lifespan)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Заявка не найдена")


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {"statuses": STATUSES, "sources": SOURCES, "managers": list(MANAGERS)}


@app.get("/api/leads")
def leads_list(
    status: Optional[Status] = None,
    source: Optional[Source] = None,
    manager: Optional[str] = Query(default=None, max_length=80),
    q: Optional[str] = Query(default=None, max_length=100),
) -> list[dict[str, Any]]:
    with session() as conn:
        return repo.list_leads(conn, status, source, manager, (q or "").strip() or None)


@app.post("/api/leads", status_code=201)
def leads_create(body: LeadCreate) -> dict[str, Any]:
    with session() as conn:
        return repo.create_lead(conn, body.model_dump(), author="Менеджер", note="Создана вручную")


@app.get("/api/leads/{lead_id}")
def leads_get(lead_id: int) -> dict[str, Any]:
    with session() as conn:
        lead = repo.get_lead(conn, lead_id)
        if lead is None:
            raise _not_found()
        return {**lead, "history": repo.lead_history(conn, lead_id)}


@app.patch("/api/leads/{lead_id}/status")
def leads_status(lead_id: int, body: StatusChange) -> dict[str, Any]:
    with session() as conn:
        lead = repo.change_status(conn, lead_id, body.status, body.author)
        if lead is None:
            raise _not_found()
        return lead


@app.patch("/api/leads/{lead_id}")
def leads_patch(lead_id: int, body: LeadPatch) -> dict[str, Any]:
    with session() as conn:
        lead = repo.patch_lead(conn, lead_id, body.amount, body.manager, body.author)
        if lead is None:
            raise _not_found()
        return lead


@app.post("/api/leads/{lead_id}/comments", status_code=201)
def leads_comment(lead_id: int, body: CommentCreate) -> dict[str, Any]:
    with session() as conn:
        if not repo.add_comment(conn, lead_id, body.text, body.author):
            raise _not_found()
        return {"ok": True, "history": repo.lead_history(conn, lead_id)}


@app.get("/api/stats")
def stats(weeks: int = Query(default=10, ge=2, le=52)) -> dict[str, Any]:
    with session() as conn:
        return compute_stats(conn, weeks)


@app.get("/api/webhook/log")
def webhook_log(after_id: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    with session() as conn:
        return repo.webhook_log(conn, after_id)


# --- public webhook -------------------------------------------------------

def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= WEBHOOK_LIMIT_PER_MIN:
        return True
    window.append(now)
    return False


def _parse_body(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if "application/x-www-form-urlencoded" in content_type:
        return {k: v[0] for k, v in parse_qs(text).items()}
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError("ожидается JSON-объект")
    return data


def _token_ok(request: Request) -> bool:
    expected = os.environ.get("WEBHOOK_TOKEN")
    if not expected:
        return True
    given = request.headers.get("x-webhook-token", "")
    return hmac.compare_digest(given.encode(), expected.encode())


_ERROR_RU = {
    "missing": "обязательное поле",
    "string_too_short": "слишком короткое значение",
    "string_too_long": "слишком длинное значение",
    "literal_error": "недопустимое значение",
    "int_parsing": "ожидается целое число",
    "greater_than_equal": "значение меньше допустимого",
    "less_than_equal": "значение больше допустимого",
}


def _describe(exc: ValidationError) -> str:
    err = exc.errors()[0]
    field = ".".join(str(part) for part in err.get("loc", ())) or "тело запроса"
    return f"{field}: {_ERROR_RU.get(err.get('type', ''), err.get('msg', 'ошибка'))}"


def _reject(ip: str, raw: str, code: int, error: str) -> JSONResponse:
    with session() as conn:
        repo.log_webhook(conn, ip, raw, code, error=error)
    return JSONResponse(status_code=code, content={"ok": False, "error": error})


@app.post("/api/webhook/lead")
async def webhook_lead(request: Request) -> JSONResponse:
    """Public endpoint a site form posts to. Accepts JSON or form-urlencoded."""
    ip = request.client.host if request.client else "unknown"
    raw = await request.body()
    raw_text = raw[:MAX_WEBHOOK_BODY].decode("utf-8", errors="replace")
    if len(raw) > MAX_WEBHOOK_BODY:
        return _reject(ip, raw_text, 413, "слишком большой запрос")
    if _rate_limited(ip):
        return _reject(ip, raw_text, 429, "слишком много запросов")
    if not _token_ok(request):
        return _reject(ip, raw_text, 401, "неверный токен")
    try:
        payload = WebhookLead(**_parse_body(raw, request.headers.get("content-type", "")))
    except (ValueError, ValidationError) as exc:
        detail = _describe(exc) if isinstance(exc, ValidationError) else str(exc)
        return _reject(ip, raw_text, 422, f"некорректные данные: {detail}")

    data = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "request": payload.message,
        "source": payload.source,
        "amount": payload.budget,
    }
    with session() as conn:
        lead = repo.create_lead(conn, data, author="Webhook", note=f"Получена через webhook ({ip})")
        repo.log_webhook(conn, ip, raw_text, 201, lead_id=lead["id"])
    return JSONResponse(status_code=201, content={"ok": True, "lead_id": lead["id"]})


# --- frontend -------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
