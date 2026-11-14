import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlmodel import SQLModel

from .models import AddressLookupResponse, FEMAFloodZone, GeoCoordinates


@dataclass(frozen=True)
class LookupConfig:
    census_base_url: str
    arcgis_flood_zones_url: str
    request_timeout_s: float
    cache_ttl_s: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def census_geocode(address: str, *, config: LookupConfig) -> tuple[str, GeoCoordinates, Optional[float]]:
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=config.request_timeout_s) as client:
        resp = await client.get(
            f"{config.census_base_url}/geocoder/locations/onelineaddress",
            params=params,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    candidates = data.get("result", {}).get("addressMatches") or []
    if not candidates:
        raise ValueError("unmatched_address")

    best = sorted(candidates, key=lambda c: c.get("score") or 0, reverse=True)[0]

    matched_address = best.get("matchedAddress") or ""
    lat = best.get("coordinates", {}).get("y")
    lon = best.get("coordinates", {}).get("x")
    score = best.get("score")

    if not matched_address or lat is None or lon is None:
        raise ValueError("unmatched_address")

    return matched_address, GeoCoordinates(latitude=float(lat), longitude=float(lon)), score


async def arcgis_fema_flood_zones(
    lat: float,
    lon: float,
    *,
    config: LookupConfig,
) -> tuple[FEMAFloodZone, dict[str, str], str]:
    geometry = {
        "x": lon,
        "y": lat,
        "spatialReference": {"wkid": 4326},
    }

    params = {
        "where": "1=1",
        "geometry": json.dumps(geometry),
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "outSR": "4326",
        "resultRecordCount": 1,
        "f": "json",
    }

    async with httpx.AsyncClient(timeout=config.request_timeout_s) as client:
        resp = await client.get(config.arcgis_flood_zones_url, params=params)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    features = data.get("features") or []
    if not features:
        return FEMAFloodZone(), {}, str(config.arcgis_flood_zones_url)

    attrs: dict[str, Any] = features[0].get("attributes") or {}

    designation = str(attrs["FZONE"]) if attrs.get("FZONE") not in (None, "") else None
    # Miami-Dade's layer uses ZONESUBTY; retain support for the alternate spelling.
    zone_type_value = attrs.get("ZONE_SUB_TYPE", attrs.get("ZONESUBTY"))
    zone_type = str(zone_type_value).strip() if zone_type_value not in (None, "") and str(zone_type_value).strip() else None

    raw_attributes = {str(k): str(v) for k, v in attrs.items() if v is not None}

    return (
        FEMAFloodZone(designation=designation, zone_type=zone_type, raw_attributes=raw_attributes),
        raw_attributes.copy(),
        str(config.arcgis_flood_zones_url),
    )


async def address_lookup(address: str, *, config: LookupConfig) -> AddressLookupResponse:
    matched_address, coords, _score = await census_geocode(address, config=config)
    fema_zone, available_attrs, source_url = await arcgis_fema_flood_zones(coords.latitude, coords.longitude, config=config)

    return AddressLookupResponse(
        request_id="addr-lk-unknown",
        matched_address=matched_address,
        coordinates=coords,
        fema_flood_zone=fema_zone,
        source_url=source_url,
        retrieved_at=_utc_now(),
        available_zone_attributes=available_attrs,
    )
