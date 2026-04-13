# Incident Loop Audit

## Current Path

1. The SDK posts errors to `/telemetry/error`.
2. Telemetry is normalized and persisted.
3. The outbox emits `telemetry.received`.
4. Incident creation resolves the project service and repo profile when possible.
5. Autonomous runs bootstrap the harness against the resolved repository context.
6. Successful repair attempts flow into sandbox verification before proposal or promotion.

## What Was Missing

- Autonomous runs did not persist enough launch context on the run snapshot itself.
- Onboarding verified heartbeat liveness, but not whether a project could actually launch an autonomous run.
- Operators had no single contract describing what the harness expects before starting.

## What This Pass Adds

- Richer autonomous run context fields:
  - project id
  - incident title and fingerprint
  - service and environment
  - latest telemetry id, commit SHA, and error message
  - repo/runtime commands and network allowlist
  - resolved provider repository
- A control-plane `harness-readiness` check that evaluates:
  - telemetry credentials
  - provider connectivity
  - service mapping
  - repo profile presence
  - reproduce and verify command contract
  - policy review
  - live telemetry freshness
  - analysis stack enablement
- Onboarding step 6 now surfaces launch readiness alongside heartbeat status.

## Result

The fixed part of the system is now the launch contract and evaluation discipline, not a library of hardcoded repairs. The agent still has to determine the fix itself, but it now starts from a better context package and the UI can show whether that package is actually ready.
