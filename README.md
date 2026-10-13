# FastAPI + Uvicorn + Redis API starter

Backend-only starter project. No frontend is included.

## Included
- FastAPI application with lifespan-managed async Redis client
- Uvicorn ASGI server
- `/api/v1/health` and `/api/v1/health/ready`
- Redis cache routes
- Event publish route using Redis Pub/Sub
- WebSocket starter route
- Environment configuration and Docker Compose

## Important WebSocket note
The starter WebSocket endpoint runs concurrent sender/receiver tasks and forwards Redis Pub/Sub notifications. Add authentication and authorization before exposing it. Handle task cancellation, reconnects, backpressure, and per-user camera filtering carefully as the project grows.

Redis Pub/Sub is transient and at-most-once. It is appropriate for best-effort notifications, not as the only storage for safety-critical events. Persist authoritative events in SQL Server and/or use a durable queue/stream for reliable processing.

## 1. Create environment
Copy `.env.example` to `.env`.

Windows PowerShell:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Start Redis
With Docker Compose:
```bash
docker compose up -d redis
```

Or install/run Redis separately and update `REDIS_URL` in `.env`.

## 3. Run API locally
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health
- Readiness: http://127.0.0.1:8000/api/v1/health/ready

Do not use `--reload` in production.

## 4. Try the cache API
```bash
curl -X PUT http://127.0.0.1:8000/api/v1/cache/demo ^
  -H "Content-Type: application/json" ^
  -d "{\"value\":\"hello\",\"ttl_seconds\":60}"

curl http://127.0.0.1:8000/api/v1/cache/demo
curl -X DELETE http://127.0.0.1:8000/api/v1/cache/demo
```

PowerShell may require `curl.exe` or `Invoke-RestMethod`.

## 5. Publish an event
```bash
curl -X POST http://127.0.0.1:8000/api/v1/events ^
  -H "Content-Type: application/json" ^
  -d "{\"event_type\":\"PPE_VIOLATION\",\"camera_id\":\"CAM-001\",\"message\":\"Helmet not detected\",\"severity\":\"warning\"}"
```

## API routes
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Root information |
| GET | `/api/v1/health` | Liveness check |
| GET | `/api/v1/health/ready` | Redis readiness check |
| PUT | `/api/v1/cache/{key}` | Write a cache value with TTL |
| GET | `/api/v1/cache/{key}` | Read a cache value |
| DELETE | `/api/v1/cache/{key}` | Delete a cache value |
| POST | `/api/v1/events` | Publish an event to Redis Pub/Sub |
| WS | `/api/v1/events/ws` | Minimal WebSocket starter |

## Suggested next additions
1. SQL Server repository and connection pooling
2. JWT authentication and role/plant/camera-level authorization
3. Production WebSocket sender/receiver task management
4. Durable event queue, retry policy and idempotency
5. Structured logs, metrics, tracing and rate limiting
6. Automated tests and load tests

## Production cautions
- Keep `.env` and secrets out of source control.
- Do not expose Redis publicly; use private networking and authentication/TLS as appropriate.
- Restrict CORS origins to trusted origins when a browser frontend is added.
- Add authentication and authorization before deploying non-public routes.
- Do not put video frames or large files in Redis; store media in the VMS/media service or object storage.
- Scale Uvicorn workers only after benchmarking. Each worker is a separate process and creates its own Redis connection pool.
