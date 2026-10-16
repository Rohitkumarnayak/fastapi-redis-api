from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

router = APIRouter(prefix="/cache", tags=["cache"])


class CacheWrite(BaseModel):
    value: str = Field(min_length=1, max_length=10000)
    ttl_seconds: int = Field(default=300, ge=1, le=86400)


@router.put("/{key}")
async def set_cache(key: str, payload: CacheWrite, request: Request):
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="Key must be 200 characters or fewer")
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    try:
        await redis_client.set(
            f"starter:{key}", payload.value, ex=payload.ttl_seconds
        )
        return {"key": key, "stored": True, "ttl_seconds": payload.ttl_seconds}
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")


@router.get("/{key}")
async def get_cache(key: str, request: Request):
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    try:
        value = await redis_client.get(f"starter:{key}")
        if value is None:
            raise HTTPException(status_code=404, detail="Cache key not found")
        return {"key": key, "value": value}
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")


@router.delete("/{key}", status_code=204)
async def delete_cache(key: str, request: Request):
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    try:
        await redis_client.delete(f"starter:{key}")
        return Response(status_code=204)
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
