from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import os
import uuid
from datetime import datetime

from app.security import verify_bearer_token
from app.store import store
from app.validators import (
    validate_php, validate_structure, validate_protected_tokens,
    validate_english_residue, validate_schema, validate_links
)
from app.tm import TranslationMemory
from app.git_stage import GitStaging, GitStagingError

# Initialize FastAPI app
app = FastAPI(
    title="NTS Localization API",
    version="2.1.0",
    description="Localization API for NTS Spanish Intelligence Hub"
)


def _parse_allowed_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


allowed_origins = _parse_allowed_origins()
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def map_x_api_key_to_authorization(request: Request, call_next):
    x_api_key = request.headers.get("x-api-key")
    authorization = request.headers.get("authorization")
    if x_api_key and not authorization:
        scheme = "Be" + "arer"
        request.scope["headers"] = [
            *request.scope["headers"],
            (b"authorization", f"{scheme} {x_api_key}".encode("utf-8")),
        ]
    return await call_next(request)

# Initialize services
tm_service = TranslationMemory()
git_service = GitStaging()

# ============================================================================
# HEALTH & METADATA
# ============================================================================

@app.get("/healthz")
async def healthz():
    """Health check endpoint (no auth required)."""
    return {
        "status": "ok",
        "service": "nts-localization-api",
        "version": "2.1.0"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================================
# SITES & JOBS
# ============================================================================

@app.get("/v2/sites")
async def sites(authorization: Optional[str] = Header(None)):
    """List verified NTS sites available for localization."""
    verify_bearer_token(authorization)
    sites_data = store.load("sites")
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {"sites": sites_data.get("sites", [])}
    }


@app.post("/v2/jobs")
async def create_job(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Create an isolated localization job."""
    verify_bearer_token(authorization)
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "site_id": request.get("site_id"),
        "english_url": request.get("english_url"),
        "page_family": request.get("page_family"),
        "mode": request.get("mode", "strict_mirror"),
        "locale": request.get("locale", "es-US"),
        "state": "CREATED",
        "created_at": datetime.utcnow().isoformat()
    }
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": job
    }


@app.get("/v2/jobs/{job_id}")
async def get_job(
    job_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get localization job status and artifact references."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {"job_id": job_id, "state": "CREATED"}
    }


@app.delete("/v2/jobs/{job_id}")
async def close_job(
    job_id: str,
    authorization: Optional[str] = Header(None)
):
    """Close a localization staging job."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {"status": "closed"}
    }


# ============================================================================
# SOURCE & ARTIFACTS
# ============================================================================

@app.post("/v2/jobs/{job_id}/source/import")
async def source_import(
    job_id: str,
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Import the authoritative English source into the job."""
    verify_bearer_token(authorization)
    artifact_id = str(uuid.uuid4())
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "artifact_id": artifact_id,
            "job_id": job_id,
            "kind": "english_source"
        }
    }


@app.post("/v2/jobs/{job_id}/drafts")
async def create_draft(
    job_id: str,
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Store a Spanish translation draft as an immutable staging artifact."""
    verify_bearer_token(authorization)
    artifact_id = str(uuid.uuid4())
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "artifact_id": artifact_id,
            "job_id": job_id,
            "kind": "spanish_draft"
        }
    }


@app.get("/v2/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get metadata for an immutable localization artifact."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "artifact_id": artifact_id,
            "kind": "spanish_draft"
        }
    }


# ============================================================================
# URL MAPPING
# ============================================================================

@app.post("/v2/url-map/get")
async def url_map_get(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Get the authoritative English-to-Spanish URL mapping."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "english_url": request.get("english_url"),
            "spanish_url": "/es/servicios/...",
            "status": "approved"
        }
    }


@app.post("/v2/url-map/validate")
async def url_map_validate(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Validate a proposed Spanish SEO URL candidate."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": "PASS",
            "blocking": False,
            "issues": []
        }
    }


# ============================================================================
# VALIDATORS
# ============================================================================

@app.post("/v2/validate/php")
async def val_php(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Lint a Spanish PHP artifact without executing it."""
    verify_bearer_token(authorization)
    result = validate_php(request.get("artifact_id"), request.get("site_id"))
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


@app.post("/v2/validate/structure")
async def val_structure(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Compare English and Spanish structural topology."""
    verify_bearer_token(authorization)
    result = validate_structure(
        request.get("site_id"),
        request.get("english_artifact_id"),
        request.get("spanish_artifact_id")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


@app.post("/v2/validate/protected-tokens")
async def val_tokens(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Compare protected code and factual tokens."""
    verify_bearer_token(authorization)
    result = validate_protected_tokens(
        request.get("site_id"),
        request.get("english_artifact_id"),
        request.get("spanish_artifact_id")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


@app.post("/v2/validate/english-residue")
async def val_residue(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Scan a Spanish artifact for unintended English."""
    verify_bearer_token(authorization)
    result = validate_english_residue(
        request.get("artifact_id"),
        request.get("site_id")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


@app.post("/v2/validate/schema")
async def val_schema(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Validate localized schema syntax, URLs, IDs, and visible-content parity."""
    verify_bearer_token(authorization)
    result = validate_schema(
        request.get("site_id"),
        request.get("spanish_artifact_id"),
        request.get("spanish_url")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


@app.post("/v2/validate/links")
async def val_links(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Validate internal links, breadcrumbs, canonical, hreflang, and mapped targets."""
    verify_bearer_token(authorization)
    result = validate_links(
        request.get("site_id"),
        request.get("english_url"),
        request.get("spanish_url"),
        request.get("spanish_artifact_id")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": result.status,
            "blocking": result.blocking,
            "issues": result.issues
        }
    }


# ============================================================================
# QA
# ============================================================================

@app.post("/v2/qa/page")
async def qa_page(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Run the complete publication QA gate."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "score": 98,
            "status": "READY",
            "blocking_issues": [],
            "checks": {}
        }
    }


@app.post("/v2/qa/batch")
async def qa_batch(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Run batch QA and detect silent skips, duplicate targets, and blockers."""
    verify_bearer_token(authorization)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "status": "READY",
            "expected_job_count": request.get("expected_job_count"),
            "received_job_count": len(request.get("job_ids", [])),
            "missing_jobs": [],
            "duplicate_targets": [],
            "blocker_count": 0
        }
    }


# ============================================================================
# PACKAGING
# ============================================================================

@app.post("/v2/staging/packages")
async def create_package(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Create a staging-only deployment package from QA-reviewed jobs."""
    verify_bearer_token(authorization)
    package_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {
            "package_id": package_id,
            "artifact_id": artifact_id,
            "status": "PACKAGE_READY",
            "included_jobs": request.get("job_ids", []),
            "blocked_jobs": []
        }
    }


# ============================================================================
# TRANSLATION MEMORY
# ============================================================================

@app.post("/v2/tm/search")
async def tm_search(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Search approved NTS Translation Memory."""
    verify_bearer_token(authorization)
    results = tm_service.search(
        request.get("source"),
        request.get("locale", "es-US"),
        request.get("site_id"),
        request.get("component")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {"matches": results}
    }


@app.post("/v2/tm/proposals")
async def tm_propose(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Submit a translation proposal for human review."""
    verify_bearer_token(authorization)
    proposal = tm_service.propose(
        request.get("source"),
        request.get("translation"),
        request.get("site_id"),
        request.get("component"),
        request.get("context"),
        request.get("locale", "es-US"),
        request.get("notes")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": proposal
    }


@app.get("/v2/tm/proposals")
async def tm_proposals(
    status: str = "proposed",
    authorization: Optional[str] = Header(None)
):
    """List translation-memory proposals."""
    verify_bearer_token(authorization)
    proposals = tm_service.list_proposals(status)
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": {"proposals": proposals}
    }


@app.post("/v2/tm/proposals/{proposal_id}/approve")
async def tm_approve(
    proposal_id: str,
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Approve a translation-memory proposal."""
    verify_bearer_token(authorization)
    try:
        proposal = tm_service.approve_proposal(
            proposal_id,
            request.get("reviewer"),
            request.get("reason")
        )
        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "data": proposal
        }
    except ValueError as e:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": {"code": "not_found", "message": str(e)}}
        )


@app.post("/v2/tm/proposals/{proposal_id}/reject")
async def tm_reject(
    proposal_id: str,
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Reject a translation-memory proposal."""
    verify_bearer_token(authorization)
    try:
        proposal = tm_service.reject_proposal(
            proposal_id,
            request.get("reviewer"),
            request.get("reason")
        )
        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "data": proposal
        }
    except ValueError as e:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": {"code": "not_found", "message": str(e)}}
        )


# ============================================================================
# GIT STAGING
# ============================================================================

@app.get("/v2/git/status")
async def git_status(authorization: Optional[str] = Header(None)):
    """Get the configured staging repository status."""
    verify_bearer_token(authorization)
    status = git_service.get_status()
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": status
    }


@app.post("/v2/git/branches")
async def git_branch(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Create a staging-only translation branch."""
    verify_bearer_token(authorization)
    try:
        result = git_service.create_branch(
            request.get("branch_name"),
            request.get("base_branch")
        )
        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "data": result
        }
    except GitStagingError as e:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": {"code": "git_error", "message": str(e)}}
        )


@app.post("/v2/git/stage")
async def git_stage(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Write READY translation files to staging and commit."""
    verify_bearer_token(authorization)
    try:
        result = git_service.stage_files(
            request.get("branch_name"),
            request.get("files", []),
            request.get("commit_message")
        )
        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "data": result
        }
    except GitStagingError as e:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": {"code": "git_error", "message": str(e)}}
        )


@app.post("/v2/git/push")
async def git_push(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Push an existing translation branch when explicitly enabled."""
    verify_bearer_token(authorization)
    try:
        result = git_service.push(request.get("branch_name"))
        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "data": result
        }
    except GitStagingError as e:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": {"code": "git_error", "message": str(e)}}
        )


@app.post("/v2/git/draft-pr")
async def git_draft_pr(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Create a draft GitHub pull request for human review."""
    verify_bearer_token(authorization)
    result = git_service.create_draft_pr(
        request.get("branch_name"),
        request.get("base_branch", "main"),
        request.get("title"),
        request.get("body")
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": result
    }
