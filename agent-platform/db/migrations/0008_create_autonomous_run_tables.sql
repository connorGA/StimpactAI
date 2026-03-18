CREATE TABLE IF NOT EXISTS autonomous_runs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    repo_profile_id UUID NULL REFERENCES repo_profiles (id) ON DELETE SET NULL,
    async_job_id UUID NULL REFERENCES async_jobs (id) ON DELETE SET NULL,
    feature_seeds JSONB NOT NULL DEFAULT '[]'::jsonb,
    initializer_summary TEXT NOT NULL,
    max_steps INTEGER NOT NULL DEFAULT 8,
    run_snapshot JSONB NOT NULL,
    outcome_snapshot JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS autonomous_run_attempts (
    id UUID PRIMARY KEY,
    autonomous_run_id UUID NOT NULL REFERENCES autonomous_runs (id) ON DELETE CASCADE,
    async_job_id UUID NULL REFERENCES async_jobs (id) ON DELETE SET NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS autonomous_runs_incident_created_at_idx
    ON autonomous_runs (incident_id, created_at DESC);

CREATE INDEX IF NOT EXISTS autonomous_runs_async_job_id_idx
    ON autonomous_runs (async_job_id);
