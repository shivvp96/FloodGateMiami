from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.address_lookup.models import GeoCoordinates
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


def _geocode_result(address: str, lat: float, lon: float):
    async def _fake(address_in, *, config):
        assert address_in == address
        return address, GeoCoordinates(latitude=lat, longitude=lon), 100.0

    return _fake


def test_saved_location_create_stores_validated_coordinates() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with patch(
            "app.saved_locations.routes.census_geocode",
            new=_geocode_result("111 NW 1st St, Miami, FL 33128", 25.7751, -80.1963),
        ):
            created = client.post(
                "/api/v1/saved-locations/",
                json={"owner_type": "property", "label": "Home", "address": "111 NW 1st St, Miami, FL 33128"},
            )
        assert created.status_code == 201, created.text
        body = created.json()
        location_id = body["id"]
        assert body["latitude"] == 25.7751
        assert body["longitude"] == -80.1963

        listing = client.get("/api/v1/saved-locations/?owner_type=property")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [location_id]
        assert listing.json()[0]["latitude"] == 25.7751

    # Coordinates persist across restarts
    with TestClient(create_app()) as restarted_client:
        persisted = restarted_client.get("/api/v1/saved-locations/?owner_type=property")
        assert [item["id"] for item in persisted.json()] == [location_id]
        assert persisted.json()[0]["longitude"] == -80.1963
        removed = restarted_client.delete(f"/api/v1/saved-locations/{location_id}")
        assert removed.status_code == 204


def test_saved_location_unmatched_address_rejected() -> None:
    reset_database()

    async def _unmatched(address_in, *, config):
        raise ValueError("unmatched_address")

    with TestClient(create_app()) as client:
        with patch("app.saved_locations.routes.census_geocode", new=_unmatched):
            created = client.post(
                "/api/v1/saved-locations/",
                json={"owner_type": "vehicle", "label": "Car", "address": "zzzz nowhere"},
            )
        assert created.status_code == 422
        assert "geocod" in created.json()["detail"].lower()
        assert client.get("/api/v1/saved-locations/?owner_type=vehicle").json() == []


def test_saved_location_geocoder_unavailable_is_503() -> None:
    reset_database()
    import httpx

    async def _down(address_in, *, config):
        raise httpx.ConnectError("census down")

    with TestClient(create_app()) as client:
        with patch("app.saved_locations.routes.census_geocode", new=_down):
            created = client.post(
                "/api/v1/saved-locations/",
                json={"owner_type": "vehicle", "label": "Car", "address": "111 NW 1st St, Miami, FL 33128"},
            )
        assert created.status_code == 503


def test_saved_location_validation() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        assert client.post(
            "/api/v1/saved-locations/",
            json={"owner_type": "property", "label": " ", "address": "Miami"},
        ).status_code == 422
        assert client.get("/api/v1/saved-locations/?owner_type=boat").status_code == 422
        assert client.delete("/api/v1/saved-locations/999").status_code == 404


def test_migration_adds_coordinates_to_existing_rows() -> None:
    """Pre-existing rows (no lat/lon) survive the additive migration and remain nullable."""
    from sqlmodel import Session, text

    from app.db import init_db
    from app.saved_locations.models import SavedLocation

    reset_database()
    # Simulate a legacy row inserted before the columns existed: create table fresh,
    # then drop the new columns to emulate the old schema.
    with Session(engine) as session:
        session.exec(text("ALTER TABLE savedlocation DROP COLUMN latitude"))
        session.exec(text("ALTER TABLE savedlocation DROP COLUMN longitude"))
        session.exec(
            text(
                "INSERT INTO savedlocation (owner_type, label, address, created_at) "
                "VALUES ('property', 'Legacy', '100 Legacy Way, Miami, FL', '2026-01-01T00:00:00')"
            )
        )
        session.commit()

    init_db()  # idempotent migration should re-add the columns

    with TestClient(create_app()) as client:
        listing = client.get("/api/v1/saved-locations/?owner_type=property")
        assert listing.status_code == 200
        rows = listing.json()
        assert len(rows) == 1
        assert rows[0]["label"] == "Legacy"
        assert rows[0]["latitude"] is None
        assert rows[0]["longitude"] is None
