CREATE TABLE IF NOT EXISTS provider_integrations (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    credentials_secret_ref_id UUID NULL,
    webhook_secret_ref_id UUID NULL,
    aws_region TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS provider_repositories (
    id UUID PRIMARY KEY,
    provider_integration_id UUID NOT NULL REFERENCES provider_integrations (id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_repository_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    default_branch TEXT NOT NULL,
    clone_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider_integration_id, external_repository_id)
);

CREATE TABLE IF NOT EXISTS secret_refs (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT NULL,
    backend TEXT NOT NULL,
    external_ref TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, label)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'provider_integrations_credentials_secret_ref_fk'
          AND conrelid = 'provider_integrations'::regclass
    ) THEN
        ALTER TABLE provider_integrations
            ADD CONSTRAINT provider_integrations_credentials_secret_ref_fk
            FOREIGN KEY (credentials_secret_ref_id) REFERENCES secret_refs (id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'provider_integrations_webhook_secret_ref_fk'
          AND conrelid = 'provider_integrations'::regclass
    ) THEN
        ALTER TABLE provider_integrations
            ADD CONSTRAINT provider_integrations_webhook_secret_ref_fk
            FOREIGN KEY (webhook_secret_ref_id) REFERENCES secret_refs (id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS repo_profiles (
    id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_repository_id UUID NOT NULL REFERENCES provider_repositories (id) ON DELETE CASCADE,
    runtime_kind TEXT NOT NULL,
    base_image TEXT NULL,
    install_command TEXT NULL,
    startup_commands JSONB NOT NULL DEFAULT '[]'::jsonb,
    reproduce_command TEXT NOT NULL,
    verify_command TEXT NOT NULL,
    success_criteria TEXT NULL,
    network_allowlist JSONB NOT NULL DEFAULT '[]'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repo_profile_secret_refs (
    repo_profile_id UUID NOT NULL REFERENCES repo_profiles (id) ON DELETE CASCADE,
    secret_ref_id UUID NOT NULL REFERENCES secret_refs (id) ON DELETE CASCADE,
    mount_as TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_profile_id, secret_ref_id, mount_as)
);

CREATE INDEX IF NOT EXISTS provider_repositories_provider_owner_name_idx
    ON provider_repositories (provider, owner, name);

CREATE INDEX IF NOT EXISTS repo_profiles_project_active_idx
    ON repo_profiles (project_id, active);
