import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from .models import HourlyForecastPeriod, NWSWeatherResponse, WeatherAlert

NWS_BASE_URL = "https://api.weather.gov"
USER_AGENT = os.environ.get(
    "NWS_USER_AGENT",
    "FloodGuardMiami (floodguard.miami@example.com)",
)

# Events considered flood-related per NWS API naming conventions.
_FLOOD_EVENT_TERMS = frozenset({
    "flood", "flooding", "flash flood", "coastal flood", "lakeshore flood",
    "flood advisory", "flash flood warning", "flood warning", "coastal flood warning",
    "coastal flood advisory", "river flood warning", "urban flooding",
})


def _is_flood_related(event: Optional[str]) -> bool:
    if not event:
        return False
    normalized = event.lower()
    return any(term in normalized for term in _FLOOD_EVENT_TERMS)


@dataclass(frozen=True)
class WeatherConfig:
    base_url: str
    user_agent: str
    timeout_s: float
    cache_ttl_s: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_s: int) -> None:
        self.value = value
        self.expires_at = _utc_now() + timedelta(seconds=ttl_s)

    def is_valid(self) -> bool:
        return _utc_now() < self.expires_at


class WeatherClient:
    def __init__(self, config: WeatherConfig) -> None:
        self._config = config
        self._cache: dict[str, _CacheEntry] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._config.user_agent,
            "Accept": "application/geo+json",
        }

    def _cache_key(self, lat: float, lon: float, resource: str) -> str:
        return f"{resource}:{lat:.4f}:{lon:.4f}"

    def _get_cached(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            return entry.value
        self._cache.pop(key, None)
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        self._cache[key] = _CacheEntry(value, self._config.cache_ttl_s)

    async def _get(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url, headers=self._headers(), timeout=self._config.timeout_s)
        response.raise_for_status()
        return response.json()

    async def discover_hourly_forecast_url(self, lat: float, lon: float) -> Optional[str]:
        key = self._cache_key(lat, lon, "points")
        cached = self._get_cached(key)
        if cached:
            return cached

        url = f"{self._config.base_url}/points/{lat:.4f},{lon:.4f}"
        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            payload = await self._get(client, url)

        forecast_url = payload.get("properties", {}).get("forecastHourly")
        if forecast_url:
            self._set_cached(key, forecast_url)
        return forecast_url

    async def fetch_hourly_forecast(self, forecast_url: str) -> list[HourlyForecastPeriod]:
        cached = self._get_cached(forecast_url)
        if cached:
            return [HourlyForecastPeriod(**p) for p in cached]

        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            payload = await self._get(client, forecast_url)

        raw_periods = payload.get("properties", {}).get("periods", [])
        periods = [
            HourlyForecastPeriod(
                number=p.get("number"),
                start_time=p.get("startTime"),
                end_time=p.get("endTime"),
                is_daytime=p.get("isDaytime"),
                temperature=p.get("temperature"),
                temperature_unit=p.get("temperatureUnit"),
                short_forecast=p.get("shortForecast"),
                detailed_forecast=p.get("detailedForecast"),
                wind_speed=p.get("windSpeed"),
                wind_direction=p.get("windDirection"),
                precipitation_chance=p.get("probabilityOfPrecipitation", {}).get("value"),
            )
            for p in raw_periods[:12]
        ]
        self._set_cached(forecast_url, raw_periods[:12])
        return periods

    async def fetch_active_alerts(self, lat: float, lon: float) -> list[WeatherAlert]:
        url = f"{self._config.base_url}/alerts/active?point={lat:.4f},{lon:.4f}"
        cached = self._get_cached(url)
        if cached:
            return [WeatherAlert(**a) for a in cached]

        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            payload = await self._get(client, url)

        raw_features = payload.get("features", [])
        alerts = [
            WeatherAlert(
                id=f.get("properties", {}).get("id") or f"alert-{idx}",
                event=f.get("properties", {}).get("event") or "Unknown Alert",
                headline=f.get("properties", {}).get("headline") or "",
                severity=f.get("properties", {}).get("severity"),
                urgency=f.get("properties", {}).get("urgency"),
                certainty=f.get("properties", {}).get("certainty"),
                effective=f.get("properties", {}).get("effective"),
                expires=f.get("properties", {}).get("expires"),
                description=f.get("properties", {}).get("description") or "",
                instruction=f.get("properties", {}).get("instruction"),
                sender_name=f.get("properties", {}).get("senderName"),
                area_desc=f.get("properties", {}).get("areaDesc"),
                is_flood_related=_is_flood_related(f.get("properties", {}).get("event")),
                source_url=f"{self._config.base_url}/alerts/{f.get('properties', {}).get('id', '')}",
            )
            for idx, f in enumerate(raw_features)
        ]
        self._set_cached(url, [a.model_dump() for a in alerts])
        return alerts


def _config_from_env() -> WeatherConfig:
    return WeatherConfig(
        base_url=os.environ.get("NWS_BASE_URL", NWS_BASE_URL),
        user_agent=os.environ.get("NWS_USER_AGENT", USER_AGENT),
        timeout_s=float(os.environ.get("NWS_TIMEOUT_S", "10")),
        cache_ttl_s=int(os.environ.get("NWS_CACHE_TTL_S", "120")),
    )


async def get_weather_for_coordinates(lat: float, lon: float) -> NWSWeatherResponse:
    config = _config_from_env()
    client = WeatherClient(config)
    rounded_lat = round(lat, 4)
    rounded_lon = round(lon, 4)

    try:
        forecast_url = await asyncio.wait_for(
            client.discover_hourly_forecast_url(rounded_lat, rounded_lon),
            timeout=config.timeout_s + 2,
        )
        if not forecast_url:
            return NWSWeatherResponse(
                status="unavailable",
                coordinates={"latitude": rounded_lat, "longitude": rounded_lon},
                source=config.base_url,
                flood_alert_count=0,
                retrieved_at=_utc_now(),
                message="NWS did not provide a forecast URL for this location.",
            )

        forecast_task = client.fetch_hourly_forecast(forecast_url)
        alerts_task = client.fetch_active_alerts(rounded_lat, rounded_lon)
        hourly_periods, active_alerts = await asyncio.gather(forecast_task, alerts_task)

        flood_alert_count = sum(1 for a in active_alerts if a.is_flood_related)
        status = "flood_alerts" if flood_alert_count else "no_alerts"
        if flood_alert_count:
            status = "flood_alerts"
        elif active_alerts:
            status = "no_alerts"
        else:
            status = "no_alerts"

        return NWSWeatherResponse(
            status=status,
            coordinates={"latitude": rounded_lat, "longitude": rounded_lon},
            forecast_url=forecast_url,
            hourly_periods=hourly_periods,
            active_alerts=active_alerts,
            flood_alert_count=flood_alert_count,
            source=config.base_url,
            retrieved_at=_utc_now(),
            message=None,
        )
    except (httpx.HTTPError, httpx.TimeoutException, asyncio.TimeoutError) as exc:
        return NWSWeatherResponse(
            status="unavailable",
            coordinates={"latitude": rounded_lat, "longitude": rounded_lon},
            source=config.base_url,
            flood_alert_count=0,
            retrieved_at=_utc_now(),
            message=f"NWS data is unavailable ({type(exc).__name__}).",
        )
