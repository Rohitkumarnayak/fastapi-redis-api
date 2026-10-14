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
    try:
        await request.app.state.redis.ping()
        dependencies["redis"] = "ok"
    except RedisError:
        dependencies["redis"] = "unavailable"
    if any(value != "ok" for value in dependencies.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "dependencies": dependencies})
    return {"status": "ready", "dependencies": dependencies}
