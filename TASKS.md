# Self Healing Platform Task List

Cursor should only work on ONE task at a time.

Each task must be completed before moving to the next.

Do not refactor unrelated parts of the system.

---

# Phase 1 — Observability + Incident System

## Task 1

Create the telemetry ingestion API.

Service:
agent-platform

Endpoint:

POST /telemetry/error

Responsibilities:

• validate incoming telemetry
• normalize error payload
• store event in Postgres
• publish incident event

---

## Task 2

Implement incident creation logic.

Requirements:

• group identical errors
• create incident record
• attach stack traces
• assign severity

Tables:

incidents
incident_events

---

## Task 3

Implement incident dashboard API.

Endpoints:

GET /incidents
GET /incidents/{id}

---

# Phase 2 — Agent Workflow

## Task 4

Implement failure classifier.

Input:

incident

Output:

failure category

---

## Task 5

Implement root cause analysis.

Tools required:

• stack trace parsing
• code search
• git history
• AI synthesis of a grounded hypothesis

Requirements:

• gather deterministic evidence first
• send the collected evidence to AI for reasoning
• return a structured root-cause hypothesis, not raw context only

---

## Task 6

Implement patch generation.

Constraints:

• max 3 files
• max 200 lines

---

# Phase 3 — Sandbox

## Task 7

Implement sandbox runner.

Requirements:

• clone repo
• install dependencies
• replay failing request

---

# Phase 4 — Git Integration

## Task 8

Create GitHub integration.

Capabilities:

• create branch
• commit patch
• open PR