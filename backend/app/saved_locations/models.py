from datetime import UTC, datetime
from typing import Literal

from sqlmodel import Field, SQLModel

OwnerType = Literal["property", "vehicle"]


class SavedLocationCreate(SQLModel):
    owner_type: OwnerType
    label: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=1, max_length=240)


class SavedLocation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_type: str = Field(index=True)
    user_id: str | None = Field(default=None, index=True)
    label: str
    address: str
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SavedLocationRead(SQLModel):
    id: int
    owner_type: OwnerType
    label: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime
