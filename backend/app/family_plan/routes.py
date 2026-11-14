from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import get_current_user_id
from ..db import get_session
from .models import FamilyPlan, FamilyPlanPayload

router = APIRouter()


@router.get("/", response_model=FamilyPlanPayload)
def get_plan(user_id: str = Depends(get_current_user_id), session: Session = Depends(get_session)):
    return session.get(FamilyPlan, user_id) or FamilyPlanPayload()


@router.put("/", response_model=FamilyPlanPayload)
def save_plan(payload: FamilyPlanPayload, user_id: str = Depends(get_current_user_id), session: Session = Depends(get_session)):
    plan = session.get(FamilyPlan, user_id)
    if plan is None:
        plan = FamilyPlan(user_id=user_id, **payload.model_dump())
    else:
        for field, value in payload.model_dump().items():
            setattr(plan, field, value)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan
