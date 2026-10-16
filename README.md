# FastAPI Backend

FastAPI backend for event monitoring, user/session management, devices, plant zones, ROI polygons, dashboard analytics, pagination and CSV reports. PostgreSQL/Neon is the durable source of truth; Redis Pub/Sub is best-effort live notification only.

## Before deployment to an existing Neon database

1. Create a Neon branch or backup.
2. Run `migrations/001_expand_schema.sql` in the Neon SQL Editor. It adds `users.username`, event workflow/location fields, and the `devices`, `zones`, and `rois` tables. Existing user/event/session rows are retained. If `events.assigned_to` was an integer, its existing values are converted to text IDs; the migration cannot guess contact names or phone numbers.
3. Set environment variables in your deployment provider. Never copy `.env` into the deployment artifact or commit secrets.
4. Deploy the code and restart the service.
5. If your database has a different schema from the supplied app, inspect it and adapt the migration before execution.

In production, this app does not run `create_all()` at startup. In `development` or `test`, it creates missing tables for local convenience. `create_all()` does not migrate existing tables.

## Configuration

Set `DATABASE_URL` to a Neon SQLAlchemy URL, e.g. `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`, and `REDIS_URL` to a reachable Redis instance. Also set `SESSION_HOURS`, `CORS_ORIGINS`, and bootstrap admin environment variables as needed. Keep Redis private and use TLS/auth where available.

Install and run:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Swagger UI: `/docs`; OpenAPI: `/openapi.json`.

## API overview (`/api/v1`)

### Authentication
- `POST /auth/login` — `identifier` accepts username or email plus password.
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
{"identifier":"admin@example.com","password":"replace-me"}
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
