ALTER TABLE telemetry_events
    ADD COLUMN IF NOT EXISTS classification TEXT NULL,
    ADD COLUMN IF NOT EXISTS classification_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS classification_source TEXT NULL,
    ADD COLUMN IF NOT EXISTS handled BOOLEAN NULL,
    ADD COLUMN IF NOT EXISTS classified_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS telemetry_events_project_classification_idx
    ON telemetry_events (project_id, classification, occurred_at DESC);

CREATE TABLE IF NOT EXISTS telemetry_fingerprint_classifications (
    project_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    classification TEXT NOT NULL,
    reason TEXT NULL,
    source TEXT NOT NULL,
    confidence REAL NULL,
    model TEXT NULL,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS telemetry_fingerprint_classifications_project_idx
    ON telemetry_fingerprint_classifications (project_id, classified_at DESC);
