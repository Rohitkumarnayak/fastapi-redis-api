from fastapi import APIRouter, HTTPException, Request
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.database.connection import engine

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health():
    return {"status": "ok"}

@router.get("/ready")
async def readiness(request: Request):
    dependencies = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        dependencies["postgresql"] = "ok"
    except SQLAlchemyError:
        dependencies["postgresql"] = "unavailable"
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        dependencies["redis"] = "disabled"
    else:
        try:
            await redis_client.ping()
            dependencies["redis"] = "ok"
        except RedisError:
            dependencies["redis"] = "unavailable"
    # PostgreSQL is required for core APIs. Redis is optional for live events/cache.
    if dependencies.get("postgresql") != "ok":
        raise HTTPException(status_code=503, detail={"status": "not_ready", "dependencies": dependencies})
    return {"status": "ready", "dependencies": dependencies}
