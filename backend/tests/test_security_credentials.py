import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.address_lookup.models import GeoCoordinates
from app.db import engine
from app.main import create_app


def _geocode_result(address: str, lat: float, lon: float):
    async def _fake(address_in, *, config):
        return address, GeoCoordinates(latitude=lat, longitude=lon), 100.0

    return _fake


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_saved_locations_never_public_on_vercel_missing_key() -> None:
    os.environ["VERCEL"] = "1"
    os.environ.pop("SAVED_LOCATIONS_API_KEY", None)

    reset_database()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/saved-locations/?owner_type=property")
        assert response.status_code in {401, 503}

    os.environ.pop("VERCEL", None)


def test_saved_locations_requires_correct_api_key_on_vercel() -> None:
    os.environ["VERCEL"] = "1"
    os.environ["SAVED_LOCATIONS_API_KEY"] = "test-key"

    patcher = patch(
        "app.saved_locations.routes.census_geocode",
        new=_geocode_result("123 Biscayne Blvd", 25.77, -80.18),
    )
    patcher.start()

    reset_database()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/saved-locations/",
            json={"owner_type": "property", "label": "Home", "address": "123 Biscayne Blvd"},
            headers={"x-api-key": "wrong"},
        )
        assert response.status_code == 401

        response2 = client.post(
            "/api/v1/saved-locations/",
            json={"owner_type": "property", "label": "Home", "address": "123 Biscayne Blvd"},
            headers={"x-api-key": "test-key"},
        )
        assert response2.status_code == 201

    os.environ.pop("VERCEL", None)
    os.environ.pop("SAVED_LOCATIONS_API_KEY", None)
    patcher.stop()
