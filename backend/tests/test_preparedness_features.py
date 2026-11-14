"""Private preparedness plan and user incident journal API tests."""
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.address_lookup.models import GeoCoordinates
from app.auth import get_current_user_id
from app.db import engine
from app.flood_reports.models import FloodReport
from app.main import create_app


A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def reset():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_family_plan_is_private_and_persistent():
    reset()
    app = create_app()
    identity = {"id": A}
    app.dependency_overrides[get_current_user_id] = lambda: identity["id"]
    with TestClient(app) as client:
        plan = {"meeting_place": "Community center", "emergency_contact": "Family friend", "notes": "Bring pets",
                "water_ready": True, "medication_ready": False, "documents_ready": True, "evacuation_route_ready": False}
        assert client.put("/api/v1/family-plan/", json=plan).status_code == 200
        assert client.get("/api/v1/family-plan/").json() == plan
        identity["id"] = B
        other = client.get("/api/v1/family-plan/").json()
        assert other["meeting_place"] == ""
        assert not other["water_ready"]
        identity["id"] = A
        assert client.get("/api/v1/family-plan/").json() == plan


def test_flood_reports_private_and_unverified():
    reset()
    app = create_app()
    identity = {"id": A}
    app.dependency_overrides[get_current_user_id] = lambda: identity["id"]

    async def fake_geocode(address, *, config):
        return address, GeoCoordinates(latitude=25.77, longitude=-80.19), 100.0

    with TestClient(app) as client, patch("app.flood_reports.routes.census_geocode", new=fake_geocode):
        payload = {"address": "111 NW 1st St Miami FL", "description": "I saw six inches of water near the curb",
                   "observed_at": "2026-11-14T21:00:00Z"}
        saved = client.post("/api/v1/reports/", json=payload)
        assert saved.status_code == 201, saved.text
        report_id = saved.json()["id"]
        assert saved.json()["verification_status"] == "unverified"
        assert len(client.get("/api/v1/reports/").json()) == 1
        identity["id"] = B
        assert client.get("/api/v1/reports/").json() == []
        assert client.delete(f"/api/v1/reports/{report_id}").status_code == 404
        identity["id"] = A
        assert client.delete(f"/api/v1/reports/{report_id}").status_code == 204
        assert client.get("/api/v1/reports/").json() == []
