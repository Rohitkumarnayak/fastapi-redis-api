from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user
from app.database.connection import get_db
from app.models import Event, User, Device, Zone, ROI

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("")
def dashboard(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    start = start_date or now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end_date or now
    base = select(Event).where(Event.created_at >= start, Event.created_at <= end)
    total_events = db.scalar(select(func.count(Event.id)).where(Event.created_at >= start, Event.created_at <= end)) or 0
    total_devices = db.scalar(select(func.count(Device.id)).where(Device.enabled.is_(True))) or 0
    cameras_with_events = db.scalar(select(func.count(func.distinct(Event.camera_id))).where(Event.created_at >= start, Event.created_at <= end)) or 0
    by_severity = db.execute(select(Event.severity, func.count(Event.id)).where(Event.created_at >= start, Event.created_at <= end).group_by(Event.severity)).all()
    by_status = db.execute(select(Event.status, func.count(Event.id)).where(Event.created_at >= start, Event.created_at <= end).group_by(Event.status)).all()
    by_type = db.execute(select(Event.event_type, func.count(Event.id)).where(Event.created_at >= start, Event.created_at <= end).group_by(Event.event_type).order_by(desc(func.count(Event.id))).limit(10)).all()
    by_camera = db.execute(select(Event.camera_id, func.count(Event.id)).where(Event.created_at >= start, Event.created_at <= end).group_by(Event.camera_id).order_by(desc(func.count(Event.id))).limit(10)).all()
    pending = db.scalar(select(func.count(Event.id)).where(Event.status.in_(["pending", "assigned"]))) or 0
    critical = db.scalar(select(func.count(Event.id)).where(Event.severity == "critical", Event.created_at >= start, Event.created_at <= end)) or 0
    acknowledged = db.scalar(select(func.count(Event.id)).where(Event.status == "acknowledged", Event.created_at >= start, Event.created_at <= end)) or 0
    resolved = db.scalar(select(func.count(Event.id)).where(Event.status.in_(["resolved", "closed"]), Event.created_at >= start, Event.created_at <= end)) or 0
    return {"success": True, "filters": {"start_date": start, "end_date": end}, "data": {
        "total_events": total_events, "total_devices": total_devices, "cameras_with_events": cameras_with_events,
        "critical_events": critical, "pending_events": pending, "acknowledged_events": acknowledged, "resolved_events": resolved,
        "by_severity": [{"severity": k, "count": v} for k,v in by_severity],
        "by_status": [{"status": k, "count": v} for k,v in by_status],
        "top_event_types": [{"event_type": k, "count": v} for k,v in by_type],
        "top_cameras": [{"camera_id": k, "count": v} for k,v in by_camera],
        "generated_at": now,
    }}

@router.get("/timeline")
def timeline(days: int = Query(7, ge=1, le=365), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(select(func.date(Event.created_at), func.count(Event.id)).where(Event.created_at >= start).group_by(func.date(Event.created_at)).order_by(func.date(Event.created_at))).all()
    return {"days": days, "items": [{"date": str(day), "count": count} for day,count in rows]}

@router.get("/zones")
def zone_dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(Zone.id, Zone.name, Zone.site, Zone.latitude, Zone.longitude, func.count(Event.id)).select_from(Zone).join(ROI, ROI.zone_id == Zone.id).join(Event, Event.camera_id == ROI.device_id, isouter=True).group_by(Zone.id, Zone.name, Zone.site, Zone.latitude, Zone.longitude).order_by(Zone.name)).all()
    return {"items": [{"zone_id": z, "name": n, "site": s, "latitude": lat, "longitude": lon, "event_count": count} for z,n,s,lat,lon,count in rows]}
