from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response, status
from sqlmodel import Session, select

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



def _clean(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field} must not be blank")
    return cleaned


@router.post("/", response_model=SavedLocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: SavedLocationCreate,
    session: Session = Depends(get_session),
    _: None = Depends(_require_api_key),
) -> SavedLocation:
    location = SavedLocation(
        owner_type=payload.owner_type,
        label=_clean(payload.label, "label"),
        address=_clean(payload.address, "address"),
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
