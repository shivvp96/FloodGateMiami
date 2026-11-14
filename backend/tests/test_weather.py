from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import create_app


_MOCK_POINTS = {
    "properties": {
        "forecastHourly": "https://api.weather.gov/gridpoints/MFL/25,55/forecast/hourly",
    }
}

_MOCK_HOURLY = {
    "properties": {
        "periods": [
            {
                "number": 1,
                "startTime": "2026-11-14T14:00:00-05:00",
                "endTime": "2026-11-14T15:00:00-05:00",
                "isDaytime": True,
                "temperature": 82,
                "temperatureUnit": "F",
                "shortForecast": "Slight Chance Showers And Thunderstorms",
                "detailedForecast": "A slight chance of showers and thunderstorms.",
                "windSpeed": "10 mph",
                "windDirection": "SE",
                "probabilityOfPrecipitation": {"value": 30},
            },
            {
                "number": 2,
                "startTime": "2026-11-14T15:00:00-05:00",
                "endTime": "2026-11-14T16:00:00-05:00",
                "isDaytime": True,
                "temperature": 83,
                "temperatureUnit": "F",
                "shortForecast": "Chance Showers And Thunderstorms",
                "detailedForecast": "A chance of showers and thunderstorms.",
                "windSpeed": "12 mph",
                "windDirection": "SE",
                "probabilityOfPrecipitation": {"value": 40},
            },
        ]
    }
}

_MOCK_NO_ALERTS = {"features": []}

_MOCK_FLOOD_ALERT = {
    "features": [
        {
            "properties": {
                "id": "urn:oid:2.49.0.1.840.0.flood",
                "event": "Flash Flood Warning",
                "headline": "Flash Flood Warning issued for Miami-Dade",
                "severity": "Severe",
                "urgency": "Immediate",
                "certainty": "Likely",
                "effective": "2026-11-14T13:00:00-05:00",
                "expires": "2026-11-14T18:00:00-05:00",
                "description": "Flash flooding caused by excessive rainfall is imminent.",
                "instruction": "Move to higher ground.",
                "senderName": "NWS Miami FL",
                "areaDesc": "Coastal Miami-Dade",
            }
        }
    ]
}


def test_weather_lookup_returns_forecast_and_no_alerts() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_POINTS),
                _response(200, _MOCK_HOURLY),
                _response(200, _MOCK_NO_ALERTS),
            ]
            response = client.get("/api/v1/weather/lookup", params={"lat": 25.7751, "lon": -80.1963})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_alerts"
    assert data["flood_alert_count"] == 0
    assert len(data["hourly_periods"]) == 2
    assert data["hourly_periods"][0]["temperature"] == 82


def test_weather_lookup_detects_flood_related_alert() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                _response(200, _MOCK_POINTS),
                _response(200, _MOCK_HOURLY),
                _response(200, _MOCK_FLOOD_ALERT),
            ]
            response = client.get("/api/v1/weather/lookup", params={"lat": 25.7751, "lon": -80.1963})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "flood_alerts"
    assert data["flood_alert_count"] == 1
    assert data["active_alerts"][0]["is_flood_related"] is True


def test_weather_lookup_handles_nws_failure() -> None:
    with TestClient(create_app()) as client:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            from httpx import ConnectError
            mock_get.side_effect = ConnectError("connection failed")
            response = client.get("/api/v1/weather/lookup", params={"lat": 25.7751, "lon": -80.1963})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["flood_alert_count"] == 0
    assert "unavailable" in data["message"].lower()


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
