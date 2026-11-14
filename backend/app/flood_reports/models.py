from datetime import UTC, datetime
from sqlmodel import Field, SQLModel


class FloodReportCreate(SQLModel):
    address: str = Field(min_length=5, max_length=240)
    description: str = Field(min_length=10, max_length=1500)
    observed_at: datetime


class FloodReport(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    address: str
    description: str
    observed_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latitude: float
    longitude: float
    verification_status: str = Field(default="unverified")


class FloodReportRead(SQLModel):
    id: int
    address: str
    description: str
    observed_at: datetime
    created_at: datetime
    latitude: float
    longitude: float
    verification_status: str
