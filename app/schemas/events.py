from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=4000)
    severity: str = Field(default="info", pattern=r"^(info|warning|critical)$")
    status: str = Field(default="pending", pattern=r"^(pending|assigned|acknowledged|resolved|closed)$")
    assigned_to: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinates_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class EventUpdate(BaseModel):
    event_type: str | None = Field(default=None, min_length=1, max_length=100)
    camera_id: str | None = Field(default=None, min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=4000)
    severity: str | None = Field(default=None, pattern=r"^(info|warning|critical)$")
    status: str | None = Field(default=None, pattern=r"^(pending|assigned|acknowledged|resolved|closed)$")
    assigned_to: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class EventResponse(BaseModel):
    id: int
    event_type: str
    camera_id: str
    message: str
    severity: str
    status: str
    assigned_to: str | None = None
    assigned_by: int | None = None
    assigned_at: datetime | None = None
    acknowledged_by: int | None = None
    acknowledged_at: datetime | None = None
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ResolveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)


class AssignRequest(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=2000)
