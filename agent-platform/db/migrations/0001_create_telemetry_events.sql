CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    service TEXT NOT NULL,
    error_message TEXT NOT NULL,
    stacktrace TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    request_payload JSONB NULL,
    response_payload JSONB NULL,
    commit_sha TEXT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS telemetry_events_project_fingerprint_idx
    ON telemetry_events (project_id, fingerprint, occurred_at DESC);
