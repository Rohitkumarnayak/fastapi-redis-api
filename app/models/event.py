
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Float,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    __table_args__ = (
        Index("ix_events_created_severity", "created_at", "severity"),
    )

    # Event identification
    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )

    camera_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )

    # Event zone
    zone: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    # Severity and workflow status
    severity: Mapped[str] = mapped_column(
        String(20),
        default="info",
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
        nullable=False,
    )

    # Assignment details
    # Can contain an external person's name, phone number,
    # or other contact details.
    assigned_to: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    assigned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Acknowledgement details
    acknowledged_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Resolution details
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Event location
    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Event image
    # Stores the raw Base64 string, without a data URL prefix.
    image_base64: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Examples: image/jpeg, image/png, image/webp
    image_mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Event creation timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
        nullable=False,
    )
