import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

router = APIRouter(prefix="/events", tags=["events"])
EVENT_CHANNEL = "starter:events"


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=2000)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")


@router.post("", status_code=202)
async def publish_event(payload: EventCreate, request: Request):
    """
    Publish a sample event to Redis Pub/Sub.
    Pub/Sub is transient: it does not retain messages for disconnected clients.
    Persist important events in a database or durable queue in production.
    """
    event = {
        "id": str(uuid4()),
        "event_type": payload.event_type,
        "camera_id": payload.camera_id,
        "message": payload.message,
        "severity": payload.severity,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        subscribers = await request.app.state.redis.publish(
            EVENT_CHANNEL, json.dumps(event)
        )
        return {
            "accepted": True,
            "event": event,
            "redis_subscriber_count": subscribers,
        }
    except RedisError:
        raise HTTPException(status_code=503, detail="Event service unavailable")


@router.websocket("/ws")
async def event_websocket(websocket: WebSocket):
    """
    Development starter endpoint.
    Add authentication, authorization and per-user camera filtering before production.
    """
    await websocket.accept()
    redis_client = websocket.app.state.redis
    pubsub = redis_client.pubsub()

    async def redis_to_websocket():
        async for message in pubsub.listen():
            if message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, str):
                    await websocket.send_text(data)

    async def websocket_reader():
        while True:
            message = await websocket.receive_text()
            if message.lower() == "ping":
                await websocket.send_json({"type": "pong"})

    try:
        await pubsub.subscribe(EVENT_CHANNEL)
        await websocket.send_json({"type": "connected", "channel": EVENT_CHANNEL})

        sender = asyncio.create_task(redis_to_websocket())
        receiver = asyncio.create_task(websocket_reader())
        done, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            # Re-raise unexpected task errors; disconnects are handled below.
            task.result()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except RedisError:
        # Closing the socket is preferable to silently pretending live updates work.
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
