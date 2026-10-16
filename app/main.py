from contextlib import asynccontextmanager
import logging
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from app.api.routes import auth, cache, dashboard, events, health, users, devices, zones, reports
from app.core.config import settings
from app.database.connection import Base, engine, SessionLocal
from app.models import Event, LoginSession, User  # noqa: F401 - register ORM models
from app.core.security import hash_password
from sqlalchemy import select

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # For an empty Neon database, explicitly enable AUTO_CREATE_SCHEMA=true
    # for the first deployment. This creates tables and the first admin only
    # when no users exist. It does not migrate existing tables.
    if settings.environment.lower() in {"development", "test"} or settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)

    if settings.auto_create_schema:
        with SessionLocal() as db:
            has_users = db.scalar(select(User.id).limit(1)) is not None
            if not has_users:
                if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
                    raise RuntimeError(
                        "Empty database: set BOOTSTRAP_ADMIN_EMAIL and "
                        "BOOTSTRAP_ADMIN_PASSWORD to create the first admin."
                    )
                if len(settings.bootstrap_admin_password) < 4:
                    raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 4 characters.")
                email = settings.bootstrap_admin_email.strip().lower()
                username = re.sub(r"[^a-z0-9_.-]", "", email.split("@", 1)[0])[:50]
                if not username:
                    username = "administrator"
                admin = User(
                    name=settings.bootstrap_admin_name.strip() or "Administrator",
                    username=username[:50],
                    email=email,
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="admin",
                    is_active=True,
                )
                db.add(admin)
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                logger.info("Initial administrator created for configured bootstrap email")

    redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True, socket_connect_timeout=3, socket_timeout=3, health_check_interval=30)
    app.state.redis = redis_client
    try:
        await redis_client.ping()
        logger.info("Redis connection established")
        app.state.redis_available = True
    except Exception:
        # Redis is used only for best-effort live notifications. It must not
        # prevent authentication or normal HTTP endpoints from starting.
        logger.warning("Redis is unavailable; live notifications are disabled")
        app.state.redis_available = False
        await redis_client.aclose()
        app.state.redis = None
    yield
    if app.state.redis is not None:
        await app.state.redis.aclose()
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
    return {"message": "API is running", "docs": "/docs", "health": "/api/v1/health", "readiness": "/api/v1/health/ready"}
