-- One-time / operator script: remove all incident-related rows. Does not drop tables or
-- change schema. Safe to re-run on an empty database.
-- Does not touch: projects, orgs, project_services, repo_profiles, policies, users, etc.

BEGIN;

-- Order respects FKs; CASCADE handles any we miss between these tables.
TRUNCATE TABLE
  release_sourcemaps,
  sandbox_run_steps,
  sandbox_run_attempts,
  artifacts,
  sandbox_runs,
  autonomous_run_attempts,
  autonomous_runs,
  patch_runs,
  incident_events,
  incidents,
  telemetry_events,
  telemetry_fingerprint_classifications,
  project_telemetry_heartbeats,
  outbox_events,
  job_attempts,
  async_jobs
RESTART IDENTITY CASCADE;

COMMIT;
