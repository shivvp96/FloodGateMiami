from fastapi import APIRouter, HTTPException, Query

from .models import NWSWeatherResponse
from .service import get_weather_for_coordinates

router = APIRouter()


@router.get("/lookup", response_model=NWSWeatherResponse)
async def weather_lookup_endpoint(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> NWSWeatherResponse:
    """Public read-only NWS weather and alert lookup for given coordinates."""
    if lat == 0 and lon == 0:
        raise HTTPException(status_code=422, detail="coordinates cannot both be zero")

    return await get_weather_for_coordinates(lat, lon)
