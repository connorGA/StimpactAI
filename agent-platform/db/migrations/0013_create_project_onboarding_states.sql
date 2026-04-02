CREATE TABLE IF NOT EXISTS project_onboarding_states (
    project_id TEXT PRIMARY KEY,
    policy_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    sdk_setup_status TEXT NOT NULL DEFAULT 'pending',
    sdk_setup_provider_repository_id TEXT NULL,
    sdk_setup_change_request_url TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
