ALTER TABLE telemetry_events
ADD COLUMN IF NOT EXISTS dist TEXT NULL,
ADD COLUMN IF NOT EXISTS session_id TEXT NULL,
ADD COLUMN IF NOT EXISTS user_payload JSONB NULL,
ADD COLUMN IF NOT EXISTS tags_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS contexts_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS breadcrumbs_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS symbolicated_stacktrace TEXT NULL;

ALTER TABLE incident_events
ADD COLUMN IF NOT EXISTS release TEXT NULL,
ADD COLUMN IF NOT EXISTS dist TEXT NULL,
ADD COLUMN IF NOT EXISTS session_id TEXT NULL,
ADD COLUMN IF NOT EXISTS user_payload JSONB NULL,
ADD COLUMN IF NOT EXISTS tags_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS contexts_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS breadcrumbs_payload JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS telemetry_events_release_idx
    ON telemetry_events (project_id, release, occurred_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_events_session_idx
    ON telemetry_events (project_id, session_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS release_sourcemaps (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    release TEXT NOT NULL,
    dist TEXT NOT NULL DEFAULT '',
    artifact_id UUID NOT NULL REFERENCES artifacts (id) ON DELETE CASCADE,
    bundle_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS release_sourcemaps_project_release_dist_bundle_idx
    ON release_sourcemaps (project_id, release, dist, bundle_path);
