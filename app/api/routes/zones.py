from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user, require_admin
from app.database.connection import get_db
from app.models import Zone, ROI, Event, User

router = APIRouter(tags=["zones and ROIs"])

class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    site: str | None = Field(default=None, max_length=150)
    boundary: dict | list | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    site: str | None = None
    boundary: dict | list | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

class ZoneOut(BaseModel):
    id: int; name: str; description: str | None; site: str | None; boundary: dict | list | None
    latitude: float | None; longitude: float | None; created_by: int | None; created_at: object; updated_at: object
    model_config = ConfigDict(from_attributes=True)

class ROICreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    zone_id: int = Field(ge=1)
    device_id: str | None = Field(default=None, max_length=100)
    points: list | dict
    coordinate_space: str = Field(default="normalized", pattern=r"^(normalized|pixel|geographic)$")
    description: str | None = None
    enabled: bool = True

class ROIUpdate(BaseModel):
    name: str | None = None
    zone_id: int | None = Field(default=None, ge=1)
    device_id: str | None = None
    points: list | dict | None = None
    coordinate_space: str | None = Field(default=None, pattern=r"^(normalized|pixel|geographic)$")
    description: str | None = None
    enabled: bool | None = None

class ROIOut(BaseModel):
    id: int; name: str; zone_id: int; device_id: str | None; points: list | dict
    coordinate_space: str; description: str | None; enabled: bool; created_by: int | None; created_at: object; updated_at: object
    model_config = ConfigDict(from_attributes=True)

@router.post("/zones", response_model=ZoneOut, status_code=201)
def create_zone(payload: ZoneCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if (payload.latitude is None) != (payload.longitude is None): raise HTTPException(422, "latitude and longitude must be provided together")
    zone = Zone(**payload.model_dump(), created_by=user.id); db.add(zone)
    try: db.commit(); db.refresh(zone)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Zone name already exists")
    return zone

@router.get("/zones")
def list_zones(q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = select(Zone)
    if q: query = query.where(Zone.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Zone.name).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [ZoneOut.model_validate(x) for x in rows], "page": page, "page_size": page_size, "total": total}

@router.get("/zones/{zone_id}", response_model=ZoneOut)
def get_zone(zone_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    zone = db.get(Zone, zone_id)
    if not zone: raise HTTPException(404, "Zone not found")
    return zone

@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: int, payload: ZoneUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    zone = db.get(Zone, zone_id)
    if not zone: raise HTTPException(404, "Zone not found")
    for k,v in payload.model_dump(exclude_unset=True).items(): setattr(zone,k,v)
    if (zone.latitude is None) != (zone.longitude is None): raise HTTPException(422, "latitude and longitude must be provided together")
    try: db.commit(); db.refresh(zone)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Zone name already exists")
    return zone

@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    zone = db.get(Zone, zone_id)
    if not zone: raise HTTPException(404, "Zone not found")
    db.delete(zone); db.commit()
    return {"success": True, "message": "Zone deleted"}

@router.post("/rois", response_model=ROIOut, status_code=201)
def create_roi(payload: ROICreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if not db.get(Zone, payload.zone_id): raise HTTPException(404, "Zone not found")
    roi = ROI(**payload.model_dump(), created_by=user.id); db.add(roi); db.commit(); db.refresh(roi)
    return roi

@router.get("/rois")
def list_rois(zone_id: int | None = None, device_id: str | None = None, enabled: bool | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = select(ROI)
    if zone_id is not None: query = query.where(ROI.zone_id == zone_id)
    if device_id: query = query.where(ROI.device_id == device_id)
    if enabled is not None: query = query.where(ROI.enabled == enabled)
    return {"items": [ROIOut.model_validate(x) for x in db.scalars(query.order_by(ROI.id.desc())).all()]}

@router.patch("/rois/{roi_id}", response_model=ROIOut)
def update_roi(roi_id: int, payload: ROIUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    roi = db.get(ROI, roi_id)
    if not roi: raise HTTPException(404, "ROI not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("zone_id") and not db.get(Zone, data["zone_id"]): raise HTTPException(404, "Zone not found")
    for k,v in data.items(): setattr(roi,k,v)
    db.commit(); db.refresh(roi)
    return roi

@router.delete("/rois/{roi_id}")
def delete_roi(roi_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    roi = db.get(ROI, roi_id)
    if not roi: raise HTTPException(404, "ROI not found")
    db.delete(roi); db.commit()
    return {"success": True, "message": "ROI deleted"}

@router.get("/analytics/zones/summary")
def zone_summary(start_date: str | None = None, end_date: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    # Zone membership is inferred from camera/device IDs assigned to ROIs.
    rows = db.execute(select(Zone.id, Zone.name, func.count(Event.id)).select_from(Zone).join(ROI, ROI.zone_id == Zone.id).join(Event, Event.camera_id == ROI.device_id, isouter=True).group_by(Zone.id, Zone.name).order_by(Zone.name)).all()
    return {"items": [{"zone_id": zid, "zone_name": name, "event_count": count} for zid,name,count in rows]}
