from datetime import UTC, datetime
from typing import Optional

from ..address_lookup.service import LookupConfig, arcgis_fema_flood_zones
from ..saved_locations.models import SavedLocation
from ..auth import LOCAL_USER_ID
from ..tides.service import get_tides
from ..weather.service import get_weather_for_coordinates
from .models import MoveMyCarCandidate, MoveMyCarRequest, MoveMyCarResponse, RiskFactor


DISCLAIMER = (
    "This advisory uses mapped FEMA flood zones, NWS alerts, and NOAA tide predictions. "
    "It is planning information only. It cannot confirm any specific street, route, or parking "
    "spot is safe or flood-free. Always follow official emergency guidance."
)

# Zones with statutory 1%-annual-chance flood hazard (Special Flood Hazard Area).
_HIGH_RISK_ZONES = {"A", "AE", "AH", "AO", "VE", "V"}

# Candidate zones that are never surfaced as recommendations — either not
# land-based flood zones, or lacking a definitive classification.
_EXCLUDED_CANDIDATE_ZONES = {"OPEN WATER", "", None, "UNMATCHED", "UNCLASSIFIED"}
_LOWER_MAPPED_HAZARD_ZONES = {"X"}  # Zone D is undetermined, not evidence of low hazard


def _config_from_env() -> LookupConfig:
    import os

    return LookupConfig(
        census_base_url=os.environ.get("CENSUS_GEOCODER_BASE_URL", "https://geocoding.geo.census.gov"),
        arcgis_flood_zones_url=os.environ.get(
            "ARCGIS_FEMA_FLOOD_ZONES_URL",
            "https://gisweb.miamidade.gov/arcgis/rest/services/EnerGov/MD_LandMgtViewer/MapServer/63/query",
        ),
        request_timeout_s=float(os.environ.get("LOOKUP_REQUEST_TIMEOUT_S", "8")),
        cache_ttl_s=int(os.environ.get("LOOKUP_CACHE_TTL_S", "300")),
    )


async def assess_and_recommend(request: MoveMyCarRequest, session, *, user_id: str) -> MoveMyCarResponse:
    """Assess flood risk for a stored vehicle location using only live official data."""
    import asyncio

    now = datetime.now(UTC)

    vehicle = session.get(SavedLocation, request.location_id)
    if vehicle is None or vehicle.owner_type != "vehicle" or not (vehicle.user_id == user_id or (user_id == LOCAL_USER_ID and vehicle.user_id is None)):
        return MoveMyCarResponse(
            status="no_location",
            location_id=request.location_id,
            recommendation="no_recommendation",
            disclaimer=DISCLAIMER,
            retrieved_at=now,
            message="Saved vehicle location not found.",
        )

    if vehicle.latitude is None or vehicle.longitude is None:
        return MoveMyCarResponse(
            status="insufficient_data",
            location_id=request.location_id,
            vehicle_label=vehicle.label,
            recommendation="no_recommendation",
            disclaimer=DISCLAIMER,
            retrieved_at=now,
            message="This location has no verified coordinates. Re-save it with a geocodable address.",
        )

    lat, lon = vehicle.latitude, vehicle.longitude
    config = _config_from_env()

    risk_factors: list[RiskFactor] = []
    grounding_ok = True

    # Gather live FEMA zone, weather, and tides concurrently.
    async def _fema():
        zone, _attrs, source = await arcgis_fema_flood_zones(lat, lon, config=config)
        return zone.designation, source

    async def _weather():
        return await get_weather_for_coordinates(lat, lon)

    async def _tides():
        return await get_tides()

    fema_res, weather_res, tides_res = await asyncio.gather(_fema(), _weather(), _tides(), return_exceptions=True)

    fema_zone: Optional[str] = None
    if isinstance(fema_res, Exception):
        grounding_ok = False
        risk_factors.append(RiskFactor(
            kind="fema_zone",
            detail="FEMA zone lookup is currently unavailable.",
            source="Miami-Dade ArcGIS FEMA layer",
        ))
    else:
        fema_zone, fema_source = fema_res
        if fema_zone and fema_zone.upper() in _HIGH_RISK_ZONES:
            risk_factors.append(RiskFactor(
                kind="fema_zone",
                detail=f"Parked in FEMA zone {fema_zone} (special flood hazard area, 1% annual chance).",
                source=fema_source,
            ))

    if isinstance(weather_res, Exception):
        grounding_ok = False
    else:
        weather = weather_res
        flood_alerts = [a for a in weather.active_alerts if a.is_flood_related]
        for alert in flood_alerts:
            risk_factors.append(RiskFactor(
                kind="flood_alert",
                detail=f"Active NWS alert: {alert.event} — {alert.headline or alert.area_desc or ''}".strip(),
                source="https://api.weather.gov",
            ))

    if isinstance(tides_res, Exception):
        grounding_ok = False
    else:
        tides = tides_res
        if tides.next_high_tide is not None:
            threshold = tides.king_tide_watch.threshold_value
            if tides.next_high_tide.value >= threshold:
                risk_factors.append(RiskFactor(
                    kind="high_tide",
                    detail=(
                        f"Next high tide {tides.next_high_tide.value} ft MLLW at {tides.next_high_tide.timestamp} "
                        f"meets or exceeds the local planning reference of {threshold} ft."
                    ),
                    source="https://api.tidesandcurrents.noaa.gov",
                ))
        if tides.king_tide_watch.active:
            risk_factors.append(RiskFactor(
                kind="king_tide",
                detail=tides.king_tide_watch.message,
                source="https://api.tidesandcurrents.noaa.gov",
            ))

    if not grounding_ok:
        return MoveMyCarResponse(
            status="insufficient_data",
            location_id=request.location_id,
            vehicle_label=vehicle.label,
            recommendation="no_recommendation",
            disclaimer=DISCLAIMER,
            retrieved_at=now,
            message="Live risk data could not be fully verified; no recommendation is made.",
        )

    if not risk_factors:
        return MoveMyCarResponse(
            status="ok",
            location_id=request.location_id,
            vehicle_label=vehicle.label,
            recommendation="stay_parked",
            risk_factors=[],
            candidates=[],
            disclaimer=DISCLAIMER,
            retrieved_at=now,
            message="No active flood-risk indicators for this location right now.",
        )

    # Flood risk present: surface alternative candidates only from OTHER saved
    # locations that have verified coordinates. Check each candidate's FEMA zone
    # so recommendations are evidence-based.
    from sqlmodel import select as _select

    others = [
        loc for loc in session.exec(
            _select(SavedLocation).where(SavedLocation.latitude != None, SavedLocation.longitude != None)  # noqa: E711
        ).all()
        if loc.id != vehicle.id and (loc.user_id == user_id or (user_id == LOCAL_USER_ID and loc.user_id is None))
    ]

    candidates: list[MoveMyCarCandidate] = []
    for cand in others:
        try:
            zone, _attrs, _src = await arcgis_fema_flood_zones(cand.latitude, cand.longitude, config=config)
            designation = zone.designation
        except Exception:
            continue  # unverifiable candidate — never surface it

        # Exclude OPEN WATER, unmatched, unclassified, or missing designations —
        # these are not valid land-based flood zones to recommend parking at.
        normalized = (designation or "").strip().upper()
        if normalized in _EXCLUDED_CANDIDATE_ZONES:
            continue

        cand_zone = normalized
        vehicle_zone = fema_zone.upper() if fema_zone else None
        lower_risk = cand_zone in _LOWER_MAPPED_HAZARD_ZONES and vehicle_zone in _HIGH_RISK_ZONES
        if not lower_risk:
            continue  # Only show a strictly lower mapped hazard alternative.
        note = (
            f"FEMA zone {designation or 'not mapped'} — lower mapped flood hazard than your current spot."
            if lower_risk
            else f"FEMA zone {designation or 'not mapped'}."
        )
        candidates.append(MoveMyCarCandidate(
            location_id=cand.id,
            label=cand.label,
            address=cand.address,
            latitude=cand.latitude,
            longitude=cand.longitude,
            fema_zone=designation,
            note=note,
        ))

    return MoveMyCarResponse(
        status="ok",
        location_id=request.location_id,
        vehicle_label=vehicle.label,
        recommendation="consider_moving",
        risk_factors=risk_factors,
        candidates=candidates,
        disclaimer=DISCLAIMER,
        retrieved_at=now,
        message=None if candidates else
            "Flood-risk indicators are present, but no alternative saved locations with verified coordinates are available to compare.",
    )
