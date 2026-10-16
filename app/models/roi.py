from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base


def utcnow():
    return datetime.now(timezone.utc)


class ROI(Base):
    __tablename__ = "rois"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    # Pixel or normalized polygon points, e.g. [[x,y], ...]; coordinate convention is supplied by client.
    points: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    coordinate_space: Mapped[str] = mapped_column(String(30), default="normalized", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
