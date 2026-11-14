import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from .models import AddressLookupResponse
from .service import LookupConfig, address_lookup

router = APIRouter()


def _config_from_env() -> LookupConfig:
    census_base_url = os.environ.get("CENSUS_GEOCODER_BASE_URL", "https://geocoding.geo.census.gov")

    # ArcGIS query endpoint for FEMA flood zones (Miami-Dade layer). The exact service/params must match your data.
    arcgis_flood_zones_url = os.environ.get(
        "ARCGIS_FEMA_FLOOD_ZONES_URL",
        "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query",
    )

    request_timeout_s = float(os.environ.get("LOOKUP_REQUEST_TIMEOUT_S", "8"))
    cache_ttl_s = int(os.environ.get("LOOKUP_CACHE_TTL_S", "300"))

    return LookupConfig(
        census_base_url=census_base_url,
        arcgis_flood_zones_url=arcgis_flood_zones_url,
        request_timeout_s=request_timeout_s,
        cache_ttl_s=cache_ttl_s,
    )


@router.get("/lookup", response_model=AddressLookupResponse)
async def address_lookup_endpoint(
    address: str = Query(..., min_length=3, max_length=240),
) -> AddressLookupResponse:
    # Minimal request validation
    addr = address.strip()
    if not addr:
        raise HTTPException(status_code=422, detail="address must not be blank")

    config = _config_from_env()

    try:
        response = await address_lookup(addr, config=config)
    except ValueError as e:
        if str(e) == "unmatched_address":
            raise HTTPException(status_code=404, detail="unmatched_address")
        raise HTTPException(status_code=422, detail=str(e))
    except (httpx.HTTPError, httpx.TimeoutException):
        raise HTTPException(status_code=503, detail="address lookup service unavailable")

    # Set request_id more usefully than a placeholder
    response.request_id = f"addr-lk-{uuid.uuid4().hex}"  # type: ignore[misc]
    return response
