import importlib

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

PILLARS = ["track", "grow", "learn", "protect", "ai-cfo", "auth"]


def test_health_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "finguru-api"}


def test_pillar_status_endpoints():
    for pillar in PILLARS:
        response = client.get(f"/api/{pillar}/status")
        assert response.status_code == 200
        body = response.json()
        assert body["pillar"] == pillar
        assert body["phase"] == "scaffolded"
        assert len(body["modules"]) > 0


def test_auth_me_rejects_unauthenticated_with_consistent_error_shape():
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"] == "Authentication required"


def test_business_logic_packages_importable_from_backend():
    # The backend package bootstraps sys.path so the engines (still at the
    # repo root during migration) are importable from the API layer.
    importlib.import_module("engines.fire_engine")
    importlib.import_module("engines.tax_engine")
