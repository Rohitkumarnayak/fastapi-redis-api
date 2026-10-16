-- API schema expansion for an existing Neon PostgreSQL database.
-- Take a Neon branch/backup before running. Execute once in Neon SQL Editor.
BEGIN;

-- Existing users: add username without dropping users or password/session data.
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);
UPDATE users
SET username = LEFT(
    COALESCE(NULLIF(regexp_replace(lower(split_part(email, '@', 1)), '[^a-z0-9_.-]', '', 'g'), ''), 'user')
    || '_' || id::text,
    50
)
WHERE username IS NULL OR btrim(username) = '';
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
ALTER TABLE users ALTER COLUMN username SET NOT NULL;

-- Add event workflow, assignment, resolution and location fields.
ALTER TABLE events ADD COLUMN IF NOT EXISTS assigned_to TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE events ADD COLUMN IF NOT EXISTS resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE events ADD COLUMN IF NOT EXISTS resolution_notes TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE events ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

-- If an earlier version made assigned_to an integer/FK, remove only its FK and
-- convert existing IDs to text (e.g. "12"). This preserves values; it cannot
-- infer a person's name/phone from an old user ID. Review that field after migration.
DO $$
DECLARE c RECORD;
DECLARE current_type TEXT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'events' AND column_name = 'assigned_to'
    ) THEN
        FOR c IN
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'events'::regclass AND contype = 'f'
              AND pg_get_constraintdef(oid) ILIKE '%(assigned_to)%'
        LOOP
            EXECUTE format('ALTER TABLE events DROP CONSTRAINT %I', c.conname);
        END LOOP;
        SELECT data_type INTO current_type
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'events' AND column_name = 'assigned_to';
        IF current_type <> 'text' THEN
            ALTER TABLE events ALTER COLUMN assigned_to TYPE TEXT USING assigned_to::text;
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_events_assigned_by ON events (assigned_by);
CREATE INDEX IF NOT EXISTS ix_events_resolved_by ON events (resolved_by);
CREATE INDEX IF NOT EXISTS ix_events_latitude_longitude ON events (latitude, longitude);

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    device_type VARCHAR(50) NOT NULL DEFAULT 'camera',
    ip_address VARCHAR(100),
    stream_url TEXT,
    location VARCHAR(255),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    status VARCHAR(30) NOT NULL DEFAULT 'inactive',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSON,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_devices_device_id ON devices (device_id);
CREATE INDEX IF NOT EXISTS ix_devices_status ON devices (status);
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS zones (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    site VARCHAR(150),
    boundary JSON,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_zones_name ON zones (name);

CREATE TABLE IF NOT EXISTS rois (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    zone_id INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    device_id VARCHAR(100),
    points JSON NOT NULL,
    coordinate_space VARCHAR(30) NOT NULL DEFAULT 'normalized',
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_rois_zone_id ON rois (zone_id);
CREATE INDEX IF NOT EXISTS ix_rois_device_id ON rois (device_id);

COMMIT;
