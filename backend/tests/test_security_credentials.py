"""Production private endpoints are JWT-authenticated, not shared-key protected."""
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import create_app


def reset_database():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_saved_locations_fail_closed_when_auth_not_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    reset_database()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/saved-locations/?owner_type=property")
        assert response.status_code == 503


def test_shared_api_key_can_never_authenticate_production_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SAVED_LOCATIONS_API_KEY", "obsolete-test-key")
    reset_database()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/saved-locations/",
            json={"owner_type": "property", "label": "Home", "address": "123 Biscayne Blvd"},
            headers={"x-api-key": "obsolete-test-key"},
        )
        assert response.status_code == 401
        assert client.get("/api/v1/saved-locations/", headers={"x-api-key": "obsolete-test-key"}).status_code == 401
        assert client.post("/api/v1/move-car/recommend", json={"location_id": 1}, headers={"x-api-key": "obsolete-test-key"}).status_code == 401
