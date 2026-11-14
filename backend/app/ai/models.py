from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AskFloodGuardRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class AskFloodGuardResponse(BaseModel):
    status: str  # ok | unavailable
    answer: str
    question: str
    grounding: dict[str, Any]
    model: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: Optional[str] = None
