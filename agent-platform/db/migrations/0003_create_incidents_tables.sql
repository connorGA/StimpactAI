CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    service TEXT NOT NULL,
    environment TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    severity TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 1,
    latest_telemetry_id UUID NOT NULL REFERENCES telemetry_events (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS incidents_open_project_fingerprint_idx
    ON incidents (project_id, fingerprint)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS incidents_status_last_seen_at_idx
    ON incidents (status, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS incident_events (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    telemetry_id UUID NOT NULL UNIQUE REFERENCES telemetry_events (id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    stacktrace TEXT NOT NULL,
    request_payload JSONB NULL,
    response_payload JSONB NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_events_incident_occurred_at_idx
    ON incident_events (incident_id, occurred_at DESC);
