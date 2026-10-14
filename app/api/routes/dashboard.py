from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user
from app.database.connection import get_db
from app.models import Event, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_cameras = db.scalar(select(func.count(func.distinct(Event.camera_id)))) or 0
    total_today = db.scalar(select(func.count(Event.id)).where(Event.created_at >= start)) or 0
    critical_today = db.scalar(select(func.count(Event.id)).where(Event.created_at >= start, Event.severity == "critical")) or 0
    pending = db.scalar(select(func.count(Event.id)).where(Event.status == "pending")) or 0
    acknowledged = db.scalar(select(func.count(Event.id)).where(Event.status == "acknowledged")) or 0
    return {"success": True, "data": {"total_cameras_with_events": total_cameras, "total_events_today": total_today, "critical_events_today": critical_today, "pending_events": pending, "acknowledged_events": acknowledged, "generated_at": now.isoformat()}}
