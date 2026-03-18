CREATE TABLE IF NOT EXISTS patch_runs (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    patch_summary TEXT NOT NULL,
    rationale TEXT NOT NULL,
    target_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    unified_diff TEXT NOT NULL,
    verification_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL,
    based_on_commit_sha TEXT NULL,
    diff_line_count INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS patch_runs_incident_created_at_idx
    ON patch_runs (incident_id, created_at DESC);
