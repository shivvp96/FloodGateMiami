from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.db import engine
from app.main import create_app
from app.saved_locations.models import SavedLocation


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def _insert(session: Session, **kwargs) -> SavedLocation:
    loc = SavedLocation(**kwargs)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


def _fake_tides(next_high_value: float = 1.5, threshold: float = 2.8):
    return type("T", (), {
        "status": "ok",
        "current_water_level": None,
        "next_high_tide": None if next_high_value is None else type("P", (), {
            "value": next_high_value, "timestamp": "2026-11-15 05:16",
        })(),
        "message": None,
        "king_tide_watch": type("K", (), {
            "active": False,
            "threshold_value": threshold,
            "next_high_tides_above_threshold": [],
            "message": "none",
        })(),
    })()


def _fake_weather(alerts: list = []):
    return type("W", (), {
        "status": "flood_alerts" if alerts else "no_alerts",
        "flood_alert_count": len(alerts),
        "active_alerts": alerts,
        "hourly_periods": [],
        "message": None,
    })()


def _alert(event: str):
    return type("A", (), {
        "event": event, "headline": f"{event} in effect", "severity": "Warning",
        "area_desc": "Miami-Dade", "is_flood_related": True,
    })()


def _fema_zone(designation):
    return type("Z", (), {"designation": designation, "zone_type": None})(), {}, "https://arcgis.example"


def test_move_car_requires_positive_location_id() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/move-car/recommend", json={"location_id": 0}).status_code == 422
        assert client.post("/api/v1/move-car/recommend", json={"location_id": -3}).status_code == 422


def test_move_car_unknown_location_returns_no_location() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/move-car/recommend", json={"location_id": 9999})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_location"
    assert data["recommendation"] == "no_recommendation"


def test_move_car_requires_vehicle_type() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with Session(engine) as session:
            _insert(session, owner_type="property", label="Home", address="A", latitude=25.7, longitude=-80.2)
        response = client.post("/api/v1/move-car/recommend", json={"location_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "no_location"


def test_move_car_without_coordinates_is_insufficient_data() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with Session(engine) as session:
            _insert(session, owner_type="vehicle", label="My car", address="B", latitude=None, longitude=None)
        response = client.post("/api/v1/move-car/recommend", json={"location_id": 1})
    data = response.json()
    assert data["status"] == "insufficient_data"
    assert "coordinates" in data["message"].lower()


def test_move_car_no_risk_stay_parked() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with Session(engine) as session:
            _insert(session, owner_type="vehicle", label="My car", address="B", latitude=25.7, longitude=-80.2)
        with patch("app.move_car.service.arcgis_fema_flood_zones", new=AsyncMock(return_value=_fema_zone("X"))), \
             patch("app.move_car.service.get_weather_for_coordinates", new=AsyncMock(return_value=_fake_weather())), \
             patch("app.move_car.service.get_tides", new=AsyncMock(return_value=_fake_tides())):
            response = client.post("/api/v1/move-car/recommend", json={"location_id": 1})
    data = response.json()
    assert data["status"] == "ok"
    assert data["recommendation"] == "stay_parked"
    assert data["risk_factors"] == []
    assert "cannot confirm" in data["disclaimer"]


def test_move_car_high_risk_zone_surfaces_candidates() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with Session(engine) as session:
            vehicle = _insert(session, owner_type="vehicle", label="My car", address="B", latitude=25.775, longitude=-80.196)
            vehicle_id = vehicle.id
            _insert(session, owner_type="vehicle", label="Garage", address="C", latitude=25.9, longitude=-80.3)

        zone_map = {
            (25.775, -80.196): "AE",   # vehicle: high risk
            (25.9, -80.3): "X",        # candidate: low risk
        }

        async def _fema(lat, lon, *, config):
            return _fema_zone(zone_map[(lat, lon)])

        with patch("app.move_car.service.arcgis_fema_flood_zones", new=_fema), \
             patch("app.move_car.service.get_weather_for_coordinates", new=AsyncMock(return_value=_fake_weather())), \
             patch("app.move_car.service.get_tides", new=AsyncMock(return_value=_fake_tides())):
            response = client.post("/api/v1/move-car/recommend", json={"location_id": vehicle_id})
    data = response.json()
    assert data["status"] == "ok"
    assert data["recommendation"] == "consider_moving"
    kinds = [rf["kind"] for rf in data["risk_factors"]]
    assert "fema_zone" in kinds
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["label"] == "Garage"
    assert data["candidates"][0]["fema_zone"] == "X"
    assert "lower mapped flood hazard" in data["candidates"][0]["note"]


def test_move_car_flood_alert_triggers_recommendation_without_candidates() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with Session(engine) as session:
            vehicle = _insert(session, owner_type="vehicle", label="My car", address="B", latitude=25.775, longitude=-80.196)
            vehicle_id = vehicle.id
            # Candidate with NO verified coordinates — must never be surfaced
            _insert(session, owner_type="vehicle", label="Garage", address="C", latitude=None, longitude=None)

        with patch("app.move_car.service.arcgis_fema_flood_zones", new=AsyncMock(return_value=_fema_zone("X"))), \
             patch("app.move_car.service.get_weather_for_coordinates", new=AsyncMock(return_value=_fake_weather([_alert("Flood Warning")]))), \
             patch("app.move_car.service.get_tides", new=AsyncMock(return_value=_fake_tides())):
            response = client.post("/api/v1/move-car/recommend", json={"location_id": vehicle_id})
    data = response.json()
    assert data["recommendation"] == "consider_moving"
    assert any(rf["kind"] == "flood_alert" for rf in data["risk_factors"])
    assert data["candidates"] == []
    assert "no alternative saved locations" in data["message"]


def test_move_car_unverifiable_data_returns_insufficient() -> None:
    reset_database()
    import httpx

    async def _down(lat, lon, *, config):
        raise httpx.ConnectError("arcgis down")

    with TestClient(create_app()) as client:
        with Session(engine) as session:
            vehicle = _insert(session, owner_type="vehicle", label="My car", address="B", latitude=25.775, longitude=-80.196)
        with patch("app.move_car.service.arcgis_fema_flood_zones", new=_down), \
             patch("app.move_car.service.get_weather_for_coordinates", new=AsyncMock(return_value=_fake_weather())), \
             patch("app.move_car.service.get_tides", new=AsyncMock(return_value=_fake_tides())):
            response = client.post("/api/v1/move-car/recommend", json={"location_id": vehicle.id})
    data = response.json()
    assert data["status"] == "insufficient_data"
    assert data["recommendation"] == "no_recommendation"
