from datetime import datetime
from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=4000)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")


class EventResponse(BaseModel):
    id: int
    event_type: str
    camera_id: str
    message: str
    severity: str
    status: str
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
