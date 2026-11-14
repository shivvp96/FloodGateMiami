import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlmodel import SQLModel

from .models import (
    AddressLookupResponse,
    FEMAFloodZone,
    FEMAOverlayFeature,
    FEMAOverlayResponse,
    GeoCoordinates,
)


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


def _esri_geometry_to_geojson(esri_geom: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Convert an ArcGIS JSON geometry (rings/paths) to a GeoJSON geometry.

    Esri rings are clockwise-ordered outer rings followed by counter-clockwise holes;
    GeoJSON polygons expect the opposite winding order. We reverse each ring so the
    frontend renders correct fills without relying on Leaflet's winding tolerance.
    """
    if not esri_geom:
        return {"type": "Polygon", "coordinates": []}

    rings = esri_geom.get("rings")
    if rings is not None:
        # Reverse winding order for every ring (Esri CW → GeoJSON CCW).
        reversed_rings = [list(reversed(ring)) for ring in rings]
        # A single ring is a simple Polygon; multiple rings are a Polygon with holes
        # (outer ring first, then interior holes per the GeoJSON spec).
        return {"type": "Polygon", "coordinates": reversed_rings}

    paths = esri_geom.get("paths")
    if paths is not None:
        return {"type": "MultiLineString", "coordinates": paths}

    x = esri_geom.get("x")
    y = esri_geom.get("y")
    if x is not None and y is not None:
        return {"type": "Point", "coordinates": [x, y]}

    points = esri_geom.get("points")
    if points is not None:
        return {"type": "MultiPoint", "coordinates": points}

    return {"type": "Polygon", "coordinates": []}


async def arcgis_fema_overlay_bbox(
    sw_lat: float,
    sw_lon: float,
    ne_lat: float,
    ne_lon: float,
    *,
    config: LookupConfig,
) -> FEMAOverlayResponse:
    """Query Layer 63 for FEMA flood-zone polygons inside the visible bounding box.

    Uses `f=json` with `returnGeometry=true` and converts Esri geometries to GeoJSON
    server-side, because the live service intermittently returns HTTP 500 when asked
    for `f=geojson`. Handles pagination via resultOffset; any upstream failure on a
    later page marks coverage incomplete rather than failing the whole request.
    """
    geometry = json.dumps({
        "xmin": sw_lon,
        "ymin": sw_lat,
        "xmax": ne_lon,
        "ymax": ne_lat,
        "spatialReference": {"wkid": 4326},
    })

    base_params = {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,FZONE,ZONESUBTY,ELEV",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": "50",
    }

    all_features: list[FEMAOverlayFeature] = []
    max_features = 1000
    exceeded_limit = False
    offset = 0
    page_size = 50

    async with httpx.AsyncClient(timeout=config.request_timeout_s) as client:
        while offset < max_features:
            params = {**base_params, "resultOffset": str(offset)}
            resp = None
            for attempt in range(2):
                try:
                    resp = await client.get(config.arcgis_flood_zones_url, params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    # ArcGIS intermittently returns 500 on later pages; retry once,
                    # then treat the viewport as incomplete rather than failing.
                    if exc.response.status_code >= 500 and attempt == 0:
                        continue
                    if exc.response.status_code >= 500:
                        exceeded_limit = True
                        resp = None
                        break
                    raise
            if resp is None:
                break
            data: dict[str, Any] = resp.json()

            features = data.get("features") or []
            if not features:
                break

            for f in features:
                attrs = f.get("attributes") or {}
                geojson_geom = _esri_geometry_to_geojson(f.get("geometry"))
                all_features.append(
                    FEMAOverlayFeature(
                        type="Feature",
                        geometry=geojson_geom,
                        properties=attrs,
                        id=attrs.get("OBJECTID"),
                    )
                )

            if data.get("exceededTransferLimit"):
                exceeded_limit = True
                offset += page_size
            else:
                exceeded_limit = False
                break

            if len(all_features) >= max_features:
                exceeded_limit = True
                break

    status = "incomplete" if exceeded_limit else "ok"
    message = None
    if exceeded_limit:
        message = (
            "ArcGIS returned more flood-zone features than the current viewport limit. "
            "Coverage is incomplete; zoom in to see additional zones."
        )

    return FEMAOverlayResponse(
        status=status,
        source_url=str(config.arcgis_flood_zones_url),
        retrieved_at=_utc_now(),
        features=all_features,
        total_returned=len(all_features),
        exceeded_transfer_limit=exceeded_limit,
        message=message,
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
