from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import create_app


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_saved_location_create_list_delete_and_persistence() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        created = client.post(
            "/api/v1/saved-locations/",
            json={"owner_type": "property", "label": "Home", "address": "123 Biscayne Blvd, Miami, FL"},
        )
        assert created.status_code == 201
        location_id = created.json()["id"]
        listing = client.get("/api/v1/saved-locations/?owner_type=property")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [location_id]

    with TestClient(create_app()) as restarted_client:
        persisted = restarted_client.get("/api/v1/saved-locations/?owner_type=property")
        assert [item["id"] for item in persisted.json()] == [location_id]
        removed = restarted_client.delete(f"/api/v1/saved-locations/{location_id}")
        assert removed.status_code == 204
        assert restarted_client.get("/api/v1/saved-locations/?owner_type=property").json() == []


def test_saved_location_validation() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/saved-locations/", json={"owner_type": "property", "label": " ", "address": "Miami"}).status_code == 422
        assert client.get("/api/v1/saved-locations/?owner_type=boat").status_code == 422
        assert client.delete("/api/v1/saved-locations/999").status_code == 404
