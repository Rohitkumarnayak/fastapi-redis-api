from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import or_, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user, require_admin
from app.database.connection import get_db
from app.models import Device, User

router = APIRouter(prefix="/devices", tags=["device management"])

class DeviceCreate(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=150)
    device_type: str = Field(default="camera", max_length=50)
    ip_address: str | None = Field(default=None, max_length=100)
    stream_url: str | None = None
    location: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    status: str = Field(default="inactive", pattern=r"^(active|inactive|offline|maintenance)$")
    enabled: bool = True
    metadata_json: dict | None = Field(default=None, alias="metadata")
    model_config = {"populate_by_name": True}

class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    device_type: str | None = Field(default=None, max_length=50)
    ip_address: str | None = None
    stream_url: str | None = None
    location: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|offline|maintenance)$")
    enabled: bool | None = None
    metadata_json: dict | None = Field(default=None, alias="metadata")
    model_config = {"populate_by_name": True}

class DeviceOut(BaseModel):
    id: int; device_id: str; name: str; device_type: str; ip_address: str | None
    stream_url: str | None; location: str | None; latitude: float | None; longitude: float | None
    status: str; enabled: bool; metadata_json: dict | None = Field(serialization_alias="metadata")
    created_at: datetime; last_seen_at: datetime | None; updated_at: datetime
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

@router.post("", response_model=DeviceOut, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    data = payload.model_dump(by_alias=False)
    if (data.get("latitude") is None) != (data.get("longitude") is None): raise HTTPException(422, "latitude and longitude must be provided together")
    device = Device(**data)
    db.add(device)
    try: db.commit(); db.refresh(device)
    except IntegrityError: db.rollback(); raise HTTPException(409, "Device ID already registered")
    return device

@router.get("")
def list_devices(q: str | None = None, status: str | None = None, enabled: bool | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = select(Device)
    if q:
        term = f"%{q.strip()}%"; query = query.where(or_(Device.name.ilike(term), Device.device_id.ilike(term), Device.location.ilike(term)))
    if status: query = query.where(Device.status == status)
    if enabled is not None: query = query.where(Device.enabled == enabled)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Device.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [DeviceOut.model_validate(x) for x in items], "page": page, "page_size": page_size, "total": total, "pages": (total+page_size-1)//page_size}

@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device: raise HTTPException(404, "Device not found")
    return device

@router.post("/{device_id}/heartbeat", response_model=DeviceOut)
def device_heartbeat(device_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device: raise HTTPException(404, "Device not found")
    device.last_seen_at = datetime.now(timezone.utc)
    device.status = "active"
    db.commit(); db.refresh(device)
    return device

@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: str, payload: DeviceUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device: raise HTTPException(404, "Device not found")
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    for k, v in data.items(): setattr(device, k, v)
    if (device.latitude is None) != (device.longitude is None): raise HTTPException(422, "latitude and longitude must be provided together")
    db.commit(); db.refresh(device)
    return device

@router.delete("/{device_id}")
def disable_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if not device: raise HTTPException(404, "Device not found")
    device.enabled = False; device.status = "inactive"; db.commit()
    return {"success": True, "message": "Device disabled", "device_id": device_id}
