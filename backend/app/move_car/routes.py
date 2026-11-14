from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from .models import MoveMyCarRequest, MoveMyCarResponse
from .service import assess_and_recommend

router = APIRouter()


@router.post("/recommend", response_model=MoveMyCarResponse)
async def move_my_car_endpoint(
    request: MoveMyCarRequest,
    session: Session = Depends(get_session),
) -> MoveMyCarResponse:
    """Evidence-based vehicle-moving advisory. Never guarantees a safe route or spot."""
    if request.location_id <= 0:
        raise HTTPException(status_code=422, detail="location_id must be a positive integer")
    return await assess_and_recommend(request, session)
