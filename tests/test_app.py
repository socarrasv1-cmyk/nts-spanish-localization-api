import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.git_stage import GitStaging, GitStagingError
from app.main import API_VERSION, LEGACY_API_VERSION, _rate_windows, app
from app.store import store
from app.tm import TranslationMemory


client = TestClient(app)
AUTH = {"Authorization": "Bearer test-secret-key"}
SOURCE_URL = "/services/break-bulk-transport.php"
TARGET_URL = "/es/servicios/transporte-de-carga-fraccionada.php"

SOURCE_HTML = f"""<!doctype html><html><head>
<link rel="canonical" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="en-US" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="es-US" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Service","url":"https://www.heavyequipmenttransport.com{SOURCE_URL}"}}</script>
</head><body><main id="content" class="service"><h1>Break bulk transport</h1><a href="/quote.php">Start Quote</a></main></body></html>"""

TARGET_HTML = f"""<!doctype html><html><head>
<link rel="canonical" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<link rel="alternate" hreflang="en-US" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="es-US" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Service","url":"https://www.heavyequipmenttransport.com{TARGET_URL}"}}</script>
</head><body><main id="content" class="service"><h1>Transporte de carga fraccionada</h1><a href="/quote.php">Iniciar cotización</a></main></body></html>"""


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("NTS_API_KEY", "test-secret-key")
    original = store.data_dir
    store.data_dir = tmp_path
    _rate_windows.clear()
    (tmp_path / "sites.json").write_text(json.dumps({"sites": [{
        "site_id": "het-main", "brand_name": "Heavy Equipment Transport", "status": "verified"
    }]}), encoding="utf-8")
    yield
    store.data_dir = original
    _rate_windows.clear()


def test_health_and_authentication():
    assert client.get("/healthz").json()["version"] == API_VERSION
    assert client.get("/v2/sites").status_code == 401
    assert client.get("/v2/sites", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v2/sites", headers=AUTH).status_code == 200


def test_body_limit():
    response = client.post("/v2/validate/php", headers=AUTH, json={"php_code": "x" * 100_000})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_jobs_artifacts_are_persistent_and_immutable():
    job = client.post("/v2/jobs", headers=AUTH, json={
        "site_id": "het", "english_url": SOURCE_URL
    }).json()["data"]
    source = client.post(f"/v2/jobs/{job['job_id']}/source/import", headers=AUTH,
                         json={"content": SOURCE_HTML}).json()["data"]
    artifact = client.get(f"/v2/artifacts/{source['artifact_id']}", headers=AUTH).json()["data"]
    assert artifact["content"] == SOURCE_HTML
    assert artifact["sha256"] == source["sha256"]
    assert client.get(f"/v2/jobs/{job['job_id']}", headers=AUTH).json()["data"]["state"] == "SOURCE_IMPORTED"


def test_approved_url_mapping_and_alias():
    response = client.get("/v2/url-map/approved", headers=AUTH,
                          params={"site_id": "het", "source_url": SOURCE_URL})
    assert response.status_code == 200
    assert response.json()["data"]["spanish_url"] == TARGET_URL
    assert response.json()["data"]["approved"] is True


def test_url_candidate_rules_and_collision():
    valid = client.post("/v2/url-map/validate", headers=AUTH, json={
        "site_id": "het-main", "source_url": "/services/new.php",
        "candidate": "/es/servicios/nuevo.php",
    }).json()["data"]
    assert valid["status"] == "PASS"
    store.save("url_map", {"mappings": [{
        "site_id": "het-main", "english_url": "/one.php",
        "spanish_url": "/es/servicios/duplicado.php", "status": "approved",
    }]})
    collision = client.post("/v2/url-map/validate", headers=AUTH, json={
        "site_id": "het-main", "source_url": "/two.php",
        "candidate": "/es/servicios/duplicado.php",
    }).json()["data"]
    assert collision["blocking"] is True
    assert {issue["code"] for issue in collision["issues"]} == {"URL_COLLISION"}


@pytest.mark.parametrize("endpoint,payload", [
    ("/v2/validate/php", {"php_code": TARGET_HTML}),
    ("/v2/validate/structure", {"source_html": SOURCE_HTML, "target_html": TARGET_HTML}),
    ("/v2/validate/protected-tokens", {"source_content": SOURCE_HTML, "target_content": TARGET_HTML}),
    ("/v2/validate/english-residue", {"target_content": TARGET_HTML}),
    ("/v2/validate/schema", {"html_content": TARGET_HTML, "target_url": TARGET_URL}),
    ("/v2/validate/links", {"html_content": TARGET_HTML, "target_url": TARGET_URL}),
])
def test_validators_pass_with_evidence(endpoint, payload):
    result = client.post(endpoint, headers=AUTH, json=payload).json()["data"]
    assert result["status"] == "PASS", result
    assert result["blocking"] is False
    assert result["metrics"]["version"] == "2.2"


def test_php_lint_failure_is_blocking():
    completed = type("Completed", (), {"returncode": 255, "stdout": "", "stderr": "Parse error in candidate.php"})()
    with patch("app.validators.shutil.which", return_value="/usr/bin/php"), \
         patch("app.validators.subprocess.run", return_value=completed):
        result = client.post("/v2/validate/php", headers=AUTH,
                             json={"php_code": "<?php broken( ?>"}).json()["data"]
    assert result["status"] == "FAIL"
    assert result["issues"][0]["code"] == "PHP_SYNTAX_ERROR"


def test_structure_token_english_and_link_failures():
    cases = [
        ("/v2/validate/structure", {"source_html": "<main><p>A</p></main>", "target_html": "<main>A</main>"}),
        ("/v2/validate/protected-tokens", {"source_content": "Call {{phone}}", "target_content": "Llame {{telefono}}"}),
        ("/v2/validate/english-residue", {"target_content": "Start Quote and contact us now"}),
        ("/v2/validate/links", {"html_content": "<a href='javascript:alert(1)'>X</a>"}),
    ]
    for endpoint, payload in cases:
        result = client.post(endpoint, headers=AUTH, json=payload).json()["data"]
        assert result["blocking"] is True, (endpoint, result)


def test_page_qa_ready_and_blocked_are_evidence_based():
    ready = client.post("/v2/qa/page", headers=AUTH, json={
        "site_id": "het-main", "source_url": SOURCE_URL, "target_url": TARGET_URL,
        "source_html": SOURCE_HTML, "target_html": TARGET_HTML,
    }).json()["data"]
    assert ready["status"] == "READY"
    assert ready["score"] == 100
    blocked = client.post("/v2/qa/page", headers=AUTH, json={
        "source_html": SOURCE_HTML, "target_html": "<main>Start Quote</main>",
        "target_url": TARGET_URL,
    }).json()["data"]
    assert blocked["status"] == "BLOCKED"
    assert blocked["blocking_issues"]


def test_batch_qa_detects_duplicate_targets():
    page = {"source_url": SOURCE_URL, "target_url": TARGET_URL,
            "source_html": SOURCE_HTML, "target_html": TARGET_HTML}
    result = client.post("/v2/qa/batch", headers=AUTH,
                         json={"site_id": "het-main", "pages": [page, page]}).json()["data"]
    assert result["status"] == "BLOCKED"
    assert result["duplicate_targets"] == [TARGET_URL]


def test_package_requires_ready_jobs():
    job = client.post("/v2/jobs", headers=AUTH,
                      json={"site_id": "het", "english_url": SOURCE_URL}).json()["data"]
    blocked = client.post("/v2/staging/packages", headers=AUTH,
                          json={"job_ids": [job["job_id"]]}).json()["data"]
    assert blocked["status"] == "BLOCKED"
    client.post("/v2/qa/page", headers=AUTH, json={
        "job_id": job["job_id"], "source_html": SOURCE_HTML,
        "target_html": TARGET_HTML, "target_url": TARGET_URL,
    })
    package = client.post("/v2/staging/packages", headers=AUTH,
                          json={"job_ids": [job["job_id"]]}).json()["data"]
    assert package["status"] == "PACKAGE_READY"


def test_translation_memory_requires_human_review_and_audits():
    tm = TranslationMemory()
    proposal = tm.propose("break bulk", "carga fraccionada", "het-main", "service")
    assert tm.search("break bulk", site_id="het-main") == []
    reviewed = tm.approve_proposal(proposal["proposal_id"], "Javier Socarras", "Approved terminology")
    assert reviewed["status"] == "approved"
    assert tm.search("BREAK BULK", site_id="het-main")[0]["translation"] == "carga fraccionada"
    assert store.load("translation_memory")["audit"][-1]["event"] == "proposal_approved"
    with pytest.raises(ValueError, match="already approved"):
        tm.reject_proposal(proposal["proposal_id"], "Javier Socarras")


def test_action_tm_compatibility_routes():
    proposal = client.post("/v2/tm/propose", headers=AUTH, json={
        "source": "break bulk", "translation": "carga fraccionada",
        "locale": "es-US", "site_id": "het-main", "component": "service",
    })
    assert proposal.status_code == 201
    proposal_id = proposal.json()["data"]["proposal_id"]
    assert client.post(f"/v2/tm/approve/{proposal_id}", headers=AUTH,
                       json={"reviewer": "Javier Socarras"}).status_code == 200
    search = client.get("/v2/tm/search", headers=AUTH, params={
        "source": "break bulk", "locale": "es-US", "site_id": "het-main", "component": "service",
    })
    assert search.status_code == 200
    assert search.json()["data"]["matches"][0]["approved"] is True


def test_git_rejects_path_traversal(tmp_path):
    git = GitStaging()
    git.repo_path = tmp_path / "repo"
    for branch in ("../../etc/passwd", "/main", "feature//bad", "bad.lock"):
        with pytest.raises(GitStagingError):
            git._validate_branch_name(branch)
    with pytest.raises(GitStagingError):
        git._safe_file_path("../../outside.php")


def test_git_staging_creates_real_commit(tmp_path):
    git = GitStaging()
    git.repo_path = tmp_path / "repo"
    assert git.create_branch("localization/test")["status"] == "created"
    result = git.stage_files("localization/test", [{
        "path": "es/pagina.php", "content": "<h1>Hola</h1>"
    }], "Add reviewed Spanish page")
    assert result["status"] == "committed"
    assert len(result["commit_sha"]) == 40
    assert (git.repo_path / "es/pagina.php").read_text(encoding="utf-8") == "<h1>Hola</h1>"


def test_gpt_action_contract_matches_live_app():
    schema_path = Path(__file__).parents[1] / "NTS-LOCALIZATION-ACTIONS-OPENAPI-V2.1-LIVE.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["info"]["version"] == LEGACY_API_VERSION
    operations = []
    app_routes = {(route.path, method.lower()) for route in app.routes
                  for method in getattr(route, "methods", set())}

    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                assert ref.startswith("#/components/schemas/")
                assert ref.rsplit("/", 1)[-1] in schema["components"]["schemas"]
            if value.get("type") == "array":
                assert "items" in value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(schema)
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            assert (path, method) in app_routes
            assert isinstance(operation["x-openai-isConsequential"], bool)
            operations.append(operation["operationId"])
    assert len(operations) == len(set(operations)) == 17
