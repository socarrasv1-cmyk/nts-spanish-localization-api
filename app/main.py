from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.git_stage import GitStaging, GitStagingError
from app.security import verify_bearer_token
from app.store import store
from app.tm import TranslationMemory
from app.validators import (
    ValidationResult, score_validation_results, validate_english_residue,
    validate_links, validate_php, validate_protected_tokens, validate_schema,
    validate_structure,
)


API_VERSION = "2.2.0"
MAX_BODY_BYTES = int(os.getenv("NTS_MAX_BODY_BYTES", "95000"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("NTS_RATE_LIMIT_PER_MINUTE", "120"))

app = FastAPI(
    title="NTS Localization API", version=API_VERSION,
    description="Evidence-based Spanish localization validation and staging for NTS",
)
tm_service = TranslationMemory()
git_service = GitStaging()
_rate_windows: Dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()

SITE_ID_ALIASES = {
    "het": "het-main", "het-main": "het-main",
    "nts": "nts-main", "nts-main": "nts-main",
}
DEFAULT_URL_MAPPINGS = [{
    "source_url": "/services/break-bulk-transport.php",
    "spanish_url": "/es/servicios/transporte-de-carga-fraccionada.php",
    "site_id": "het-main", "approved": True, "status": "approved",
}]
DEFAULT_SITES = [
    {
        "site_id": "nts-main", "brand_name": "Nationwide Transport Services",
        "domain": "https://www.nationwidetransportservices.com", "status": "verified",
    },
    {
        "site_id": "het-main", "brand_name": "Heavy Equipment Transport",
        "domain": "https://www.heavyequipmenttransport.com", "status": "verified",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id() -> str:
    return str(uuid.uuid4())


def _success(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={
        "ok": True, "request_id": _request_id(), "data": data,
    })


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={
        "ok": False, "request_id": _request_id(),
        "error": {"code": code, "message": message},
    })


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


def _required(payload: Dict[str, Any], name: str, *aliases: str) -> Any:
    value = next((payload.get(key) for key in (name, *aliases) if payload.get(key) is not None), None)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise HTTPException(status_code=422, detail=f"{name} is required")
    return value


def normalize_site_id(site_id: Optional[str]) -> str:
    normalized = (site_id or "").strip().lower()
    return SITE_ID_ALIASES.get(normalized, normalized)


def _client_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    raw = authorization or (request.client.host if request.client else "unknown")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@app.middleware("http")
async def production_guardrails(request: Request, call_next):
    if request.url.path.startswith("/v2/"):
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


def _mappings() -> List[Dict[str, Any]]:
    data = store.load("url_map")
    return list(data.get("url_mappings") or data.get("mappings") or []) + DEFAULT_URL_MAPPINGS


def find_approved_url_mapping(site_id: str, source_url: str) -> Optional[Dict[str, Any]]:
    requested_site, requested_source = normalize_site_id(site_id), (source_url or "").strip()
    for mapping in _mappings():
        source = mapping.get("source_url") or mapping.get("english_url")
        approved = mapping.get("approved") is True or str(mapping.get("status", "")).lower() == "approved"
        if normalize_site_id(mapping.get("site_id")) == requested_site and source == requested_source and approved:
            return {
                "source_url": source, "spanish_url": mapping.get("spanish_url"),
                "site_id": requested_site, "approved": True,
                "approved_by": mapping.get("approved_by"), "approved_at": mapping.get("approved_at"),
            }
    return None


def _artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    artifact = store.load("artifacts").get("artifacts", {}).get(artifact_id)
    if artifact and artifact.get("expires_at"):
        if datetime.fromisoformat(artifact["expires_at"]) <= datetime.now(timezone.utc):
            def remove(data):
                data.setdefault("artifacts", {}).pop(artifact_id, None)
            store.mutate("artifacts", remove)
            return None
    return artifact


def _content(payload: Dict[str, Any], direct: str, artifact_key: str) -> str:
    if payload.get(direct) is not None:
        return str(payload[direct])
    artifact_id = payload.get(artifact_key)
    artifact = _artifact(artifact_id) if artifact_id else None
    return str(artifact.get("content", "")) if artifact else ""


def _save_artifact(job_id: str, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    content = str(payload.get("content") or payload.get("html_content") or "")
    if not content:
        raise HTTPException(status_code=422, detail="content is required")
    created_at = datetime.now(timezone.utc)
    ttl_hours = max(1, int(os.getenv("NTS_ARTIFACT_TTL_HOURS", "168")))
    artifact = {
        "artifact_id": str(uuid.uuid4()), "job_id": job_id, "kind": kind,
        "content": content, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "bytes": len(content.encode("utf-8")), "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(hours=ttl_hours)).isoformat(),
        "metadata": payload.get("metadata", {}),
    }

    def save(data):
        data.setdefault("artifacts", {})[artifact["artifact_id"]] = artifact

    store.mutate("artifacts", save)
    return artifact


def _get_job_or_404(job_id: str) -> Dict[str, Any]:
    job = store.load("jobs").get("jobs", {}).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


def _run_page_qa(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_html = _content(payload, "source_html", "english_artifact_id")
    target_html = _content(payload, "target_html", "spanish_artifact_id")
    target_url = payload.get("target_url") or payload.get("spanish_url")
    checks: Dict[str, ValidationResult] = {
        "php": validate_php(target_html),
        "structure": validate_structure(source_html, target_html),
        "protected_tokens": validate_protected_tokens(source_html, target_html, payload.get("token_patterns")),
        "english_residue": validate_english_residue(target_html),
        "schema": validate_schema(target_html, target_url),
        "links": validate_links(target_html, target_url),
    }
    scored = score_validation_results(checks)
    scored["checks"] = {name: result.as_dict() for name, result in checks.items()}
    scored["source_url"] = payload.get("source_url") or payload.get("english_url")
    scored["target_url"] = target_url
    return scored


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "nts-localization-api", "version": API_VERSION}


@app.get("/v2/sites")
async def sites(authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    combined = list(store.load("sites").get("sites", [])) + DEFAULT_SITES
    unique = {normalize_site_id(site.get("site_id")): site for site in reversed(combined)}
    return _success({"sites": list(unique.values())})


@app.post("/v2/jobs", status_code=201)
async def create_job(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    site_id = normalize_site_id(_required(payload, "site_id"))
    job = {
        "job_id": str(uuid.uuid4()), "site_id": site_id,
        "english_url": _required(payload, "english_url", "source_url"),
        "page_family": payload.get("page_family"), "mode": payload.get("mode", "strict_mirror"),
        "locale": payload.get("locale", "es-US"), "state": "CREATED",
        "artifact_ids": [], "created_at": _now(), "updated_at": _now(),
    }
    store.mutate("jobs", lambda data: data.setdefault("jobs", {}).__setitem__(job["job_id"], job))
    return _success(job, 201)


@app.get("/v2/jobs/{job_id}")
async def get_job(job_id: str, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(_get_job_or_404(job_id))


@app.delete("/v2/jobs/{job_id}")
async def close_job(job_id: str, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    job = _get_job_or_404(job_id)
    job.update({"state": "CLOSED", "closed_at": _now(), "updated_at": _now()})
    store.mutate("jobs", lambda data: data.setdefault("jobs", {}).__setitem__(job_id, job))
    return _success({"job_id": job_id, "status": "closed"})


async def _create_job_artifact(job_id: str, kind: str, payload: Dict[str, Any], authorization: Optional[str]):
    verify_bearer_token(authorization)
    job = _get_job_or_404(job_id)
    if job.get("state") == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed jobs cannot accept artifacts")
    artifact = _save_artifact(job_id, kind, payload)
    job.setdefault("artifact_ids", []).append(artifact["artifact_id"])
    job.update({"state": "SOURCE_IMPORTED" if kind == "english_source" else "DRAFT_CREATED", "updated_at": _now()})
    store.mutate("jobs", lambda data: data.setdefault("jobs", {}).__setitem__(job_id, job))
    return _success({key: value for key, value in artifact.items() if key != "content"}, 201)


@app.post("/v2/jobs/{job_id}/source/import", status_code=201)
async def source_import(job_id: str, payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    return await _create_job_artifact(job_id, "english_source", payload, authorization)


@app.post("/v2/jobs/{job_id}/drafts", status_code=201)
async def create_draft(job_id: str, payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    return await _create_job_artifact(job_id, "spanish_draft", payload, authorization)


@app.get("/v2/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    artifact = _artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    return _success(artifact)


@app.get("/v2/url-map/approved")
async def url_map_approved(site_id: str, source_url: str, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    mapping = find_approved_url_mapping(site_id, source_url)
    if not mapping:
        raise HTTPException(status_code=404, detail="No approved URL mapping found")
    return _success(mapping)


@app.post("/v2/url-map/get")
async def url_map_get(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    mapping = find_approved_url_mapping(_required(payload, "site_id"),
                                        _required(payload, "source_url", "english_url"))
    if not mapping:
        raise HTTPException(status_code=404, detail="No approved URL mapping found")
    return _success(mapping)


@app.post("/v2/url-map/validate")
async def url_map_validate(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    site_id = normalize_site_id(_required(payload, "site_id"))
    source = str(payload.get("source_url") or payload.get("english_url") or "").strip()
    candidate = str(_required(payload, "candidate", "candidate_url", "spanish_url")).strip()
    issues: List[Dict[str, Any]] = []
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        issues.append({"code": "URL_NOT_CLEAN_PATH", "severity": "error", "message": "Candidate must be a path without host, query, or fragment."})
    if not candidate.startswith("/es/"):
        issues.append({"code": "URL_ES_PREFIX_REQUIRED", "severity": "error", "message": "Spanish URL must begin with /es/."})
    if (candidate != candidate.lower() or "//" in candidate or candidate.endswith("/") or
            not re.fullmatch(r"/[a-z0-9/_-]+(?:\.php)?", candidate)):
        issues.append({"code": "URL_FORMAT_INVALID", "severity": "error", "message": "Use lowercase ASCII slugs, hyphens, and an optional .php suffix."})
    if source and source.endswith(".php") != candidate.endswith(".php"):
        issues.append({"code": "URL_EXTENSION_MISMATCH", "severity": "error", "message": "Source and target must preserve the .php routing convention."})
    collisions = []
    for mapping in _mappings():
        mapping_source = mapping.get("source_url") or mapping.get("english_url")
        if normalize_site_id(mapping.get("site_id")) == site_id and mapping.get("spanish_url") == candidate and mapping_source != source:
            collisions.append(mapping_source)
    if collisions:
        issues.append({"code": "URL_COLLISION", "severity": "error", "message": "Candidate is already assigned to another source URL.", "details": {"source_urls": sorted(set(collisions))}})
    result = ValidationResult("FAIL" if issues else "PASS", bool(issues), issues, {
        "validator": "url_candidate", "version": "2.2", "site_id": site_id,
        "source_url": source or None, "candidate": candidate,
    })
    return _success(result.as_dict())


@app.post("/v2/validate/php")
async def val_php(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_php(_content(payload, "php_code", "artifact_id")).as_dict())


@app.post("/v2/validate/structure")
async def val_structure(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_structure(_content(payload, "source_html", "english_artifact_id"),
                                       _content(payload, "target_html", "spanish_artifact_id")).as_dict())


@app.post("/v2/validate/protected-tokens")
async def val_tokens(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_protected_tokens(
        _content(payload, "source_content", "english_artifact_id"),
        _content(payload, "target_content", "spanish_artifact_id"), payload.get("token_patterns")
    ).as_dict())


@app.post("/v2/validate/english-residue")
async def val_residue(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_english_residue(_content(payload, "target_content", "artifact_id")).as_dict())


@app.post("/v2/validate/schema")
async def val_schema(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_schema(_content(payload, "html_content", "spanish_artifact_id"),
                                    payload.get("target_url") or payload.get("spanish_url")).as_dict())


@app.post("/v2/validate/links")
async def val_links(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(validate_links(_content(payload, "html_content", "spanish_artifact_id"),
                                   payload.get("target_url") or payload.get("spanish_url")).as_dict())


@app.post("/v2/qa/page")
async def qa_page(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    result = _run_page_qa(payload)
    job_id = payload.get("job_id")
    if job_id:
        job = _get_job_or_404(job_id)
        job.update({"state": result["status"], "qa": result, "updated_at": _now()})
        store.mutate("jobs", lambda data: data.setdefault("jobs", {}).__setitem__(job_id, job))
    return _success(result)


@app.post("/v2/qa/batch")
async def qa_batch(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    pages = payload.get("pages", [])
    if not isinstance(pages, list) or not pages:
        raise HTTPException(status_code=422, detail="pages must contain at least one page")
    results = [_run_page_qa(page) for page in pages]
    targets = [result.get("target_url") for result in results if result.get("target_url")]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    blocker_count = sum(len(result["blocking_issues"]) for result in results)
    score = round(sum(result["score"] for result in results) / len(results))
    status = "BLOCKED" if blocker_count or duplicates else "READY" if score >= 95 else "NEEDS_REVIEW"
    return _success({
        "status": status, "score": score, "page_count": len(results),
        "duplicate_targets": duplicates, "blocker_count": blocker_count,
        "pages": results,
    })


@app.post("/v2/staging/packages", status_code=201)
async def create_package(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(status_code=422, detail="job_ids must contain at least one job")
    blocked = []
    for job_id in job_ids:
        job = _get_job_or_404(job_id)
        if job.get("state") != "READY":
            blocked.append(job_id)
    if blocked:
        return _success({"status": "BLOCKED", "included_jobs": [], "blocked_jobs": blocked})
    manifest = {"job_ids": job_ids, "created_at": _now(), "kind": "staging_package"}
    artifact = _save_artifact("package", "staging_package", {
        "content": json.dumps(manifest, ensure_ascii=False, sort_keys=True), "metadata": manifest,
    })
    return _success({
        "package_id": str(uuid.uuid4()), "artifact_id": artifact["artifact_id"],
        "status": "PACKAGE_READY", "included_jobs": job_ids, "blocked_jobs": [],
    }, 201)


@app.get("/v2/tm/search")
async def tm_search_get(source: str, locale: str = "es-US", site_id: Optional[str] = None,
                        component: Optional[str] = None, authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    try:
        matches = tm_service.search(source, locale, normalize_site_id(site_id) if site_id else None, component)
        return _success({"matches": matches, "count": len(matches)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v2/tm/search")
async def tm_search(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    matches = tm_service.search(_required(payload, "source"), payload.get("locale", "es-US"),
                                normalize_site_id(payload.get("site_id")) if payload.get("site_id") else None,
                                payload.get("component"))
    return _success({"matches": matches, "count": len(matches)})


@app.post("/v2/tm/propose", status_code=201)
@app.post("/v2/tm/proposals", status_code=201)
async def tm_propose(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    try:
        proposal = tm_service.propose(
            payload.get("source"), payload.get("translation"),
            normalize_site_id(payload.get("site_id")) if payload.get("site_id") else None,
            payload.get("component"), payload.get("context"), payload.get("locale", "es-US"),
            payload.get("notes"),
        )
        return _success(proposal, 201)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "Duplicate" in str(exc) else 422, detail=str(exc)) from exc


@app.get("/v2/tm/proposals")
async def tm_proposals(status: str = "proposed", authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    try:
        return _success({"proposals": tm_service.list_proposals(status)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _review_proposal(proposal_id: str, payload: Optional[Dict[str, Any]],
                           authorization: Optional[str], decision: str):
    verify_bearer_token(authorization)
    request_data = payload or {}
    try:
        method = tm_service.approve_proposal if decision == "approve" else tm_service.reject_proposal
        return _success(method(proposal_id, request_data.get("reviewer", "NTS Spanish Translator"),
                               request_data.get("reason")))
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 409
        return _error(status_code, "proposal_review_error", str(exc))


@app.post("/v2/tm/approve/{proposal_id}")
@app.post("/v2/tm/proposals/{proposal_id}/approve")
async def tm_approve(proposal_id: str, payload: Optional[Dict[str, Any]] = None,
                     authorization: Optional[str] = Header(None)):
    return await _review_proposal(proposal_id, payload, authorization, "approve")


@app.post("/v2/tm/reject/{proposal_id}")
@app.post("/v2/tm/proposals/{proposal_id}/reject")
async def tm_reject(proposal_id: str, payload: Optional[Dict[str, Any]] = None,
                    authorization: Optional[str] = Header(None)):
    return await _review_proposal(proposal_id, payload, authorization, "reject")


@app.get("/v2/git/status")
async def git_status(authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _success(git_service.get_status())


def _git_response(call):
    try:
        return _success(call())
    except GitStagingError as exc:
        return _error(400, "git_error", str(exc))


@app.post("/v2/git/branches")
async def git_branch(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _git_response(lambda: git_service.create_branch(_required(payload, "branch_name"), payload.get("base_branch")))


@app.post("/v2/git/stage")
async def git_stage(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _git_response(lambda: git_service.stage_files(
        _required(payload, "branch_name"), payload.get("files", []), _required(payload, "commit_message")
    ))


@app.post("/v2/git/push")
async def git_push(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _git_response(lambda: git_service.push(_required(payload, "branch_name")))


@app.post("/v2/git/draft-pr")
async def git_draft_pr(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    verify_bearer_token(authorization)
    return _git_response(lambda: git_service.create_draft_pr(
        _required(payload, "branch_name"), payload.get("base_branch", "main"),
        _required(payload, "title"), payload.get("body", ""),
    ))
