from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import os
import threading
import time
from typing import Dict
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.v3 import V3_API_VERSION, router as v3_router


MAX_BODY_BYTES = int(os.getenv("NTS_MAX_BODY_BYTES", "95000"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("NTS_RATE_LIMIT_PER_MINUTE", "120"))

app = FastAPI(
    title="NTS Spanish Translator Blueprint V3 API",
    version=V3_API_VERSION,
    description=(
        "Blueprint V3-only localization orchestration, deterministic validation, "
        "immutable evidence, and human-governed publication controls."
    ),
)
app.include_router(v3_router)

_rate_windows: Dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "request_id": str(uuid.uuid4()),
            "error": {"code": code, "message": message},
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException):
    response = _error(exc.status_code, "http_error", str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request: Request, exc: RequestValidationError):
    message = "; ".join(error.get("msg", "Invalid request") for error in exc.errors()[:5])
    return _error(422, "request_validation_error", message)


def _client_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    raw = authorization or (request.client.host if request.client else "unknown")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@app.middleware("http")
async def v3_guardrails(request: Request, call_next):
    if request.url.path.startswith("/v3/"):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
            return _error(413, "payload_too_large", f"Request body exceeds {MAX_BODY_BYTES} bytes")
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > MAX_BODY_BYTES:
                return _error(413, "payload_too_large", f"Request body exceeds {MAX_BODY_BYTES} bytes")
        key, now = _client_key(request), time.monotonic()
        with _rate_lock:
            window = _rate_windows[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= RATE_LIMIT_PER_MINUTE:
                response = _error(429, "rate_limited", "Too many requests; retry after 60 seconds")
                response.headers["Retry-After"] = "60"
                return response
            window.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz", operation_id="healthCheckV3")
async def healthz():
    return {
        "status": "ok",
        "service": "nts-spanish-translator-blueprint-v3",
        "version": V3_API_VERSION,
        "runtime_contract": "V3_ONLY",
    }
