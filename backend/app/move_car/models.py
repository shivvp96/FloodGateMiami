from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


class MoveMyCarRequest(BaseModel):
    location_id: int


class RiskFactor(BaseModel):
    kind: str  # fema_zone | flood_alert | high_tide | king_tide
    detail: str
    source: str


class MoveMyCarCandidate(BaseModel):
    location_id: int
    label: str
    address: str
    latitude: float
    longitude: float
    fema_zone: Optional[str] = None
    note: str


class MoveMyCarResponse(BaseModel):
    status: str  # ok | no_location | insufficient_data
    location_id: int
    vehicle_label: Optional[str] = None
    recommendation: str  # consider_moving | stay_parked | no_recommendation
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    candidates: list[MoveMyCarCandidate] = Field(default_factory=list)
    disclaimer: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: Optional[str] = None
