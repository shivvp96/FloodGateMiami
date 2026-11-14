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


def _ring_signed_area(ring: list[list[float]]) -> float:
    """Return the signed area of a closed ring using the shoelace formula.

    Positive → counter-clockwise. Negative → clockwise.
    """
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _point_in_ring(px: float, py: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test for a single ring."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _ring_contains(ring: list[list[float]], point: list[float]) -> bool:
    """Return whether the first vertex of `point_ring` lies inside `ring`."""
    return _point_in_ring(point[0], point[1], ring)


def _classify_rings(rings: list[list[list[float]]]) -> tuple[list[list[list[float]]], list[list[list[float]]]]:
    """Classify rings into exteriors and holes using winding order + containment.

    If the ring set has mixed winding signs, CCW (positive area) = exterior and
    CW (negative area) = hole. If all rings share the same sign (some ArcGIS
    services emit everything CCW), fall back to geometric containment: sort by
    descending absolute area; the largest ring is an exterior; any ring fully
    contained by a smaller ring is a hole of the smallest containing exterior.
    """
    if not rings:
        return [], []

    areas = [(r, _ring_signed_area(r)) for r in rings]
    pos = [r for r, a in areas if a >= 0]
    neg = [r for r, a in areas if a < 0]

    if pos and neg:
        # Mixed signs — trust winding order.
        return pos, neg

    # All same sign — use containment.
    # Sort by descending absolute area; largest = exterior candidates.
    sorted_rings = sorted(rings, key=lambda r: abs(_ring_signed_area(r)), reverse=True)

    exteriors: list[list[list[float]]] = []
    holes: list[list[list[float]]] = []

    for ring in sorted_rings:
        # A ring is a hole if it is contained by any already-classified exterior.
        parent = None
        for ext in exteriors:
            if _ring_contains(ext, ring[0]):
                parent = ext
                break
        if parent is not None:
            holes.append(ring)
        else:
            exteriors.append(ring)

    return exteriors, holes


def _esri_geometry_to_geojson(esri_geom: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Convert an ArcGIS JSON geometry (rings/paths) to a GeoJSON geometry.

    Classifies rings into exteriors and holes using winding order when available,
    falling back to geometric containment when all rings share the same winding
    direction (some ArcGIS services emit everything CCW). Multiple exterior rings
    produce a MultiPolygon; each hole is assigned to its containing exterior.
    All rings are reversed so output follows GeoJSON CCW-exterior / CW-hole
    convention, which Leaflet renders correctly.
    """
    if not esri_geom:
        return {"type": "Polygon", "coordinates": []}

    rings = esri_geom.get("rings")
    if rings is not None:
        exteriors, holes = _classify_rings(rings)

        if not exteriors:
            return {"type": "Polygon", "coordinates": []}

        # Reverse all rings to swap winding direction for GeoJSON output.
        rev_ext = [list(reversed(r)) for r in exteriors]
        rev_holes = [list(reversed(r)) for r in holes]

        if len(rev_ext) == 1:
            assigned_holes = [h for h in rev_holes if _point_in_ring(h[0][0], h[0][1], rev_ext[0])]
            return {"type": "Polygon", "coordinates": [rev_ext[0]] + assigned_holes}

        # Multiple exteriors → MultiPolygon. Assign each hole to the exterior
        # that contains its first vertex.
        polygons: list[list[list[list[float]]]] = []
        for ext in rev_ext:
            poly_rings = [ext]
            for h in rev_holes:
                if _point_in_ring(h[0][0], h[0][1], ext):
                    poly_rings.append(h)
            polygons.append(poly_rings)

        return {"type": "MultiPolygon", "coordinates": polygons}

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
