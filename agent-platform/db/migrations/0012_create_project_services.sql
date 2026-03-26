CREATE TABLE IF NOT EXISTS project_services (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    service_type TEXT NOT NULL DEFAULT 'other',
    repo_profile_id UUID NULL REFERENCES repo_profiles (id) ON DELETE SET NULL,
    owner TEXT NULL,
    deploy_target TEXT NULL,
    routing_hints JSONB NOT NULL DEFAULT '{}'::jsonb,
    startup_priority INTEGER NOT NULL DEFAULT 100,
    sandbox_healthcheck_command TEXT NULL,
    sandbox_healthcheck_url TEXT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, slug)
);

CREATE TABLE IF NOT EXISTS project_service_dependencies (
    service_id UUID NOT NULL REFERENCES project_services (id) ON DELETE CASCADE,
    depends_on_service_id UUID NOT NULL REFERENCES project_services (id) ON DELETE CASCADE,
    dependency_kind TEXT NOT NULL DEFAULT 'required',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (service_id, depends_on_service_id),
    CONSTRAINT project_service_dependencies_not_self
        CHECK (service_id <> depends_on_service_id)
);

CREATE INDEX IF NOT EXISTS project_services_project_priority_idx
    ON project_services (project_id, startup_priority ASC, created_at ASC);

CREATE INDEX IF NOT EXISTS project_services_project_repo_profile_idx
    ON project_services (project_id, repo_profile_id);

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS project_service_id UUID NULL REFERENCES project_services (id) ON DELETE SET NULL;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS repo_profile_id UUID NULL REFERENCES repo_profiles (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS incidents_project_service_idx
    ON incidents (project_service_id, last_seen_at DESC);

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS project_service_id UUID NULL REFERENCES project_services (id) ON DELETE SET NULL;

ALTER TABLE sandbox_runs
    ADD COLUMN IF NOT EXISTS dependency_service_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS sandbox_runs_project_service_created_at_idx
    ON sandbox_runs (project_service_id, created_at DESC);

ALTER TABLE autonomous_runs
    ADD COLUMN IF NOT EXISTS project_service_id UUID NULL REFERENCES project_services (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS autonomous_runs_project_service_created_at_idx
    ON autonomous_runs (project_service_id, created_at DESC);
