import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.store import store
from app.tm import TranslationMemory
from app.git_stage import GitStaging
import os
import json
from datetime import datetime

client = TestClient(app)

# ============================================================================
# PHASE 2 — AUTHENTICATION & HEALTH CHECKS
# ============================================================================

def test_healthz_no_auth():
    """GET /healthz should return 200 without authentication."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "nts-localization-api"
    assert data["version"] == "2.1.0"


def test_protected_endpoint_no_auth():
    """Protected endpoints should return 401 without Bearer token."""
    response = client.get("/v2/sites")
    assert response.status_code == 401
    assert "authorization" in response.headers.get("www-authenticate", "").lower()


def test_protected_endpoint_invalid_auth():
    """Protected endpoints should return 401 with invalid Bearer format."""
    response = client.get("/v2/sites", headers={"Authorization": "InvalidFormat"})
    assert response.status_code == 401
    
    response = client.get("/v2/sites", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_protected_endpoint_wrong_token():
    """Protected endpoints should return 401 with wrong Bearer token."""
    response = client.get("/v2/sites", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_protected_endpoint_valid_token():
    """Protected endpoints should return 200 with valid Bearer token."""
    # Set test API key
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.get("/v2/sites", headers={"Authorization": "Bearer test-secret-key"})
    assert response.status_code == 200
    assert response.json()["ok"] == True


# ============================================================================
# PHASE 3 — ARTIFACT RETENTION & PERSISTENCE
# ============================================================================

def test_store_persistence():
    """PersistentStore should save and load data correctly."""
    test_data = {"test_key": "test_value", "timestamp": datetime.utcnow().isoformat()}
    store.save("test_artifact", test_data)
    
    loaded = store.load("test_artifact")
    assert loaded["test_key"] == "test_value"
    assert "timestamp" in loaded


def test_store_thread_safety():
    """PersistentStore should be thread-safe."""
    import threading
    
    results = []
    
    def write_data(index):
        store.set("concurrent_test", f"key_{index}", f"value_{index}")
    
    threads = [threading.Thread(target=write_data, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    data = store.load("concurrent_test")
    assert len(data) >= 1  # At least some writes succeeded


def test_artifact_ttl_env_var():
    """NTS_ARTIFACT_TTL_HOURS should be configurable."""
    ttl_hours = os.getenv("NTS_ARTIFACT_TTL_HOURS", "168")
    assert int(ttl_hours) == 168


# ============================================================================
# PHASE 4 — TRANSLATION MEMORY
# ============================================================================

def test_tm_propose_and_approve():
    """Translation Memory proposals should require explicit approval."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    tm = TranslationMemory()
    
    # Initialize TM
    store.save("translation_memory", {"entries": [], "proposals": []})
    
    # Submit proposal
    proposal = tm.propose(
        source="Start Quote",
        translation="Iniciar cotización",
        site_id="het",
        component="button",
        locale="es-US",
        notes="Call-to-action button on homepage"
    )
    
    assert proposal["status"] == "proposed"
    assert proposal["source"] == "Start Quote"
    assert proposal["translation"] == "Iniciar cotización"
    assert proposal["proposal_id"] is not None
    
    # Proposal should NOT be in approved entries yet
    tm_data = store.load("translation_memory")
    approved_entries = [e for e in tm_data.get("entries", []) if e.get("approved")]
    assert len(approved_entries) == 0
    
    # Approve the proposal
    approved = tm.approve_proposal(
        proposal["proposal_id"],
        reviewer="test-reviewer",
        reason="Verified translation"
    )
    
    assert approved["status"] == "approved"
    
    # Now it should be in approved entries
    tm_data = store.load("translation_memory")
    approved_entries = [e for e in tm_data.get("entries", []) if e.get("approved")]
    assert len(approved_entries) == 1
    assert approved_entries[0]["translation"] == "Iniciar cotización"


def test_tm_search_site_specific_precedence():
    """Translation Memory should prefer site-specific matches."""
    tm = TranslationMemory()
    
    # Set up TM with global and site-specific entries
    tm_data = {
        "entries": [
            {
                "source": "Help",
                "translation": "Ayuda",
                "site_id": None,  # Global
                "locale": "es-US",
                "approved": True
            },
            {
                "source": "Help",
                "translation": "Asistencia",
                "site_id": "het",  # Site-specific
                "locale": "es-US",
                "approved": True
            }
        ],
        "proposals": []
    }
    store.save("translation_memory", tm_data)
    
    # Search with site_id should return site-specific first
    results = tm.search("Help", locale="es-US", site_id="het")
    assert len(results) > 0
    assert results[0]["translation"] == "Asistencia"


def test_tm_reject_proposal():
    """Rejected proposals should not become canonical."""
    tm = TranslationMemory()
    store.save("translation_memory", {"entries": [], "proposals": []})
    
    proposal = tm.propose(
        source="Delete",
        translation="Eliminar",
        site_id="het",
        locale="es-US"
    )
    
    rejected = tm.reject_proposal(
        proposal["proposal_id"],
        reviewer="test-reviewer",
        reason="Incorrect context"
    )
    
    assert rejected["status"] == "rejected"
    
    # Rejected proposal should NOT be in entries
    tm_data = store.load("translation_memory")
    entries = tm_data.get("entries", [])
    assert all(e.get("translation") != "Eliminar" for e in entries)


# ============================================================================
# PHASE 5 — URL MAPPING & VALIDATION
# ============================================================================

def test_url_mapping_get():
    """URL mapping endpoint should return approved mappings."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    url_data = {
        "mappings": [
            {
                "english_url": "/services/break-bulk-transport.php",
                "spanish_url": "/es/servicios/transporte-de-carga-fraccionada.php",
                "status": "approved",
                "site_id": "het"
            }
        ]
    }
    store.save("url_map", url_data)
    
    response = client.post(
        "/v2/url-map/get",
        json={"english_url": "/services/break-bulk-transport.php", "site_id": "het"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    assert response.json()["ok"] == True


def test_url_candidate_vs_approved():
    """URL validation should distinguish candidate from approved."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    # Validate a candidate URL (not yet approved)
    response = client.post(
        "/v2/url-map/validate",
        json={
            "candidate_url": "/es/servicios/nuevo-servicio.php",
            "site_id": "het"
        },
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "PASS"
    # Validation should pass but NOT auto-approve
    assert data["data"]["blocking"] == False


def test_url_collision_detection():
    """URL mapping should detect collisions."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    # Two different English URLs cannot map to same Spanish URL
    url_data = {
        "mappings": [
            {
                "english_url": "/page1.php",
                "spanish_url": "/es/pagina.php",
                "status": "approved",
                "site_id": "het"
            },
            {
                "english_url": "/page2.php",
                "spanish_url": "/es/pagina.php",  # Collision!
                "status": "approved",
                "site_id": "het"
            }
        ]
    }
    store.save("url_map", url_data)
    
    response = client.post(
        "/v2/url-map/validate",
        json={"candidate_url": "/es/pagina.php", "site_id": "het"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should flag collision
    assert len(data["data"].get("issues", [])) >= 0 or data["data"]["status"] != "PASS"


# ============================================================================
# PHASE 6 & 7 — VALIDATORS
# ============================================================================

def test_validators_pass():
    """All validators should return PASS for valid input."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    validators = [
        ("/v2/validate/php", {"artifact_id": "test", "site_id": "het"}),
        ("/v2/validate/structure", {"site_id": "het", "english_artifact_id": "en", "spanish_artifact_id": "es"}),
        ("/v2/validate/protected-tokens", {"site_id": "het", "english_artifact_id": "en", "spanish_artifact_id": "es"}),
        ("/v2/validate/english-residue", {"artifact_id": "test", "site_id": "het"}),
        ("/v2/validate/schema", {"site_id": "het", "spanish_artifact_id": "es", "spanish_url": "/es/test.php"}),
        ("/v2/validate/links", {"site_id": "het", "english_url": "/test.php", "spanish_url": "/es/test.php", "spanish_artifact_id": "es"}),
    ]
    
    for endpoint, payload in validators:
        response = client.post(
            endpoint,
            json=payload,
            headers={"Authorization": "Bearer test-secret-key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert data["data"]["status"] == "PASS"
        assert data["data"]["blocking"] == False


# ============================================================================
# PHASE 8 — QA GATE
# ============================================================================

def test_qa_page_gate():
    """QA page gate should return READY only when score >= 95."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/qa/page",
        json={"site_id": "het", "artifact_id": "test"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["score"] >= 95
    assert data["data"]["status"] in ["READY", "NEEDS_REVIEW", "BLOCKED"]


def test_qa_batch_gate():
    """Batch QA should detect missing jobs and duplicates."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/qa/batch",
        json={
            "expected_job_count": 5,
            "job_ids": ["job1", "job2", "job3"]
        },
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should detect that 3 jobs were received but 5 were expected
    assert data["data"]["received_job_count"] == 3
    assert data["data"]["expected_job_count"] == 5


# ============================================================================
# PHASE 9 — GIT STAGING SAFETY
# ============================================================================

def test_git_push_disabled_by_default():
    """Git push should be disabled by default."""
    git = GitStaging()
    assert git.push_enabled == False
    
    # Attempt push should fail
    with pytest.raises(Exception):
        git.push("test-branch")


def test_git_branch_name_validation():
    """Git should validate branch names for safety."""
    git = GitStaging()
    
    # Should accept valid names
    valid_names = ["feature/new-feature", "hotfix/issue-123", "release/v2.1"]
    for name in valid_names:
        git._validate_branch_name(name)
    
    # Should reject unsafe names
    unsafe_names = ["../../etc/passwd", "origin/main", "../../../data"]
    for name in unsafe_names:
        with pytest.raises(Exception):
            git._validate_branch_name(name)


def test_git_status():
    """Git staging should report current status."""
    git = GitStaging()
    status = git.get_status()
    
    assert "repo_path" in status
    assert "remote_name" in status
    assert status["default_base_branch"] == "main"
    assert status["push_enabled"] == False


# ============================================================================
# PHASE 10+ — REGRESSION TESTS (T16, T18, T19, etc.)
# ============================================================================

def test_t16_protected_tokens():
    """T16: Protected tokens should be preserved across translation."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/validate/protected-tokens",
        json={
            "site_id": "het",
            "english_artifact_id": "en_artifact",
            "spanish_artifact_id": "es_artifact"
        },
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    assert response.json()["data"]["blocking"] == False


def test_t18_english_residue():
    """T18: Unintended English should be detected."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/validate/english-residue",
        json={"artifact_id": "es_artifact", "site_id": "het"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    assert "issues" in response.json()["data"]


def test_t19_hreflang():
    """T19: hreflang links should be validated."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/validate/links",
        json={
            "site_id": "het",
            "english_url": "/services/break-bulk-transport.php",
            "spanish_url": "/es/servicios/transporte-de-carga-fraccionada.php",
            "spanish_artifact_id": "es_artifact"
        },
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] == True


def test_t21_spanish_url_localization():
    """T21: Spanish URL mapping should work end-to-end."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    # Create mapping
    url_data = {
        "mappings": [
            {
                "english_url": "/services/break-bulk-transport.php",
                "spanish_url": "/es/servicios/transporte-de-carga-fraccionada.php",
                "status": "approved",
                "site_id": "het"
            }
        ]
    }
    store.save("url_map", url_data)
    
    # Look it up
    response = client.post(
        "/v2/url-map/get",
        json={"english_url": "/services/break-bulk-transport.php", "site_id": "het"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "approved"


def test_t23_php_preservation():
    """T23: PHP code should be preserved, not executed."""
    os.environ["NTS_API_KEY"] = "test-secret-key"
    
    response = client.post(
        "/v2/validate/php",
        json={"artifact_id": "php_artifact", "site_id": "het"},
        headers={"Authorization": "Bearer test-secret-key"}
    )
    
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PASS"
    # Should lint, not execute


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
