CREATE TABLE IF NOT EXISTS project_telemetry_heartbeats (
    project_id TEXT NOT NULL,
    service TEXT NOT NULL,
    environment TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    commit_sha TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, service, environment)
);

CREATE INDEX IF NOT EXISTS project_telemetry_heartbeats_project_last_seen_idx
    ON project_telemetry_heartbeats (project_id, last_seen_at DESC);
