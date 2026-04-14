-- Track when and how incidents were resolved for live metrics (uptime, MTTR, agent resolution rate).
ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS resolution_source TEXT NULL;

COMMENT ON COLUMN incidents.resolved_at IS 'When the incident was marked resolved (user or autonomous agent).';
COMMENT ON COLUMN incidents.resolution_source IS 'user | autonomous_agent — how the incident was resolved.';

CREATE INDEX IF NOT EXISTS incidents_project_resolved_at_idx
    ON incidents (project_id, resolved_at DESC)
    WHERE resolved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS incidents_project_first_seen_at_idx
    ON incidents (project_id, first_seen_at DESC);
