from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from app.api.routes import auth, cache, dashboard, events, health, users, devices, zones, reports
from app.core.config import settings
from app.database.connection import Base, engine
from app.models import Event, LoginSession, User  # noqa: F401 - register ORM models

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production schema changes are applied explicitly with migrations; do not mutate Neon schema on startup.
    if settings.environment.lower() in {"development", "test"}:
        Base.metadata.create_all(bind=engine)
    redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True, socket_connect_timeout=3, socket_timeout=3, health_check_interval=30)
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
    engine.dispose()
    logger.info("Database and Redis connections closed")

app = FastAPI(title=settings.app_name, version="1.0.0", description="FastAPI backend with PostgreSQL persistence, opaque bearer sessions, event APIs and Redis live notifications.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(zones.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(cache.router, prefix="/api/v1")

@app.get("/", tags=["root"])
async def root():
    return {"message": "SMART API is running", "docs": "/docs", "health": "/api/v1/health", "readiness": "/api/v1/health/ready"}
