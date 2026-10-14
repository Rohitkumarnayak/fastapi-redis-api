import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from redis.exceptions import RedisError

from app.api.routes.auth import get_current_user
from app.database.connection import get_db
from app.models import Event, User
from app.schemas.events import EventCreate, EventResponse

router = APIRouter(prefix="/events", tags=["events"])
EVENT_CHANNEL = "regeye:events"


@router.post("", response_model=EventResponse, status_code=201)
def create_event(payload: EventCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = Event(event_type=payload.event_type, camera_id=payload.camera_id, message=payload.message, severity=payload.severity)
    db.add(event)
    db.commit()
    db.refresh(event)
    data = EventResponse.model_validate(event).model_dump(mode="json")
    # PostgreSQL is the durable source of truth; Redis Pub/Sub is only for live updates.
    try:
        import anyio
        anyio.from_thread.run(request.app.state.redis.publish, EVENT_CHANNEL, json.dumps(data))
    except Exception:
        # Do not fail a successfully persisted event if live notification is unavailable.
        pass
    return event


@router.get("", response_model=list[EventResponse])
def list_events(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), severity: str | None = None, status_filter: str | None = Query(default=None, alias="status"), camera_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Event)
    if severity:
        query = query.where(Event.severity == severity)
    if status_filter:
        query = query.where(Event.status == status_filter)
    if camera_id:
        query = query.where(Event.camera_id == camera_id)
    return list(db.scalars(query.order_by(desc(Event.created_at)).offset(offset).limit(limit)).all())


@router.patch("/{event_id}/acknowledge", response_model=EventResponse)
def acknowledge_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.status = "acknowledged"
    event.acknowledged_by = user.id
    event.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event


@router.websocket("/ws")
async def event_websocket(websocket: WebSocket):
    # For production, authenticate WebSocket connections and apply per-user camera permissions.
    await websocket.accept()
    redis_client = websocket.app.state.redis
    pubsub = redis_client.pubsub()
    async def redis_to_websocket():
        async for message in pubsub.listen():
            if message.get("type") == "message":
                await websocket.send_text(message.get("data", "{}"))
    async def websocket_reader():
        while True:
            if (await websocket.receive_text()).lower() == "ping":
                await websocket.send_json({"type": "pong"})
    try:
        await pubsub.subscribe(EVENT_CHANNEL)
        await websocket.send_json({"type": "connected", "channel": EVENT_CHANNEL})
        sender = asyncio.create_task(redis_to_websocket())
        receiver = asyncio.create_task(websocket_reader())
        done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except RedisError:
        try:
            await websocket.close(code=1011, reason="Event service unavailable")
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(EVENT_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass
