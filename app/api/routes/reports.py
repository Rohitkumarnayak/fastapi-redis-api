import csv, io
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user
from app.database.connection import get_db
from app.models import Event, User

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/summary")
def report_summary(start_date: datetime, end_date: datetime, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if start_date > end_date: raise HTTPException(422, "start_date must be before end_date")
    filters = (Event.created_at >= start_date, Event.created_at <= end_date)
    total = db.scalar(select(func.count(Event.id)).where(*filters)) or 0
    severity = db.execute(select(Event.severity, func.count(Event.id)).where(*filters).group_by(Event.severity)).all()
    status = db.execute(select(Event.status, func.count(Event.id)).where(*filters).group_by(Event.status)).all()
    types = db.execute(select(Event.event_type, func.count(Event.id)).where(*filters).group_by(Event.event_type).order_by(desc(func.count(Event.id)))).all()
    cameras = db.execute(select(Event.camera_id, func.count(Event.id)).where(*filters).group_by(Event.camera_id).order_by(desc(func.count(Event.id)))).all()
    return {"start_date": start_date, "end_date": end_date, "total_events": total,
            "by_severity": [{"name": k, "count": v} for k,v in severity],
            "by_status": [{"name": k, "count": v} for k,v in status],
            "by_event_type": [{"name": k, "count": v} for k,v in types],
            "by_camera": [{"name": k, "count": v} for k,v in cameras]}

@router.get("/events.csv")
def events_csv(start_date: datetime | None = None, end_date: datetime | None = None,
               severity: str | None = None, status: str | None = None, camera_id: str | None = None,
               db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if start_date and end_date and start_date > end_date: raise HTTPException(422, "start_date must be before end_date")
    query = select(Event)
    if start_date: query = query.where(Event.created_at >= start_date)
    if end_date: query = query.where(Event.created_at <= end_date)
    if severity: query = query.where(Event.severity == severity)
    if status: query = query.where(Event.status == status)
    if camera_id: query = query.where(Event.camera_id == camera_id)
    rows = db.scalars(query.order_by(desc(Event.created_at))).all()
    output = io.StringIO(); writer = csv.writer(output)
    fields = ["id", "event_type", "camera_id", "message", "severity", "status", "assigned_to", "assigned_by", "assigned_at", "acknowledged_by", "acknowledged_at", "resolved_by", "resolved_at", "resolution_notes", "latitude", "longitude", "created_at"]
    writer.writerow(fields)
    for row in rows: writer.writerow([getattr(row, f) for f in fields])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=events_report.csv"})
