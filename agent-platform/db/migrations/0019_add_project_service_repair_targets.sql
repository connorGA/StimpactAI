ALTER TABLE project_services
    ADD COLUMN IF NOT EXISTS tracked_branch TEXT NULL;

CREATE INDEX IF NOT EXISTS project_services_project_tracked_branch_idx
    ON project_services (project_id, tracked_branch);
