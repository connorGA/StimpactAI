CREATE TABLE IF NOT EXISTS async_jobs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    dedupe_key TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS job_attempts (
    id UUID PRIMARY KEY,
    async_job_id UUID NOT NULL REFERENCES async_jobs (id) ON DELETE CASCADE,
    worker_id TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY,
    incident_id UUID NULL REFERENCES incidents (id) ON DELETE SET NULL,
    patch_run_id UUID NULL REFERENCES patch_runs (id) ON DELETE SET NULL,
    sandbox_run_id UUID NULL REFERENCES sandbox_runs (id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL,
    storage_backend TEXT NOT NULL,
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    uri TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    checksum_sha256 TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE patch_runs
    ADD COLUMN IF NOT EXISTS repo_profile_id UUID NULL REFERENCES repo_profiles (id) ON DELETE SET NULL;

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS repo_profile_id UUID NULL REFERENCES repo_profiles (id) ON DELETE SET NULL;

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS async_job_id UUID NULL REFERENCES async_jobs (id) ON DELETE SET NULL;

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS executor_backend TEXT NOT NULL DEFAULT 'local';

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS external_job_id TEXT NULL;

CREATE TABLE IF NOT EXISTS sandbox_run_steps (
    id UUID PRIMARY KEY,
    sandbox_run_id UUID NOT NULL REFERENCES sandbox_runs (id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    command TEXT NULL,
    summary TEXT NOT NULL,
    artifact_id UUID NULL REFERENCES artifacts (id) ON DELETE SET NULL,
    exit_code INTEGER NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sandbox_run_attempts (
    id UUID PRIMARY KEY,
    sandbox_run_id UUID NOT NULL REFERENCES sandbox_runs (id) ON DELETE CASCADE,
    async_job_id UUID NULL REFERENCES async_jobs (id) ON DELETE SET NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS async_jobs_status_available_at_idx
    ON async_jobs (status, available_at ASC);

CREATE INDEX IF NOT EXISTS sandbox_run_steps_run_created_at_idx
    ON sandbox_run_steps (sandbox_run_id, created_at ASC);

CREATE INDEX IF NOT EXISTS artifacts_sandbox_run_created_at_idx
    ON artifacts (sandbox_run_id, created_at ASC);
