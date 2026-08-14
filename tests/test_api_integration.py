import importlib

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok():
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_optional_in_development_without_api_key(monkeypatch):
    monkeypatch.setenv("NTS_ENV", "development")
    monkeypatch.delenv("NTS_API_KEY", raising=False)

    import app.main
    importlib.reload(app.main)
    client = TestClient(app.main.app)

    response = client.get("/v2/sites")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_auth_optional_in_development_even_with_api_key(monkeypatch):
    monkeypatch.setenv("NTS_ENV", "development")
    monkeypatch.setenv("NTS_API_KEY", "test-key")

    import app.main
    importlib.reload(app.main)
    client = TestClient(app.main.app)

    response = client.get("/v2/sites")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_development_mode_does_not_enforce_wrong_api_key(monkeypatch):
    monkeypatch.setenv("NTS_ENV", "development")
    monkeypatch.setenv("NTS_API_KEY", "expected-key")

    import app.main
    importlib.reload(app.main)
    client = TestClient(app.main.app)

    response = client.get("/v2/sites", headers={"x-api-key": "wrong-key"})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_auth_required_in_production_with_x_api_key(monkeypatch):
    monkeypatch.setenv("NTS_ENV", "production")
    monkeypatch.setenv("NTS_API_KEY", "test-key")

    import app.main
    importlib.reload(app.main)
    client = TestClient(app.main.app)

    unauthorized = client.get("/v2/sites")
    assert unauthorized.status_code == 401

    authorized = client.get("/v2/sites", headers={"x-api-key": "test-key"})
    assert authorized.status_code == 200
    assert authorized.json()["ok"] is True


def test_cors_allows_configured_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://lovable.dev, https://example.com")

    import app.main
    importlib.reload(app.main)
    client = TestClient(app.main.app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://lovable.dev",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://lovable.dev"
