import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from ..address_lookup.service import LookupConfig, census_geocode
from ..auth import get_current_user_id
from ..db import get_session
from .models import FloodReport, FloodReportCreate, FloodReportRead

router = APIRouter()


@router.get("/", response_model=list[FloodReportRead])
def list_reports(user_id: str = Depends(get_current_user_id), session: Session = Depends(get_session)):
    # Personal incident journal only. Unverified reports are never published as live flood alerts.
    return list(session.exec(select(FloodReport).where(FloodReport.user_id == user_id).order_by(FloodReport.observed_at.desc())))


@router.post("/", response_model=FloodReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(payload: FloodReportCreate, user_id: str = Depends(get_current_user_id), session: Session = Depends(get_session)):
    address = payload.address.strip()
    description = payload.description.strip()
    if len(address) < 5 or len(description) < 10:
        raise HTTPException(status_code=422, detail="Provide a valid address and at least 10 characters of detail")
    config = LookupConfig(
        census_base_url=os.getenv("CENSUS_GEOCODER_BASE_URL", "https://geocoding.geo.census.gov"),
        arcgis_flood_zones_url=os.getenv("ARCGIS_FEMA_FLOOD_ZONES_URL", "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query"),
        request_timeout_s=8,
        cache_ttl_s=300,
    )
    try:
        matched, coords, _score = await census_geocode(address, config=config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Address could not be verified") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Address verification unavailable") from exc
    report = FloodReport(
        user_id=user_id, address=matched, description=description,
        observed_at=payload.observed_at, latitude=coords.latitude, longitude=coords.longitude,
        verification_status="unverified",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, user_id: str = Depends(get_current_user_id), session: Session = Depends(get_session)):
    report = session.get(FloodReport, report_id)
    if report is None or report.user_id != user_id:
        raise HTTPException(status_code=404, detail="report not found")
    session.delete(report)
    session.commit()
    return Response(status_code=204)
