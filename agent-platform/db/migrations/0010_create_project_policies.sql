CREATE TABLE IF NOT EXISTS project_policies (
    project_id TEXT PRIMARY KEY,
    autonomy_mode TEXT NOT NULL DEFAULT 'recommend',
    require_human_approval BOOLEAN NOT NULL DEFAULT TRUE,
    allow_production_writes BOOLEAN NOT NULL DEFAULT FALSE,
    allow_low_risk_autonomy BOOLEAN NOT NULL DEFAULT TRUE,
    block_during_active_deploys BOOLEAN NOT NULL DEFAULT TRUE,
    restrict_to_approved_services BOOLEAN NOT NULL DEFAULT FALSE,
    require_rollback_plan BOOLEAN NOT NULL DEFAULT TRUE,
    require_post_action_verification BOOLEAN NOT NULL DEFAULT TRUE,
    approved_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    failure_classifier_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    root_cause_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    patch_planner_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    runbook_executor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
