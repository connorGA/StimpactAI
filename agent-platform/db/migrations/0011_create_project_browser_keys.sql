CREATE TABLE IF NOT EXISTS project_browser_keys (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    allowed_origins JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    last_used_at TIMESTAMPTZ NULL,
    last_issued_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS project_browser_keys_key_hash_idx
    ON project_browser_keys (key_hash);

CREATE INDEX IF NOT EXISTS project_browser_keys_project_status_idx
    ON project_browser_keys (project_id, status, created_at DESC);
