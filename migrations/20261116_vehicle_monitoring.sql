-- Run once against an existing PostgreSQL production database.
-- Take a database backup before applying this migration.

ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS last_online_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS last_offline_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS email_recipients JSON NULL,
    ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS object_count INTEGER NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS vehicle_journey_reports (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL,
    device_name VARCHAR(150) NOT NULL,
    online_at TIMESTAMPTZ NOT NULL,
    offline_at TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    total_detections INTEGER NOT NULL DEFAULT 0,
    total_events INTEGER NOT NULL DEFAULT 0,
    assigned_events INTEGER NOT NULL DEFAULT 0,
    acknowledged_events INTEGER NOT NULL DEFAULT 0,
    resolved_events INTEGER NOT NULL DEFAULT 0,
    event_breakdown JSON NULL,
    recipients JSON NULL,
    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
    email_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_vehicle_journey_reports_device_id
    ON vehicle_journey_reports (device_id);
CREATE INDEX IF NOT EXISTS ix_vehicle_journey_reports_offline_at
    ON vehicle_journey_reports (offline_at DESC);
