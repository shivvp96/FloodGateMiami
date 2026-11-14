from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class HourlyForecastPeriod(SQLModel):
    number: int
    start_time: str
    end_time: str
    is_daytime: bool
    temperature: Optional[float] = None
    temperature_unit: Optional[str] = None
    short_forecast: Optional[str] = None
    detailed_forecast: Optional[str] = None
    wind_speed: Optional[str] = None
    wind_direction: Optional[str] = None
    precipitation_chance: Optional[int] = None


class WeatherAlert(SQLModel):
    id: str
    event: str
    headline: str
    severity: Optional[str] = None
    urgency: Optional[str] = None
    certainty: Optional[str] = None
    effective: Optional[str] = None
    expires: Optional[str] = None
    description: str
    instruction: Optional[str] = None
    sender_name: Optional[str] = None
    area_desc: Optional[str] = None
    is_flood_related: bool
    source_url: str


class NWSWeatherResponse(SQLModel):
    status: str  # ok, no_alerts, unavailable, stale
    coordinates: dict[str, float]
    forecast_url: Optional[str] = None
    hourly_periods: list[HourlyForecastPeriod] = Field(default_factory=list)
    active_alerts: list[WeatherAlert] = Field(default_factory=list)
    flood_alert_count: int
    source: str
    retrieved_at: datetime
    message: Optional[str] = None
