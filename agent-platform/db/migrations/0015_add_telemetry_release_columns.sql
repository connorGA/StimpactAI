ALTER TABLE telemetry_events
ADD COLUMN IF NOT EXISTS release TEXT NULL;

ALTER TABLE project_telemetry_heartbeats
ADD COLUMN IF NOT EXISTS release TEXT NULL;
