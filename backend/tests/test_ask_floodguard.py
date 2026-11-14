from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import create_app


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def test_ask_requires_question_and_coordinate_pair() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/ai/ask", json={"question": "ab"}).status_code == 422
        assert client.post("/api/v1/ai/ask", json={"question": "am I at risk?", "latitude": 25.7}).status_code == 422
        assert client.post(
            "/api/v1/ai/ask", json={"question": "am I at risk?", "latitude": 0, "longitude": 0}
        ).status_code == 422


def test_ask_without_api_key_returns_unavailable() -> None:
    reset_database()
    with TestClient(create_app()) as client:
        with patch.dict("os.environ", {}, clear=False):
            import os
            saved = {k: os.environ.pop(k) for k in ("LLM_API_KEY", "OPENAI_API_KEY") if k in os.environ}
            try:
                response = client.post(
                    "/api/v1/ai/ask",
                    json={"question": "Is my street going to flood tonight?", "latitude": 25.775, "longitude": -80.196},
                )
            finally:
                os.environ.update(saved)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert "LLM_API_KEY" in data["answer"]
    assert data["message"] == "LLM API key not configured"


def test_ask_with_key_returns_grounded_answer_and_context() -> None:
    reset_database()

    fake_tides = type("T", (), {
        "status": "ok", "current_water_level": None, "next_high_tide": None, "message": None,
        "king_tide_watch": type("K", (), {"active": False, "next_high_tides_above_threshold": []})(),
    })()

    async def _fake_llm_post(self, url, **kwargs):
        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "Based on official FEMA and NWS data, your area is in zone AE."}}]}

        return R()

    with TestClient(create_app()) as client:
        with patch.dict("os.environ", {"LLM_API_KEY": "test-key-123"}):
            with patch("app.ai.service.get_weather_for_coordinates", new=AsyncMock(return_value=type("W", (), {
                "status": "no_alerts", "flood_alert_count": 0, "active_alerts": [], "hourly_periods": [], "message": None,
            })())), \
                 patch("app.ai.service.get_tides", new=AsyncMock(return_value=fake_tides)), \
                 patch("app.ai.service.arcgis_fema_flood_zones", new=AsyncMock(return_value=(
                     type("Z", (), {"designation": "AE", "zone_type": None})(), {}, "https://arcgis.example"
                 ))), \
                 patch("httpx.AsyncClient.post", new=_fake_llm_post):
                response = client.post(
                    "/api/v1/ai/ask",
                    json={"question": "Is my street going to flood tonight?", "latitude": 25.775, "longitude": -80.196},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "zone AE" in data["answer"]
    assert data["grounding"]["fema"]["designation"] == "AE"
    assert data["model"]


def test_ask_llm_provider_failure_is_explicit() -> None:
    reset_database()
    import httpx

    async def _boom(self, url, **kwargs):
        raise httpx.ConnectError("llm down")

    with TestClient(create_app()) as client:
        with patch.dict("os.environ", {"LLM_API_KEY": "test-key-123"}):
            with patch("app.ai.service.get_weather_for_coordinates", new=AsyncMock(return_value=type("W", (), {
                "status": "no_alerts", "flood_alert_count": 0, "active_alerts": [], "hourly_periods": [], "message": None,
            })())), \
                 patch("app.ai.service.get_tides", new=AsyncMock(return_value=type("T", (), {
                     "status": "ok", "current_water_level": None, "next_high_tide": None, "message": None,
                     "king_tide_watch": type("K", (), {"active": False, "next_high_tides_above_threshold": []})(),
                 })())), \
                 patch("app.ai.service.arcgis_fema_flood_zones", new=AsyncMock(return_value=(
                     type("Z", (), {"designation": "AE", "zone_type": None})(), {}, "https://arcgis.example"
                 ))), \
                 patch("httpx.AsyncClient.post", new=_boom):
                response = client.post(
                    "/api/v1/ai/ask",
                    json={"question": "Is my street going to flood tonight?", "latitude": 25.775, "longitude": -80.196},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unavailable"
    assert "cannot reach" in data["answer"]
