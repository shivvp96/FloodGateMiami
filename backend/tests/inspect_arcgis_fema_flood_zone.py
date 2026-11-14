import asyncio
import json

import httpx

from app.address_lookup.service import LookupConfig, arcgis_fema_flood_zones


URL = "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query"
LATITUDE = 25.775080963346
LONGITUDE = -80.196332054722


async def main() -> None:
    cfg = LookupConfig(
        census_base_url="https://geocoding.geo.census.gov",
        arcgis_flood_zones_url=URL,
        request_timeout_s=20.0,
        cache_ttl_s=300,
    )

    params = {
        "where": "1=1",
        "geometry": json.dumps({
            "x": LONGITUDE,
            "y": LATITUDE,
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "outSR": "4326",
        "resultRecordCount": 1,
        "f": "json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(URL, params=params)
        print(f"HTTP status: {response.status_code}")
        response.raise_for_status()
        payload = response.json()

    print(f"response keys: {sorted(payload.keys())}")
    features = payload.get("features") or []
    print(f"features count: {len(features)}")
    if not features:
        print("RESULT: no matching polygon")
        return

    print(f"first feature keys: {sorted(features[0].keys())}")
    print(f"attributes: {features[0].get('attributes')}")
    print(f"FZONE: {(features[0].get('attributes') or {}).get('FZONE')}")

    zone, attrs, source_url = await arcgis_fema_flood_zones(
        LATITUDE,
        LONGITUDE,
        config=cfg,
    )
    print(f"service designation: {zone.designation}")
    print(f"service zone_type: {zone.zone_type}")
    print(f"service attributes: {attrs}")
    print(f"service source_url: {source_url}")


if __name__ == "__main__":
    asyncio.run(main())
