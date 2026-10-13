from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.routes import cache, events, health
from app.core.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared async Redis client per API process.
    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )
    app.state.redis = redis_client

    try:
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception:
        logger.exception("Redis is not available at startup")
        await redis_client.aclose()
        raise

    yield

    await redis_client.aclose()
    logger.info("Redis connection closed")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend-only FastAPI starter with Redis and WebSocket event notifications.",
    lifespan=lifespan,
)

# No frontend is included. Restrict origins when a frontend is added.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(cache.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "FastAPI + Redis API is running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
