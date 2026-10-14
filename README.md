# REG-EYE FastAPI + Neon PostgreSQL + Redis starter

A starter backend built from the original FastAPI/Redis template. It adds PostgreSQL persistence, password-hashed users, opaque bearer sessions, dashboard aggregates, event history and acknowledgement, and Redis Pub/Sub for live notifications.

## Features / endpoints

- `GET /api/v1/health` — API liveness
- `GET /api/v1/health/ready` — PostgreSQL + Redis readiness
- `POST /api/v1/auth/login` — verify email/password and create session
- `GET /api/v1/auth/session` — inspect current session/user
- `POST /api/v1/auth/logout` — revoke current session
- `GET /api/v1/dashboard` — dashboard counts from persisted event data
- `POST /api/v1/events` — persist an event, then publish a live notification to Redis
- `GET /api/v1/events` — list/filter persisted events (`limit`, `offset`, `severity`, `status`, `camera_id`)
- `PATCH /api/v1/events/{event_id}/acknowledge` — acknowledge an event
- `WS /api/v1/events/ws` — Redis Pub/Sub live event stream (add WebSocket auth before production)
- Existing `/api/v1/cache` endpoints remain available.

Interactive API docs: `/docs`.

## 1. Local setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`: set `DATABASE_URL` to your Neon connection string, changing the prefix to `postgresql+psycopg://` and retaining `sslmode=require`. Set `REDIS_URL` to your Redis server. If running locally without a separate Redis server, use Docker Compose (Docker Desktop required). Do not commit `.env`.

## 2. Create the first administrator

Set `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` (at least 12 characters), and `BOOTSTRAP_ADMIN_NAME` in `.env`. Then run once:

```powershell
python -m scripts.create_admin
```

This creates the application tables and one admin account. The API also creates missing tables at startup as a convenience for this starter; use Alembic migrations before production.

## 3. Run

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. The API currently requires Redis at startup. With Docker Desktop, `docker compose up --build` starts Redis and the API; make sure `.env` contains the Neon URL and bootstrap values.

## 4. Login and use protected endpoints

Call `POST /api/v1/auth/login` with JSON:

```json
{"email":"admin@example.com","password":"your-long-password"}
```

Copy `access_token` from the response. For protected endpoints, send header:

```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

The token is random and only its SHA-256 hash is stored in PostgreSQL. Sessions expire after `SESSION_HOURS` and can be revoked by logout. Treat the token like a password; don't put it in logs or source code.

## 5. Create an event

`POST /api/v1/events` with bearer token:

```json
{
  "event_type": "PPE_VIOLATION",
  "camera_id": "CAM-001",
  "message": "Safety helmet not detected",
  "severity": "critical"
}
```

The event is stored in PostgreSQL first. Redis Pub/Sub is used only to notify connected clients; it is not the durable event store.

## Database notes

Tables: `users`, `login_sessions`, `events`. The dashboard's `total_cameras_with_events` counts distinct camera IDs that have generated at least one event; it is not a configured camera inventory count. Add a dedicated `cameras` table for real inventory.

## Production checklist

- Do not use student/free hosting for commercial industrial production without checking terms.
- Use managed Redis/TLS, HTTPS, strong secrets and a restricted CORS allowlist.
- Add plant/zone-based authorization before exposing multi-plant data. Current authenticated users can access all events.
- Authenticate WebSocket connections and apply camera permissions.
- Add Alembic migrations, backup/restore tests, rate limiting, audit logs, and monitoring.
- Add camera inventory and actual PPE-compliance analytics based on your real data model.
- Keep Neon credentials and admin passwords out of Git.
