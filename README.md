# FastAPI Backend

FastAPI backend for event monitoring, user/session management, devices, plant zones, ROI polygons, dashboard analytics, pagination and CSV reports. PostgreSQL/Neon is the durable source of truth; Redis Pub/Sub is best-effort live notification only.

## First deployment to a new/empty Neon database

1. Create a Neon PostgreSQL database and copy its connection string.
2. Set `DATABASE_URL` in Render to a SQLAlchemy Psycopg URL, for example `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`.
3. Set `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` (at least 12 characters), and optionally `BOOTSTRAP_ADMIN_NAME` in Render environment variables. Use a strong unique password.
4. For the first deployment only, set `AUTO_CREATE_SCHEMA=true` in Render. The service creates tables on the empty database and creates the initial admin using the bootstrap variables.
5. Deploy and wait for a successful startup. Test `GET /api/v1/health/ready`, then open `/docs` and log in with the configured bootstrap email or username (the email prefix).
6. After successful initialization, set `AUTO_CREATE_SCHEMA=false` and redeploy. Keep the bootstrap credentials private; rotate the initial password after login.

`AUTO_CREATE_SCHEMA` is intended for initializing a new/empty database. SQLAlchemy `create_all()` does not migrate existing tables. For an existing database, back it up and use a reviewed migration instead. `scripts/create_admin.py` is also available for manual one-time setup.

Redis is optional for login and ordinary database-backed API endpoints. If Redis is unavailable, live event notifications and cache endpoints are unavailable, but login should continue to work if PostgreSQL is configured correctly.

## Configuration

Set `DATABASE_URL` to a Neon SQLAlchemy URL, e.g. `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`, `AUTO_CREATE_SCHEMA` (true only for empty-DB initialization), and `REDIS_URL` to a reachable Redis instance. Also set `SESSION_HOURS`, `CORS_ORIGINS`, and bootstrap admin environment variables as needed. Keep Redis private and use TLS/auth where available.

Install and run:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Swagger UI: `/docs`; OpenAPI: `/openapi.json`.



## Login behavior

`POST /api/v1/auth/login` accepts:

```json
{"identifier": "admin@example.com", "password": "your-password"}
```

or

```json
{"identifier": "admin", "password": "your-password"}
```

The backend automatically treats an identifier containing `@` as an email and searches `users.email`. Otherwise, it searches `users.username`. The older browser payloads `{"email":"...","password":"..."}` and `{"username":"...","password":"..."}` are also accepted. The configured initial administrator username is the sanitized part of the bootstrap email before `@`.

A successful response contains `access_token`; send it on protected requests as `Authorization: Bearer <access_token>`.

## API overview (`/api/v1`)

### Authentication
- `POST /auth/login` — send `identifier` with username or email plus password. For compatibility, `email` and `username` request fields are also accepted. The backend treats a value containing `@` as email and looks up `users.email`; otherwise it looks up `users.username`.
- `POST /auth/register` — administrator-only registration; checks username and email uniqueness.
- `GET /auth/session`, `POST /auth/logout`.

### Users (administrator-only unless noted)
- `GET /users` — filters `q`, `role`, `is_active`; pagination `page`, `page_size`.
- `POST /users`, `GET /users/{id}`, `PATCH /users/{id}`, `DELETE /users/{id}` (soft-deactivates and revokes sessions).
- `GET /users/me` — current profile.

### Events (bearer token required)
- `POST /events` — persist an event with optional severity/status/assignment/location.
- `GET /events` — filters `event_type`, `severity`, `status`, `camera_id`, `assigned_to`, `zone_id`, `start_date`, `end_date`; `page`, `page_size` (max 500), `sort_by`, `sort_order`.
- `GET /events/{id}`, `PATCH /events/{id}`.
- `PATCH /events/{id}/assign` — writes `assigned_to`, `assigned_by`, `assigned_at`.
- `PATCH /events/{id}/acknowledge` — writes acknowledgment user/time.
- `PATCH /events/{id}/resolve` — writes resolution user/time/notes.
- `PATCH /events/{id}/close` — closes a resolved event.
- `DELETE /events/{id}` — administrator-only.
- `WS /events/ws` — Redis live event stream. Add gateway/token authentication and camera authorization before exposing WebSockets publicly.

### Dashboard and reports
- `GET /dashboard` — date-filtered totals, severity/status breakdowns, top event types/cameras.
- `GET /dashboard/timeline?days=7` — daily event counts.
- `GET /dashboard/zones` — zone map summaries (zone membership is inferred through ROI `device_id` matching `events.camera_id`).
- `GET /reports/summary?start_date=...&end_date=...` — report aggregates.
- `GET /reports/events.csv` — downloadable CSV with optional date/severity/status/camera filters.

### Devices
- `POST /devices` — administrator registration.
- `GET /devices` — paginated device listing with search/status/enabled filters.
- `GET /devices/{device_id}`, `PATCH /devices/{device_id}`, `DELETE /devices/{device_id}` (soft disable).
- `POST /devices/{device_id}/heartbeat` — marks a registered device active and updates `last_seen_at`.

### Zones and ROIs
- `POST /zones`, `GET /zones`, `GET /zones/{id}`, `PATCH /zones/{id}`, `DELETE /zones/{id}`.
- `POST /rois`, `GET /rois?zone_id=&device_id=&enabled=`, `PATCH /rois/{id}`, `DELETE /rois/{id}`.
- `GET /analytics/zones/summary` — event counts grouped by zone.

Zone `boundary` is GeoJSON or a client-defined list of coordinates. ROI `points` stores polygon points; `coordinate_space` is `normalized`, `pixel`, or `geographic`. Normalized ROI coordinates should use a documented convention consistently (commonly 0..1). For map overlays, geographic coordinates should be GeoJSON `[longitude, latitude]`.

## Example requests

Login:

```json
{"identifier":"admin@example.com","password":"use-your-bootstrap-password"}
```

Create event:

```json
{
  "event_type":"PPE_VIOLATION",
  "camera_id":"CAM-001",
  "message":"Helmet not detected",
  "severity":"critical",
  "latitude":21.468,
  "longitude":83.981
}
```

Assign an event (the assignee is an arbitrary string, not necessarily an application user):

```json
{"assigned_to":"Rajesh Kumar, Phone: +919876543210"}
```

All protected routes require `Authorization: Bearer <access_token>`. Roles currently recognized: `admin`, `operator`, `viewer`; user/device/zone/ROI administration and event deletion are admin-only. If your operational policy differs, adjust route dependencies before deployment.

## Production notes

- The event WebSocket route is a starter implementation and currently accepts connections without token validation. Protect it before production exposure.
- Event Pub/Sub is best-effort; event rows are committed to PostgreSQL first.
- `assigned_to` is a single free-text field by design. For reliable structured reporting on contact name/phone, separate columns would be better, but this implementation preserves the requested one-field model.
- Add rate limiting, audit logs, backup/restore testing, and automated integration tests against a non-production Neon branch before production rollout.
