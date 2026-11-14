from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TidePrediction(SQLModel):
    timestamp: str
    value: float
    type: str  # H = high, L = low
    units: str


class WaterLevelObservation(SQLModel):
    timestamp: str
    value: float
    units: str
    datum: str


class TideComparison(SQLModel):
    observed_value: float
    predicted_value: float
    difference: float
    units: str
    timestamp: str


class KingTideWatch(SQLModel):
    active: bool
    threshold_value: float
    threshold_units: str
    threshold_source: str
    message: str
    next_high_tides_above_threshold: list[TidePrediction] = Field(default_factory=list)


class TidesResponse(SQLModel):
    status: str  # ok, predictions_only, observations_only, unavailable
    station_id: str
    station_name: Optional[str] = None
    current_water_level: Optional[WaterLevelObservation] = None
    next_high_tide: Optional[TidePrediction] = None
    upcoming_high_tides: list[TidePrediction] = Field(default_factory=list)
    comparison: Optional[TideComparison] = None
    king_tide_watch: KingTideWatch
    source_urls: dict[str, str] = Field(default_factory=dict)
    retrieved_at: datetime
    message: Optional[str] = None
