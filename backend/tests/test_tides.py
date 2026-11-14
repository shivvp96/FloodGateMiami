from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


_MOCK_WATER_LEVEL = {
    "metadata": {"name": "Virginia Key"},
    "data": [
        {"t": "2026-11-14 18:00", "v": "1.23", "s": "0.00", "f": "0,0,0,0", "q": "p"},
        {"t": "2026-11-14 18:06", "v": "1.25", "s": "0.00", "f": "0,0,0,0", "q": "p"},
    ],
}

_MOCK_PREDICTIONS = {
    "predictions": [
        {"t": "2026-11-14 18:00", "v": "1.10", "type": "L"},
        {"t": "2026-11-15 20:30", "v": "2.95", "type": "H"},
        {"t": "2026-11-16 09:15", "v": "0.45", "type": "L"},
        {"t": "2026-11-16 21:45", "v": "3.10", "type": "H"},
    ]
}

# 6-minute predictions matching the observation timestamps exactly.
_MOCK_SIX_MIN_PREDICTIONS = {
    "predictions": [
        {"t": "2026-11-14 18:00", "v": "1.20"},
        {"t": "2026-11-14 18:06", "v": "1.22"},
        {"t": "2026-11-14 18:12", "v": "1.24"},
    ]
}

# 6-minute predictions that do NOT contain the observation timestamp.
_MOCK_SIX_MIN_NO_MATCH = {
    "predictions": [
        {"t": "2026-11-14 17:00", "v": "0.90"},
        {"t": "2026-11-14 17:06", "v": "0.95"},
    ]
}


def test_tides_lookup_returns_observations_predictions_and_king_tide() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_WATER_LEVEL),
                _response(200, _MOCK_PREDICTIONS),
                _response(200, _MOCK_SIX_MIN_PREDICTIONS),
            ]
            response = client.get("/api/v1/tides/lookup")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["station_id"] == "8723214"
    assert data["current_water_level"]["value"] == 1.25
    assert data["next_high_tide"]["value"] == 2.95
    assert len(data["upcoming_high_tides"]) == 2
    assert data["king_tide_watch"]["active"] is True
    assert len(data["king_tide_watch"]["next_high_tides_above_threshold"]) == 2


def test_tides_comparison_uses_exact_6min_prediction_timestamp() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_WATER_LEVEL),
                _response(200, _MOCK_PREDICTIONS),
                _response(200, _MOCK_SIX_MIN_PREDICTIONS),
            ]
            response = client.get("/api/v1/tides/lookup")

    data = response.json()
    # Observation at 18:06 (1.25 ft) must align to the 6-min prediction at 18:06 (1.22 ft),
    # NOT to the nearby hilo low at 18:00 (1.10 ft).
    assert data["comparison"]["observed_value"] == 1.25
    assert data["comparison"]["predicted_value"] == 1.22
    assert data["comparison"]["difference"] == pytest.approx(1.25 - 1.22, abs=0.001)
    assert data["comparison"]["timestamp"] == "2026-11-14 18:06"


def test_tides_comparison_unavailable_when_no_exact_prediction() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_WATER_LEVEL),
                _response(200, _MOCK_PREDICTIONS),
                _response(200, _MOCK_SIX_MIN_NO_MATCH),
            ]
            response = client.get("/api/v1/tides/lookup")

    data = response.json()
    assert data["comparison"] is None


def test_tides_comparison_unavailable_when_6min_fetch_fails() -> None:
    from httpx import ConnectError

    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_WATER_LEVEL),
                _response(200, _MOCK_PREDICTIONS),
                ConnectError("6-min prediction fetch failed"),
            ]
            response = client.get("/api/v1/tides/lookup")

    data = response.json()
    assert data["status"] == "ok"
    assert data["comparison"] is None


def test_tides_lookup_handles_noaa_failure() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            from httpx import ConnectError
            mock_get.side_effect = ConnectError("connection failed")
            response = client.get("/api/v1/tides/lookup")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["current_water_level"] is None
    assert data["message"].startswith("NOAA tide data is unavailable")


def test_tides_lookup_no_observation_returns_predictions_only() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, {"data": []}),
                _response(200, _MOCK_PREDICTIONS),
            ]
            response = client.get("/api/v1/tides/lookup")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "predictions_only"
    assert data["current_water_level"] is None
    assert data["comparison"] is None
    assert data["next_high_tide"] is not None


def test_tides_threshold_labeled_as_floodguard_planning_reference() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_WATER_LEVEL),
                _response(200, _MOCK_PREDICTIONS),
                _response(200, _MOCK_SIX_MIN_PREDICTIONS),
            ]
            response = client.get("/api/v1/tides/lookup")

    data = response.json()
    source = data["king_tide_watch"]["threshold_source"]
    assert "Configurable FloodGuard planning reference" in source
    assert "not an official NOAA flood threshold" in source


def _response(status_code: int, json_payload: dict) -> object:
    class _MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                from httpx import HTTPStatusError
                raise HTTPStatusError("error", request=None, response=self)

        def json(self) -> dict:
            return json_payload

    return _MockResponse()
