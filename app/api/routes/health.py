from fastapi import APIRouter, Request
from redis.exceptions import RedisError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    # Liveness: the API process is responding.
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request):
    # Readiness: API can reach its required Redis dependency.
    try:
        await request.app.state.redis.ping()
        return {"status": "ready", "dependencies": {"redis": "ok"}}
    except RedisError:
        # FastAPI will return a 503 only if we explicitly raise HTTPException.
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Redis unavailable")
