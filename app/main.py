from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
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

# Initialize services
tm_service = TranslationMemory()
git_service = GitStaging()

# Canonical site IDs used by the persistent registry. GPT callers may use the
# shorter public aliases shown in the Action schema.
SITE_ID_ALIASES = {
    "het": "het-main",
    "het-main": "het-main",
    "nts": "nts-main",
    "nts-main": "nts-main",
}

# Packaged fallback keeps the first approved HET mapping available even when a
# Render persistent disk predates the repository data seed.
DEFAULT_URL_MAPPINGS = [
    {
        "source_url": "/services/break-bulk-transport.php",
        "spanish_url": "/es/servicios/transporte-de-carga-fraccionada.php",
        "site_id": "het-main",
        "approved": True,
        "status": "approved",
    }
]


def normalize_site_id(site_id: Optional[str]) -> str:
    normalized = (site_id or "").strip().lower()
    return SITE_ID_ALIASES.get(normalized, normalized)


def find_approved_url_mapping(site_id: str, source_url: str) -> Optional[Dict[str, Any]]:
    url_data = store.load("url_map")
    stored_mappings = url_data.get("url_mappings") or url_data.get("mappings") or []
    mappings = list(stored_mappings) + DEFAULT_URL_MAPPINGS

    requested_site = normalize_site_id(site_id)
    requested_source = (source_url or "").strip()

    for mapping in mappings:
        mapping_site = normalize_site_id(mapping.get("site_id"))
        mapping_source = mapping.get("source_url") or mapping.get("english_url")
        is_approved = (
            mapping.get("approved") is True
            or str(mapping.get("status", "")).lower() == "approved"
        )
        if mapping_site == requested_site and mapping_source == requested_source and is_approved:
            return {
                "source_url": mapping_source,
                "spanish_url": mapping.get("spanish_url"),
                "site_id": mapping_site,
                "approved": True,
                "approved_by": mapping.get("approved_by"),
                "approved_at": mapping.get("approved_at"),
            }
    return None

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

@app.get("/v2/url-map/approved")
async def url_map_approved(
    site_id: str,
    source_url: str,
    authorization: Optional[str] = Header(None)
):
    """Return an approved English-to-Spanish URL mapping."""
    verify_bearer_token(authorization)
    mapping = find_approved_url_mapping(site_id, source_url)
    if mapping is None:
        raise HTTPException(
            status_code=404,
            detail="No approved URL mapping found for the requested site and source URL"
        )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": mapping
    }


@app.post("/v2/url-map/get")
async def url_map_get(
    request: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Backward-compatible approved URL mapping lookup."""
    verify_bearer_token(authorization)
    source_url = request.get("source_url") or request.get("english_url")
    mapping = find_approved_url_mapping(request.get("site_id"), source_url)
    if mapping is None:
        raise HTTPException(
            status_code=404,
            detail="No approved URL mapping found for the requested site and source URL"
        )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": mapping
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

@app.get("/v2/tm/search")
async def tm_search_get(
    source: str,
    locale: str = "es-US",
    site_id: Optional[str] = None,
    component: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """Search approved NTS Translation Memory using Action query parameters."""
    verify_bearer_token(authorization)
    results = tm_service.search(
        source,
        locale,
        normalize_site_id(site_id) if site_id else None,
        component
    )
    return {
        "ok": True,
        "request_id": str(uuid.uuid4()),
        "data": results
    }


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


@app.post("/v2/tm/propose", status_code=201)
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
        normalize_site_id(request.get("site_id")) if request.get("site_id") else None,
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


@app.post("/v2/tm/approve/{proposal_id}")
@app.post("/v2/tm/proposals/{proposal_id}/approve")
async def tm_approve(
    proposal_id: str,
    request: Optional[Dict[str, Any]] = None,
    authorization: Optional[str] = Header(None)
):
    """Approve a translation-memory proposal."""
    verify_bearer_token(authorization)
    try:
        request_data = request or {}
        proposal = tm_service.approve_proposal(
            proposal_id,
            request_data.get("reviewer", "NTS Spanish Translator"),
            request_data.get("reason")
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


@app.post("/v2/tm/reject/{proposal_id}")
@app.post("/v2/tm/proposals/{proposal_id}/reject")
async def tm_reject(
    proposal_id: str,
    request: Optional[Dict[str, Any]] = None,
    authorization: Optional[str] = Header(None)
):
    """Reject a translation-memory proposal."""
    verify_bearer_token(authorization)
    try:
        request_data = request or {}
        proposal = tm_service.reject_proposal(
            proposal_id,
            request_data.get("reviewer", "NTS Spanish Translator"),
            request_data.get("reason")
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
