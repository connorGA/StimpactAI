# Harness Launch Contract

## Objective

An autonomous run should receive enough evidence and repository context to investigate unfamiliar failures without relying on predefined fixes.

## Required Inputs

- Incident identity:
  - `incident_id`
  - `project_id`
  - service
  - environment
  - title
  - fingerprint
- Latest telemetry context:
  - `latest_telemetry_id`
  - latest telemetry commit SHA when available
  - normalized error message
  - stacktrace and request/response metadata from the incident event stream
- Repository context:
  - `repo_profile_id`
  - provider repository owner and name
  - repository root or clone target
  - runtime kind
- Sandbox command contract:
  - install command
  - reproduce command
  - verify command
  - success criteria
  - network allowlist
- Service topology:
  - resolved project service
  - dependency service slugs when declared
- Verification hints:
  - browser verification URLs when available
  - feature seeds derived from the incident objective

## Required Agent Loop

1. Inspect telemetry and incident evidence.
2. Gather repository context and map likely failure surfaces.
3. Form a repair hypothesis.
4. Reproduce inside the sandbox.
5. Edit code.
6. Re-run verification.
7. Either converge, retry with new evidence, or stop with a grounded blocked state.

## Stop Conditions

- Verification passes with fresh evidence.
- The run exceeds the repair budget.
- The harness reaches a blocked state with insufficient evidence.
- Policy requires human approval before continuing.

## Non-Goals

- Hardcoded patch recipes by bug type.
- Treating seeded drill scenarios as the product's repair logic.
- Promoting fixes without reproduction and verification evidence.
