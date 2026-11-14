from fastapi import APIRouter, HTTPException

from .models import AskFloodGuardRequest
from .service import ask_floodguard

router = APIRouter()


@router.post("/ask", status_code=200)
async def ask_floodguard_endpoint(request: AskFloodGuardRequest) -> dict:
    """Server-side grounded AI assistant. Never simulated."""
    if request.latitude is not None and request.longitude is None:
        raise HTTPException(status_code=422, detail="latitude provided without longitude")
    if request.longitude is not None and request.latitude is None:
        raise HTTPException(status_code=422, detail="longitude provided without latitude")
    if request.latitude is not None and request.longitude is not None:
        if request.latitude == 0 and request.longitude == 0:
            raise HTTPException(status_code=422, detail="coordinates cannot both be zero")

    response = await ask_floodguard(request)
    return response.model_dump(mode="json")
