from datetime import UTC, datetime
from typing import Any

import httpx

from ..address_lookup.service import LookupConfig, arcgis_fema_flood_zones
from ..tides.service import get_tides
from ..weather.service import get_weather_for_coordinates
from .models import AskFloodGuardRequest, AskFloodGuardResponse


SYSTEM_PROMPT = (
    "You are FloodGuard Miami, a flood-safety assistant for Miami-Dade residents. "
    "Answer ONLY using the verified government data provided in the context block "
    "(FEMA flood zone from the Miami-Dade ArcGIS FEMA layer, NWS forecasts and alerts, "
    "and NOAA tide predictions). If the context does not contain the answer, say so "
    "plainly and suggest the relevant official source (weather.gov, fema.gov, "
    "tidesandcurrents.noaa.gov). Never invent flood depths, zone designations, or "
    "alert details. Always include a short plain-language safety caveat that mapped "
    "flood zones are planning references, not real-time street-flood forecasts. "
    "Keep answers under 200 words."
)


def _config_from_env() -> LookupConfig:
    import os

    return LookupConfig(
        census_base_url=os.environ.get("CENSUS_GEOCODER_BASE_URL", "https://geocoding.geo.census.gov"),
        arcgis_flood_zones_url=os.environ.get(
            "ARCGIS_FEMA_FLOOD_ZONES_URL",
            "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query",
        ),
        request_timeout_s=float(os.environ.get("LOOKUP_REQUEST_TIMEOUT_S", "8")),
        cache_ttl_s=int(os.environ.get("LOOKUP_CACHE_TTL_S", "300")),
    )


async def _gather_grounding(question: str, lat: float | None, lon: float | None) -> dict[str, Any]:
    """Fetch live FEMA, NWS, and NOAA data to ground the answer. Never simulated."""
    grounding: dict[str, Any] = {"fema": None, "weather": None, "tides": None}

    async def _tides():
        t = await get_tides()
        return {
            "status": t.status,
            "current_water_level": t.current_water_level,
            "next_high_tide": t.next_high_tide,
            "king_tide_watch": {
                "active": t.king_tide_watch.active,
                "next_high_tides_above_threshold": t.king_tide_watch.next_high_tides_above_threshold,
            },
            "message": t.message,
        }

    tasks = []
    if lat is not None and lon is not None:
        # FEMA zone for the exact coordinates
        from ..address_lookup.service import arcgis_fema_flood_zones

        async def _fema():
            zone, attrs, source = await arcgis_fema_flood_zones(lat, lon, config=_config_from_env())
            return {"designation": zone.designation, "zone_type": zone.zone_type, "raw_attributes": attrs, "source": source}

        async def _weather():
            w = await get_weather_for_coordinates(lat, lon)
            return {
                "status": w.status,
                "flood_alert_count": w.flood_alert_count,
                "active_alerts": [
                    {"event": a.event, "headline": a.headline, "severity": a.severity, "area": a.area_desc}
                    for a in w.active_alerts
                ],
                "hourly_forecast_next_12h": [
                    {"time": p.start_time, "temp_f": p.temperature, "forecast": p.short_forecast, "precip_chance": p.precipitation_chance}
                    for p in w.hourly_periods
                ],
                "message": w.message,
            }

        tasks.append(("fema", _fema()))
        tasks.append(("weather", _weather()))

    tasks.append(("tides", _tides()))

    import asyncio

    results = await asyncio.gather(*(t for _, t in tasks), return_exceptions=True)
    for (name, _coro), result in zip(tasks, results):
        if isinstance(result, Exception):
            grounding[name] = {"error": f"{type(result).__name__}: data unavailable"}
        else:
            grounding[name] = result
    return grounding


def _llm_config() -> tuple[str, str, str, str] | None:
    """Return (api_key, base_url, model, provider) or None if not configured.

    provider is "gemini" for Google's native generateContent API, or
    "openai" for any OpenAI-compatible chat/completions endpoint.
    """
    import os

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "gemini":
        base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
        model = model or "gemini-flash-lite-latest"
    return api_key, base_url, model, provider


async def ask_floodguard(request: AskFloodGuardRequest) -> AskFloodGuardResponse:
    import asyncio
    import json
    import os

    now = datetime.now(UTC)

    llm = _llm_config()
    if llm is None:
        return AskFloodGuardResponse(
            status="unavailable",
            answer="Ask FloodGuard is not configured. An administrator must set the LLM_API_KEY environment variable.",
            question=request.question,
            grounding={},
            retrieved_at=now,
            message="LLM API key not configured",
        )

    api_key, base_url, model, provider = llm

    grounding = await _gather_grounding(request.question, request.latitude, request.longitude)

    user_prompt = (
        f"Question from a Miami resident: {request.question}\n\n"
        f"Verified live government data (JSON):\n{json.dumps(grounding, default=str)}\n\n"
        f"Answer using only this data."
    )

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            if provider == "gemini":
                resp = await client.post(
                    f"{base_url}/models/{model}:generateContent",
                    headers={"X-goog-api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": user_prompt}]}],
                        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.2},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.2,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError) as exc:
        return AskFloodGuardResponse(
            status="unavailable",
            answer="Ask FloodGuard cannot reach the AI service right now. Please try again shortly.",
            question=request.question,
            grounding=grounding,
            retrieved_at=now,
            message=f"LLM provider error ({type(exc).__name__})",
        )

    return AskFloodGuardResponse(
        status="ok",
        answer=answer,
        question=request.question,
        grounding=grounding,
        model=model,
        retrieved_at=now,
        message=None,
    )
