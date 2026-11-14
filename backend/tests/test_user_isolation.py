"""Security regressions: authenticated users must not see or assess each other's locations."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from app.auth import get_current_user_id
from app.db import engine
from app.main import create_app
from app.saved_locations.models import SavedLocation


USER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def seed():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SavedLocation(user_id=USER_A, owner_type="vehicle", label="A car", address="A", latitude=25.77, longitude=-80.19))
        session.add(SavedLocation(user_id=USER_B, owner_type="vehicle", label="B car", address="B", latitude=25.78, longitude=-80.20))
        session.commit()


def test_saved_location_list_and_delete_isolation():
    seed()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    with TestClient(app) as client:
        res = client.get("/api/v1/saved-locations/?owner_type=vehicle")
        assert res.status_code == 200
        assert [row["label"] for row in res.json()] == ["A car"]
        assert client.delete("/api/v1/saved-locations/2").status_code == 404
    with Session(engine) as session:
        assert session.get(SavedLocation, 2) is not None


def test_move_car_does_not_assess_other_users_vehicle():
    seed()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    with TestClient(app) as client:
        res = client.post("/api/v1/move-car/recommend", json={"location_id": 2})
        assert res.status_code == 200
        assert res.json()["status"] == "no_location"


