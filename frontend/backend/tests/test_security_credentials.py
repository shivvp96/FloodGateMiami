from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import create_app


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_saved_locations_requires_credentials_on_vercel() -> None:
    # Simulate production where saved-locations must not become public.
    import os

    os.environ["VERCEL"] = "1"
    os.environ.pop("SAVED_LOCATIONS_API_KEY", None)

    reset_database()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/saved-locations/?owner_type=property")
        assert response.status_code in {401, 503}

    os.environ.pop("VERCEL", None)


def test_saved_locations_requires_correct_api_key() -> None:
    import os

    os.environ["VERCEL"] = "1"
    os.environ["SAVED_LOCATIONS_API_KEY"] = "test-key"

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
