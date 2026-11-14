from datetime import datetime
from typing import Literal, Optional

from sqlmodel import Field, SQLModel


class GeoCoordinates(SQLModel):
    latitude: float
    longitude: float


class CensusGeocodeMatch(SQLModel):
    matched_address: str
    coordinates: GeoCoordinates
    geocoding_score: Optional[float] = None


class FEMAFloodZone(SQLModel):
    designation: Optional[str] = None
    zone_type: Optional[str] = None
    raw_attributes: dict[str, str] = Field(default_factory=dict)


class AddressLookupResponse(SQLModel):
    request_id: str
    matched_address: str
    coordinates: GeoCoordinates

    # FEMA results
    fema_flood_zone: FEMAFloodZone

    # Provenance
    source_url: str
    retrieved_at: datetime

    # Additional attributes for UI/explainability
    available_zone_attributes: dict[str, str] = Field(default_factory=dict)


class AddressLookupError(SQLModel):
    detail: str


class FEMAOverlayFeature(SQLModel):
    type: str = "Feature"
    geometry: dict
    properties: dict
    id: Optional[int] = None


class FEMAOverlayResponse(SQLModel):
    status: str  # ok, incomplete, unavailable
    source_url: str
    retrieved_at: datetime
    features: list[FEMAOverlayFeature] = Field(default_factory=list)
    total_returned: int
    exceeded_transfer_limit: bool
    message: Optional[str] = None


OwnerSource = Literal["census_geocoder", "arcgis_fema_flood_zones"]
