from fastapi import APIRouter

from .models import TidesResponse
from .service import get_tides

router = APIRouter()


@router.get("/lookup", response_model=TidesResponse)
async def tides_lookup_endpoint() -> TidesResponse:
    """Public read-only NOAA CO-OPS tide lookup for the configured station."""
    return await get_tides()
