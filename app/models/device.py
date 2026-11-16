from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, JSON, String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base


def utcnow():
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), default="camera", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stream_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="inactive", index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_online_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_offline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_recipients: Mapped[list | None] = mapped_column(JSON, nullable=True)
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class VehicleJourneyReport(Base):
    """Immutable summary of one online-to-offline vehicle journey."""
    __tablename__ = "vehicle_journey_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(150), nullable=False)
    online_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    offline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_detections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acknowledged_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recipients: Mapped[list | None] = mapped_column(JSON, nullable=True)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
