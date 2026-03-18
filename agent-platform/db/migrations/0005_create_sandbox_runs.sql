CREATE TABLE IF NOT EXISTS sandbox_runs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    patch_run_id UUID NOT NULL REFERENCES patch_runs (id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    install_command TEXT NULL,
    reproduce_command TEXT NOT NULL,
    verify_command TEXT NOT NULL,
    reproduction_succeeded BOOLEAN NOT NULL,
    patch_applied BOOLEAN NOT NULL,
    verification_succeeded BOOLEAN NOT NULL,
    summary TEXT NOT NULL,
    execution_log TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sandbox_runs_incident_created_at_idx
    ON sandbox_runs (incident_id, created_at DESC);
