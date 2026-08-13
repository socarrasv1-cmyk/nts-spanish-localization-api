import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import _rate_windows, app
from app.v3_main import app as v3_only_app
from app.store import store


client = TestClient(app)
AUTH = {"Authorization": "Bearer test-secret-key"}
SOURCE_URL = "/services/break-bulk-transport.php"
TARGET_URL = "/es/servicios/transporte-de-carga-fraccionada.php"

SOURCE_HTML = f"""<!doctype html><html><head>
<link rel="canonical" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="en-US" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="es-US" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Service","url":"https://www.heavyequipmenttransport.com{SOURCE_URL}"}}</script>
</head><body><main id="content" class="service"><h1>Break bulk transport</h1><p>Call 877-278-3135 for a 40,000 lbs shipment.</p><a href="/quote.php">Start Quote</a></main></body></html>"""

TARGET_HTML = f"""<!doctype html><html><head>
<link rel="canonical" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<link rel="alternate" hreflang="en-US" href="https://www.heavyequipmenttransport.com{SOURCE_URL}">
<link rel="alternate" hreflang="es-US" href="https://www.heavyequipmenttransport.com{TARGET_URL}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Service","url":"https://www.heavyequipmenttransport.com{TARGET_URL}"}}</script>
</head><body><main id="content" class="service"><h1>Transporte de carga fraccionada</h1><p>Llame al 877-278-3135 para un envío de 40,000 lbs.</p><a href="/quote.php">Iniciar cotización</a></main></body></html>"""


@pytest.fixture(autouse=True)
def isolated_v3_store(tmp_path, monkeypatch):
    monkeypatch.setenv("NTS_API_KEY", "test-secret-key")
    monkeypatch.setenv("NTS_PROVENANCE_VERIFIED", "false")
    monkeypatch.setenv("NTS_ENVIRONMENT", "test")
    original = store.data_dir
    store.data_dir = tmp_path
    _rate_windows.clear()
    store.save("url_map", {"mappings": [{
        "site_id": "het-main",
        "english_url": SOURCE_URL,
        "spanish_url": TARGET_URL,
        "status": "approved",
        "approved": True,
        "approved_by": "release-test",
    }]})
    yield
    store.data_dir = original
    _rate_windows.clear()


def _create_job(source_url=SOURCE_URL, mode="strict_mirror"):
    response = client.post("/v3/jobs", headers=AUTH, json={
        "site_id": "het", "source_url": source_url, "mode": mode,
    })
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _lock_html_pair(job_id):
    source = client.post(f"/v3/jobs/{job_id}/source", headers=AUTH, json={"content": SOURCE_HTML})
    draft = client.post(f"/v3/jobs/{job_id}/draft", headers=AUTH, json={"content": TARGET_HTML})
    assert source.status_code == draft.status_code == 201
    return source.json()["data"], draft.json()["data"]


def test_v3_provenance_and_knowledge_are_verified_but_promotion_stays_fail_closed():
    provenance = client.get("/v3/system/provenance", headers=AUTH).json()["data"]
    manifest = client.get("/v3/knowledge/manifest", headers=AUTH).json()["data"]
    assert provenance["api_version"] == "3.0.0"
    assert provenance["status"] == "CANDIDATE"
    assert provenance["production_promotion_allowed"] is False
    assert manifest["status"] == "VERIFIED"
    assert manifest["unresolved_modules"] == []
    assert manifest["issues"] == []


def test_knowledge_manifest_verifies_active_module_checksum(tmp_path, monkeypatch):
    manifest_path = tmp_path / "tampered-manifest.json"
    manifest_path.write_text(json.dumps({
        "version": "3.0.0",
        "modules": [{
            "id": "blueprint-control",
            "file": "knowledge/NTS-SPANISH-TRANSLATOR-BLUEPRINT-V3.md",
            "version": "3.0.0",
            "status": "active",
            "sha256": "0" * 64,
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("NTS_KNOWLEDGE_MANIFEST", str(manifest_path))
    manifest = client.get("/v3/knowledge/manifest", headers=AUTH).json()["data"]
    assert manifest["status"] == "BLOCKED"
    assert manifest["issues"][0]["code"] == "KNOWLEDGE_MODULE_CHECKSUM_MISMATCH"


def test_job_requires_approved_site_specific_url_mapping():
    job = _create_job("/services/unapproved.php")
    assert job["state"] == "BLOCKED"
    assert job["target_url"] is None
    evidence = client.get(f"/v3/jobs/{job['job_id']}/evidence", headers=AUTH).json()["data"]
    assert evidence["events"][-1]["event_type"] == "url_mapping_missing"


def test_v3_job_runs_evidence_based_full_qa():
    job = _create_job()
    assert job["state"] == "URL_RESOLVED"
    source, draft = _lock_html_pair(job["job_id"])
    assert len(source["sha256"]) == len(draft["sha256"]) == 64

    coverage = client.post(f"/v3/jobs/{job['job_id']}/qa/coverage", headers=AUTH).json()["data"]
    facts = client.post(f"/v3/jobs/{job['job_id']}/qa/facts", headers=AUTH).json()["data"]
    assert coverage["status"] == "PASS", coverage
    assert coverage["metrics"]["coverage_percent"] == 100
    assert facts["status"] == "PASS", facts

    qa = client.post(f"/v3/jobs/{job['job_id']}/qa", headers=AUTH, json={
        "visual_review_completed": True, "reviewer": "release-test",
    }).json()["data"]
    assert qa["status"] == "READY", qa
    assert qa["score"] == 100
    assert set(qa["checks"]) == {
        "php", "structure", "protected_tokens", "english_residue", "schema", "links",
        "coverage", "facts_parity", "site_isolation", "prompt_injection_content",
    }

    evidence = client.get(f"/v3/jobs/{job['job_id']}/evidence", headers=AUTH).json()["data"]
    assert evidence["job"]["state"] == "READY"
    assert len(evidence["artifacts"]) == 2
    assert all("content" not in artifact for artifact in evidence["artifacts"])
    assert all(len(event["sha256"]) == 64 for event in evidence["events"])
    assert all(event["integrity"] == "VERIFIED" for event in evidence["events"])
    assert [event["new_state"] for event in evidence["events"][-2:]] == ["VALIDATED", "READY"]


def test_v3_artifacts_are_immutable():
    job = _create_job()
    _lock_html_pair(job["job_id"])
    assert client.post(f"/v3/jobs/{job['job_id']}/source", headers=AUTH,
                       json={"content": SOURCE_HTML}).status_code == 409
    assert client.post(f"/v3/jobs/{job['job_id']}/draft", headers=AUTH,
                       json={"content": TARGET_HTML}).status_code == 409


def test_csv_contract_enforces_image_alt_and_logical_groups():
    valid = "slug,target_url,body_section_1,image_01,alt_01\na,/es/a,Texto,/img/a.webp,Equipo"
    invalid = "slug,target_url,body_p_1,body_list_1,image_01,title\na,/es/a,Texto,Lista,/img/a.webp,Título"
    from app.validators_v3 import validate_csv_contract

    assert validate_csv_contract(valid).status == "PASS"
    result = validate_csv_contract(invalid)
    assert result.status == "FAIL"
    assert {issue["code"] for issue in result.issues} == {
        "CSV_IMAGE_ALT_ADJACENCY", "CSV_IMAGE_ALT_VALUE_MISSING", "CSV_SECTION_GROUP_SPLIT",
    }


def test_regression_suite_is_deterministic_and_adversarial():
    report = client.post("/v3/regression/run", headers=AUTH).json()["data"]
    assert report["status"] == "PASS", report
    assert report["fixture_count"] >= 7
    assert report["failed"] == 0
    assert {item["fixture_id"] for item in report["results"]} >= {
        "coverage-negative", "facts-negative", "csv-negative", "injection-data",
    }


def test_packaging_requires_verified_provenance():
    job = _create_job()
    _lock_html_pair(job["job_id"])
    ready = client.post(f"/v3/jobs/{job['job_id']}/qa", headers=AUTH, json={
        "visual_review_completed": True, "reviewer": "release-test",
    })
    assert ready.json()["data"]["status"] == "READY"
    package = client.post("/v3/evidence-packages", headers=AUTH, json={"job_id": job["job_id"]})
    assert package.status_code == 409
    assert "provenance" in package.json()["error"]["message"].lower()


def test_v3_action_contract_matches_routes_and_has_unique_operations():
    schema_path = Path(__file__).parents[1] / "NTS-LOCALIZATION-ACTIONS-OPENAPI-V3-STAGING.json"
    raw = schema_path.read_text(encoding="utf-8")
    schema = json.loads(raw)
    assert schema["info"]["version"] == "3.0.0"
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest()
    app_routes = {(route.path, method.lower()) for route in app.routes
                  for method in getattr(route, "methods", set())}
    operations = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            assert (path, method) in app_routes
            assert isinstance(operation["x-openai-isConsequential"], bool)
            operations.append(operation["operationId"])
    assert len(operations) == len(set(operations)) == 13


def test_v3_only_runtime_exposes_no_legacy_routes():
    schema = v3_only_app.openapi()
    assert schema["info"]["version"] == "3.0.0"
    assert schema["info"]["title"] == "NTS Spanish Translator Blueprint V3 API"
    assert all(path == "/healthz" or path.startswith("/v3/") for path in schema["paths"])
    assert not any(path.startswith("/v2/") for path in schema["paths"])


def test_v3_validator_evidence_never_reports_legacy_bundle_version():
    job = _create_job()
    _lock_html_pair(job["job_id"])
    response = client.post(f"/v3/jobs/{job['job_id']}/qa", headers=AUTH, json={
        "visual_review_completed": True,
        "reviewer": "release-test",
    })
    assert response.status_code == 200
    checks = response.json()["data"]["checks"]
    assert checks
    assert {check["validator_version"] for check in checks.values()} == {"3.0.0"}
    assert {check["metrics"]["version"] for check in checks.values()} == {"3.0.0"}
