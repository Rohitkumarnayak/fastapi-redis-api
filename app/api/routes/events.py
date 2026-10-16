
import asyncio
import json
from datetime import datetime, timezone

import anyio
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from redis.exceptions import RedisError
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user, require_admin
from app.database.connection import get_db
from app.models import Event, ROI, User, Zone
from app.schemas.events import (
    AssignRequest,
    EventCreate,
    EventResponse,
    EventUpdate,
    ResolveRequest,
    inspect_image,
)

router = APIRouter(prefix="/events", tags=["events"])
EVENT_CHANNEL = "events:live"


def publish_event(request: Request, event: Event) -> None:
    """Publish a small event notification; PostgreSQL remains the source of truth."""
    try:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is None:
            return

        data = EventResponse.model_validate(event).model_dump(
            mode="json",
            exclude={"image_base64"},
        )

        # This route uses synchronous SQLAlchemy endpoints. Run an async
        # Redis client's publish method from the worker thread when needed.
        anyio.from_thread.run(
            redis_client.publish,
            EVENT_CHANNEL,
            json.dumps(data),
        )
    except Exception:
        # Pub/Sub is best-effort; do not fail the database operation.
        pass


def apply_filters(
    query,
    *,
    event_type=None,
    severity=None,
    status_filter=None,
    camera_id=None,
    assigned_to=None,
    zone_id=None,
    start_date=None,
    end_date=None,
):
    if event_type:
        query = query.where(Event.event_type == event_type)

    if severity:
        query = query.where(Event.severity == severity)

    if status_filter:
        query = query.where(Event.status == status_filter)

    if camera_id:
        query = query.where(Event.camera_id == camera_id)

    if assigned_to:
        query = query.where(
            Event.assigned_to.ilike(f"%{assigned_to.strip()}%")
        )

    if start_date:
        query = query.where(Event.created_at >= start_date)

    if end_date:
        query = query.where(Event.created_at <= end_date)

    if zone_id is not None:
        roi_devices = (
            select(ROI.device_id)
            .join(Zone, ROI.zone_id == Zone.id)
            .where(
                Zone.id == zone_id,
                ROI.device_id.is_not(None),
            )
        )
        query = query.where(Event.camera_id.in_(roi_devices))

    return query


def validate_stored_image(event: Event) -> None:
    """Validate that the stored image and its declared MIME type agree."""
    if event.image_base64 is None:
        if event.image_mime_type is not None:
            raise HTTPException(
                status_code=422,
                detail="image_mime_type requires image_base64",
            )
        return

    if event.image_mime_type is None:
        raise HTTPException(
            status_code=422,
            detail="image_mime_type is required when an image is provided",
        )

    try:
        image_info = inspect_image(event.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if image_info is None or image_info[0] != event.image_mime_type:
        raise HTTPException(
            status_code=422,
            detail="image_mime_type does not match the actual image format",
        )


@router.post("", response_model=EventResponse, status_code=201)
def create_event(
    payload: EventCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event_data = payload.model_dump()
    event = Event(**event_data)

    if event.assigned_to:
        event.assigned_by = user.id
        event.assigned_at = datetime.now(timezone.utc)
        if event.status == "pending":
            event.status = "assigned"

    validate_stored_image(event)

    db.add(event)
    db.commit()
    db.refresh(event)

    publish_event(request, event)
    return event


@router.get("")
def list_events(
    event_type: str | None = None,
    severity: str | None = Query(
        default=None,
        pattern=r"^(info|warning|critical)$",
    ),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(pending|assigned|acknowledged|resolved|closed)$",
    ),
    camera_id: str | None = None,
    assigned_to: str | None = None,
    zone_id: int | None = Query(default=None, ge=1),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort_by: str = Query(
        default="created_at",
        pattern=r"^(created_at|severity|status|event_type|camera_id|id)$",
    ),
    sort_order: str = Query(
        default="desc",
        pattern=r"^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before or equal to end_date",
        )

    query = apply_filters(
        select(Event),
        event_type=event_type,
        severity=severity,
        status_filter=status_filter,
        camera_id=camera_id,
        assigned_to=assigned_to,
        zone_id=zone_id,
        start_date=start_date,
        end_date=end_date,
    )

    total = db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    sort_column = getattr(Event, sort_by)
    query = query.order_by(
        sort_column.asc() if sort_order == "asc" else desc(sort_column),
        Event.id.desc(),
    )

    rows = db.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()

    # Exclude Base64 image data from list results to keep pagination efficient.
    items = [
        EventResponse.model_validate(event).model_dump(
            mode="json",
            exclude={"image_base64"},
        )
        for event in rows
    ]

    return {
        "success": True,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # Includes image_base64 and image_mime_type.
    return event


@router.patch("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: int,
    payload: EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    updates = payload.model_dump(exclude_unset=True)

    # Explicitly clearing the image also clears its MIME type.
    if "image_base64" in updates and updates["image_base64"] is None:
        updates["image_mime_type"] = None

    for key, value in updates.items():
        setattr(event, key, value)

    if event.status == "assigned" and event.assigned_to and event.assigned_at is None:
        event.assigned_by = user.id
        event.assigned_at = datetime.now(timezone.utc)

    validate_stored_image(event)

    db.commit()
    db.refresh(event)
    publish_event(request, event)
    return event


@router.patch("/{event_id}/assign", response_model=EventResponse)
def assign_event(
    event_id: int,
    payload: AssignRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    assigned_to = payload.assigned_to.strip()
    if not assigned_to:
        raise HTTPException(
            status_code=422,
            detail="assigned_to cannot be blank",
        )

    event.assigned_to = assigned_to
    event.assigned_by = user.id
    event.assigned_at = datetime.now(timezone.utc)

    if event.status == "pending":
        event.status = "assigned"

    db.commit()
    db.refresh(event)
    publish_event(request, event)
    return event


@router.patch("/{event_id}/acknowledge", response_model=EventResponse)
def acknowledge_event(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status in {"resolved", "closed"}:
        raise HTTPException(
            status_code=409,
            detail="Resolved/closed events cannot be acknowledged",
        )

    event.status = "acknowledged"
    event.acknowledged_by = user.id
    event.acknowledged_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(event)
    publish_event(request, event)
    return event


@router.patch("/{event_id}/resolve", response_model=EventResponse)
def resolve_event(
    event_id: int,
    payload: ResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="Closed events cannot be resolved again",
        )

    event.status = "resolved"
    event.resolved_by = user.id
    event.resolved_at = datetime.now(timezone.utc)
    event.resolution_notes = payload.notes

    db.commit()
    db.refresh(event)
    publish_event(request, event)
    return event


@router.patch("/{event_id}/close", response_model=EventResponse)
def close_event(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status != "resolved":
        raise HTTPException(
            status_code=409,
            detail="Resolve the event before closing it",
        )

    event.status = "closed"

    db.commit()
    db.refresh(event)
    publish_event(request, event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()
    return None


@router.websocket("/ws")
async def event_websocket(websocket: WebSocket):
    # Add WebSocket token authentication before production exposure.
    redis_client = getattr(websocket.app.state, "redis", None)

    if redis_client is None:
        await websocket.close(
            code=1013,
            reason="Live notifications unavailable",
        )
        return

    await websocket.accept()
    pubsub = redis_client.pubsub()

    async def redis_to_websocket():
        async for message in pubsub.listen():
            if message.get("type") == "message":
                await websocket.send_text(message.get("data", "{}"))

    async def websocket_reader():
        while True:
            message = (await websocket.receive_text()).lower()
            if message == "ping":
                await websocket.send_json({"type": "pong"})

    sender = None
    receiver = None

    try:
        await pubsub.subscribe(EVENT_CHANNEL)
        await websocket.send_json({
            "type": "connected",
            "channel": EVENT_CHANNEL,
        })

        sender = asyncio.create_task(redis_to_websocket())
        receiver = asyncio.create_task(websocket_reader())

        done, pending = await asyncio.wait(
            {sender, receiver},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            task.result()

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except RedisError:
        try:
            await websocket.close(
                code=1011,
                reason="Event service unavailable",
            )
        except Exception:
            pass
    finally:
        for task in (sender, receiver):
            if task is not None and not task.done():
                task.cancel()

        try:
            await pubsub.unsubscribe(EVENT_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass
