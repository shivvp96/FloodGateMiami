import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from .models import (
    KingTideWatch,
    TideComparison,
    TidePrediction,
    TidesResponse,
    WaterLevelObservation,
)

NOAA_COOPS_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

# Virginia Key, FL station.
DEFAULT_STATION_ID = "8723214"
DEFAULT_DATUM = "MLLW"
DEFAULT_UNITS = "english"  # feet

# Local reference threshold for predicted high tides that may cause nuisance/sunny-day flooding
# in low-lying Miami areas. Documented here as a conservative planning value based on historical
# local tide-gauge exceedances during King Tide season. It is NOT a FEMA elevation and NOT a
# confirmed street-flood depth.
KING_TIDE_THRESHOLD_FT = float(os.environ.get("KING_TIDE_THRESHOLD_FT", "2.8"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TideConfig:
    station_id: str
    datum: str
    units: str
    base_url: str
    timeout_s: float
    cache_ttl_s: int

    @classmethod
    def from_env(cls) -> "TideConfig":
        return cls(
            station_id=os.environ.get("NOAA_STATION_ID", DEFAULT_STATION_ID),
            datum=os.environ.get("NOAA_TIDE_DATUM", DEFAULT_DATUM),
            units=os.environ.get("NOAA_TIDE_UNITS", DEFAULT_UNITS),
            base_url=os.environ.get("NOAA_COOPS_URL", NOAA_COOPS_URL),
            timeout_s=float(os.environ.get("NOAA_TIMEOUT_S", "10")),
            cache_ttl_s=int(os.environ.get("NOAA_CACHE_TTL_S", "120")),
        )

    @property
    def threshold(self) -> float:
        return float(os.environ.get("KING_TIDE_THRESHOLD_FT", str(KING_TIDE_THRESHOLD_FT)))


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_s: int) -> None:
        self.value = value
        self.expires_at = _utc_now() + timedelta(seconds=ttl_s)

    def is_valid(self) -> bool:
        return _utc_now() < self.expires_at


class TidesClient:
    def __init__(self, config: TideConfig) -> None:
        self._config = config
        self._cache: dict[str, _CacheEntry] = {}

    def _cache_key(self, resource: str, params: dict[str, str]) -> str:
        return f"{resource}:{hash(tuple(sorted(params.items())))}"

    def _get_cached(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            return entry.value
        self._cache.pop(key, None)
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        self._cache[key] = _CacheEntry(value, self._config.cache_ttl_s)

    def _params(self, **extra: str) -> dict[str, str]:
        base = {
            "station": self._config.station_id,
            "datum": self._config.datum,
            "units": self._config.units,
            "time_zone": "gmt",  # NOAA uses +0000 when time_zone=gmt; labels returned clearly
            "format": "json",
        }
        base.update(extra)
        return base

    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            response = await client.get(self._config.base_url, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_latest_water_level(self, begin_date: str, end_date: str) -> Optional[WaterLevelObservation]:
        params = self._params(
            product="water_level",
            begin_date=begin_date,
            end_date=end_date,
            interval="6",  # use latest 6-min sample
        )
        key = self._cache_key("water_level", params)
        cached = self._get_cached(key)
        payload = cached if cached is not None else await self._get(params)
        if cached is None:
            self._set_cached(key, payload)

        data = payload.get("data", [])
        if not data:
            return None

        latest = data[-1]
        try:
            value = float(latest["v"])
        except (KeyError, ValueError, TypeError):
            return None

        return WaterLevelObservation(
            timestamp=latest.get("t", ""),
            value=value,
            units="ft",
            datum=self._config.datum,
        )

    async def fetch_predictions(self, begin_date: str, end_date: str) -> list[TidePrediction]:
        params = self._params(
            product="predictions",
            begin_date=begin_date,
            end_date=end_date,
            interval="hilo",
        )
        key = self._cache_key("predictions", params)
        cached = self._get_cached(key)
        payload = cached if cached is not None else await self._get(params)
        if cached is None:
            self._set_cached(key, payload)

        predictions = payload.get("predictions", [])
        result: list[TidePrediction] = []
        for p in predictions:
            try:
                value = float(p["v"])
            except (KeyError, ValueError, TypeError):
                continue
            result.append(
                TidePrediction(
                    timestamp=p.get("t", ""),
                    value=value,
                    type=p.get("type", ""),
                    units="ft",
                )
            )
        return result


    async def fetch_six_minute_predictions(self, begin_date: str, end_date: str) -> dict[str, float]:
        """Fetch 6-minute tide predictions keyed by timestamp string (YYYY-MM-DD HH:MM).

        These use the same station, datum, units, and UTC timezone as observations, enabling
        exact timestamp alignment for observed-minus-predicted comparisons.
        """
        params = self._params(
            product="predictions",
            begin_date=begin_date,
            end_date=end_date,
            interval="6",  # 6-minute predictions matching the observation interval
        )
        key = self._cache_key("predictions_6min", params)
        cached = self._get_cached(key)
        payload = cached if cached is not None else await self._get(params)
        if cached is None:
            self._set_cached(key, payload)

        predictions = payload.get("predictions", [])
        result: dict[str, float] = {}
        for p in predictions:
            try:
                result[p["t"]] = float(p["v"])
            except (KeyError, ValueError, TypeError):
                continue
        return result


def _parse_noaa_timestamp(value: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _find_exact_prediction_value(
    observation: WaterLevelObservation,
    six_min_predictions: dict[str, float],
) -> Optional[float]:
    """Return the predicted value at the exact observation timestamp, or None."""
    return six_min_predictions.get(observation.timestamp)


def _build_source_urls(config: TideConfig) -> dict[str, str]:
    return {
        "water_level": (
            f"{config.base_url}?station={config.station_id}&product=water_level"
            f"&datum={config.datum}&units={config.units}&time_zone=gmt&format=json"
        ),
        "predictions": (
            f"{config.base_url}?station={config.station_id}&product=predictions"
            f"&datum={config.datum}&units={config.units}&time_zone=gmt&format=json"
        ),
        "predictions_6min": (
            f"{config.base_url}?station={config.station_id}&product=predictions"
            f"&datum={config.datum}&units={config.units}&time_zone=gmt&format=json&interval=6"
        ),
    }


async def get_tides() -> TidesResponse:
    config = TideConfig.from_env()
    client = TidesClient(config)
    source_urls = _build_source_urls(config)

    now = _utc_now()
    obs_begin = (now - timedelta(hours=2)).strftime("%Y%m%d %H:%M")
    obs_end = now.strftime("%Y%m%d %H:%M")
    pred_begin = now.strftime("%Y%m%d")
    pred_end = (now + timedelta(days=7)).strftime("%Y%m%d")

    try:
        observation, predictions = await asyncio.gather(
            client.fetch_latest_water_level(obs_begin, obs_end),
            client.fetch_predictions(pred_begin, pred_end),
        )
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return TidesResponse(
            status="unavailable",
            station_id=config.station_id,
            king_tide_watch=_king_tide_watch(high_tides=[], threshold=config.threshold),
            source_urls=source_urls,
            retrieved_at=_utc_now(),
            message=f"NOAA tide data is unavailable ({type(exc).__name__}).",
    )


    future_predictions = [
        p for p in predictions
        if (_parse_noaa_timestamp(p.timestamp) or now) >= now
    ]
    high_tides = [p for p in future_predictions if p.type == "H"]
    next_high = high_tides[0] if high_tides else None

    # Fetch 6-minute predictions covering the observation window for exact-timestamp
    # observed-minus-predicted comparison. Same station, datum, units, and UTC timezone.
    comparison: Optional[TideComparison] = None
    if observation is not None:
        try:
            six_min_preds = await client.fetch_six_minute_predictions(obs_begin, obs_end)
            aligned_value = _find_exact_prediction_value(observation, six_min_preds)
            if aligned_value is not None:
                comparison = TideComparison(
                    observed_value=observation.value,
                    predicted_value=aligned_value,
                    difference=round(observation.value - aligned_value, 3),
                    units="ft",
                    timestamp=observation.timestamp,
                )
        except (httpx.HTTPError, httpx.TimeoutException):
            # If the 6-minute prediction fetch fails, comparison stays None (unavailable).
            pass

    status = "ok" if (observation is not None and predictions) else (
        "predictions_only" if predictions else (
            "observations_only" if observation is not None else "unavailable"
        )
    )

    return TidesResponse(
        status=status,
        station_id=config.station_id,
        station_name="Virginia Key, FL",
        current_water_level=observation,
        next_high_tide=next_high,
        upcoming_high_tides=high_tides[:7],
        comparison=comparison,
        king_tide_watch=_king_tide_watch(high_tides, threshold=KING_TIDE_THRESHOLD_FT),
        source_urls=source_urls,
        retrieved_at=_utc_now(),
        message=None,
    )


def _king_tide_watch(high_tides: list[TidePrediction], threshold: float) -> KingTideWatch:
    elevated = [t for t in high_tides if t.value >= threshold]
    return KingTideWatch(
        active=bool(elevated),
        threshold_value=threshold,
        threshold_units="ft MLLW",
        threshold_source="Configurable FloodGuard planning reference for predicted high tides that may produce nuisance flooding in low-lying Miami areas; not an official NOAA flood threshold, not a FEMA elevation, and not a confirmed flood depth.",
        message=(
            "Upcoming predicted high tides are at or above the local reference threshold. "
            "This indicates elevated tide conditions, not confirmed street flooding."
            if elevated
            else "No upcoming predicted high tides exceed the local reference threshold."
        ),
        next_high_tides_above_threshold=elevated[:5],
    )
