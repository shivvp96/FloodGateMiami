import os
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response, status
from sqlmodel import Session, select

from ..address_lookup.service import LookupConfig, census_geocode
from ..db import get_session
from .models import SavedLocation, SavedLocationCreate, SavedLocationRead

router = APIRouter()


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    import os

    # For production/hackathon MVP safety, saved-location CRUD must never be public.
    # Use APP_ENV as the primary switch; fall back to Vercel env detection for compatibility.
    app_env = os.environ.get("APP_ENV", "development").lower()
    is_production = app_env in {"production", "staging"}
    is_vercel = is_production or bool(os.environ.get("VERCEL") or os.environ.get("Vercel"))

    expected = os.environ.get("SAVED_LOCATIONS_API_KEY")

    # If credentials are not configured, deny in production.
    if is_vercel:
        if not expected:
            raise HTTPException(status_code=503, detail="saved-locations auth not configured")
        if not x_api_key or x_api_key != expected:
            raise HTTPException(status_code=401, detail="unauthorized")
        return

    # Local dev / non-Vercel: preserve existing behavior (allow without a configured key).
    if expected:
        if not x_api_key or x_api_key != expected:
            raise HTTPException(status_code=401, detail="unauthorized")


def _lookup_config() -> LookupConfig:
    return LookupConfig(
        census_base_url=os.environ.get("CENSUS_GEOCODER_BASE_URL", "https://geocoding.geo.census.gov"),
        arcgis_flood_zones_url=os.environ.get(
            "ARCGIS_FEMA_FLOOD_ZONES_URL",
            "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query",
        ),
        request_timeout_s=float(os.environ.get("LOOKUP_REQUEST_TIMEOUT_S", "8")),
        cache_ttl_s=int(os.environ.get("LOOKUP_CACHE_TTL_S", "300")),
    )


def _validate_coords(lat: float | None, lon: float | None) -> tuple[float | None, float | None]:
    if lat is None or lon is None:
        return None, None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=422, detail="latitude/longitude out of range")
    if lat == 0 and lon == 0:
        raise HTTPException(status_code=422, detail="coordinates cannot both be zero")
    return lat, lon


@router.post("/", response_model=SavedLocationRead, status_code=status.HTTP_201_CREATED)
async def create_location(
    payload: SavedLocationCreate,
    session: Session = Depends(get_session),
    _: None = Depends(_require_api_key),
) -> SavedLocation:
    label = payload.label.strip()
    address = payload.address.strip()
    if not label or not address:
        raise HTTPException(status_code=422, detail="label and address must not be blank")

    # Geocode via the official Census geocoder so stored coordinates are real.
    # If the geocoder cannot confidently match the address, reject the save rather
    # than persisting an unusable location.
    try:
        _matched, coords, score = await census_geocode(address, config=_lookup_config())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="address could not be geocoded; check the address and try again") from exc
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise HTTPException(status_code=503, detail="geocoding service unavailable; try again shortly") from exc

    lat, lon = _validate_coords(coords.latitude, coords.longitude)

    location = SavedLocation(
        owner_type=payload.owner_type,
        label=label,
        address=address,
        latitude=lat,
        longitude=lon,
        created_at=datetime.now(UTC),
    )
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


@router.get("/", response_model=list[SavedLocationRead])
def list_locations(
    owner_type: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _: None = Depends(_require_api_key),
) -> list[SavedLocation]:
    statement = select(SavedLocation).order_by(SavedLocation.created_at.desc())
    if owner_type:
        if owner_type not in {"property", "vehicle"}:
            raise HTTPException(status_code=422, detail="owner_type must be property or vehicle")
        statement = statement.where(SavedLocation.owner_type == owner_type)
    return list(session.exec(statement))


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(_require_api_key),
) -> Response:
    location = session.get(SavedLocation, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="saved location not found")
    session.delete(location)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
