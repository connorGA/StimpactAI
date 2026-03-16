# Developer Guide – Self-Healing Software Platform

This document instructs AI coding agents (Cursor, etc.) how to implement the platform.

The project is a **monorepo containing multiple services** that together form a self-healing software system.

The platform detects production errors, analyzes the root cause using an AI agent, generates fixes, tests them, and deploys patches.

---

# Monorepo Structure

The repository must follow this structure.


self-healing-platform/

client-ui/
agent-platform/
git-integration/
sdk/
shared/
infra/


Each service is independent but communicates via APIs and event streams.

---

# Service Responsibilities

## 1. client-ui

User interface for interacting with the platform.

Responsibilities:

- display incidents
- display agent reasoning
- show logs and stack traces
- show patch diffs
- approve/reject deployments
- configure policies

Suggested stack:


Next.js
React
TypeScript
Tailwind
WebSockets


Key pages:


/incidents
/incidents/[id]
/policies
/metrics


---

## 2. agent-platform

This is the **core backend system**.

Responsibilities:

- ingest telemetry
- create incidents
- orchestrate agent workflows
- run sandbox environments
- generate patches
- verify fixes

Suggested stack:


Python
FastAPI
Temporal workflow engine
Postgres
Redis
Docker sandbox


Directory structure:


agent-platform/

api/
REST endpoints

workers/
background jobs

agent/
autonomous agent logic

sandbox/
sandbox runner

replay/
traffic replay tools

verification/
test validation

models/
AI reasoning modules


---

# Key APIs

The platform must expose the following APIs.

## Telemetry ingestion


POST /telemetry/error


Payload:


{
"project_id": "...",
"environment": "production",
"service": "backend",
"error_message": "...",
"stacktrace": "...",
"request": {...},
"response": {...},
"commit_sha": "...",
"timestamp": ...
}


---

## Incident API


GET /incidents
GET /incidents/{id}
POST /incidents/{id}/action


Actions:


approve_patch
reject_patch
deploy_patch
rollback_patch


---

# Agent Workflow

The autonomous agent runs through the following workflow.


incident created
↓
normalize telemetry
↓
classify failure
↓
reproduce failure
↓
analyze root cause
↓
generate patch
↓
generate tests
↓
verify fix
↓
score confidence
↓
produce patch artifact


Each step should be implemented as a **separate workflow step**.

---

# Sandbox Execution

The sandbox must:

- clone repository
- install dependencies
- replay failing request
- run services locally
- run tests

Sandbox implementation:


Docker container
Kubernetes job


Constraints:


network isolation
time limit
memory limit


---

# Root Cause Analysis

The agent should use these tools:


stack trace parsing
semantic code search
git blame
recent commit analysis
AST parsing


Implement code search tools using:


ripgrep
tree-sitter
vector embeddings


---

# Patch Generation

The agent should produce minimal patches.

Constraints:


max 3 files changed
max 200 lines diff
no database migrations
no auth system edits


Common fix strategies:


null guard
input validation
schema adaptation
retry/backoff logic
dependency downgrade
config change


---

# Verification

Before deployment the system must confirm:


original bug reproduced
patched code fixes bug
existing tests pass
no obvious regressions


Test layers:


unit tests
integration tests
traffic replay
browser tests
static analysis


---

# Git Integration Service

This service connects to the customer's repository.

Directory structure:


git-integration/

providers/
github.py
gitlab.py

pipeline/
ci_runner.py
deployment.py

policies/
policy_engine.py


Responsibilities:


create hotfix branch
commit patch
open pull request
trigger CI pipeline
deploy patch
rollback if needed


---

# CI/CD Workflow

Patch pipeline:


agent generates patch
↓
branch created
↓
commit pushed
↓
CI pipeline triggered
↓
tests run
↓
deployment gate
↓
deploy patch


CI stages:


lint
typecheck
unit tests
integration tests
replay tests
security scan


---

# Datastore Architecture

Primary database(Supabase):


Postgres


Tables:


incidents
incident_events
incident_messages
agent_runs
patch_runs
deploy_runs
policy_rules


---

# Artifact Storage

Large artifacts should be stored in object storage.

Examples:


logs
payload snapshots
trace dumps
screenshots
patch artifacts


Recommended storage:


S3
Cloudflare R2
GCS


---

# Metrics System

Metrics to track:


incident rate
MTTR (Mean Time to Resolution)
agent success rate
deployment success rate
rollback rate


Possible storage:


ClickHouse
BigQuery
TimescaleDB


---

# Code Context System

The agent requires a searchable code index.

Index includes:


file tree
AST nodes
function definitions
symbol graph
test coverage


Recommended implementation:


pgvector
OpenSearch
Qdrant


---

# SDK (Customer Integration)

Customers install the SDK in their application.

Example:


npm install selfheal-sdk


Initialization:


SelfHeal.init({
apiKey: "PROJECT_API_KEY"
})


SDK responsibilities:


capture exceptions
capture HTTP metadata
capture stack traces
send telemetry


SDK must support:


Node.js
Python
browser


---

# Security Requirements

The platform must enforce:


secret redaction
sandbox isolation
scoped git permissions
audit logs


Never expose production secrets to the agent.

---

# Development Order

Implement the system in this order.

### Phase 1

Observability + incidents


telemetry ingestion
incident creation
incident dashboard


### Phase 2

Agent reasoning


failure classification
root cause analysis
patch generation


### Phase 3

Sandbox verification


sandbox execution
traffic replay
test execution


### Phase 4

Git automation


branch creation
patch commits
PR creation


### Phase 5

Deployment automation


CI integration
staging deploy
canary deploy
rollback


---

# Design Principles

The system must prioritize:


safety
traceability
minimal patches
human override capability
auditability


All agent actions must be transparent and logged.

---

# Key Product Insight

Traditional tools:


detect → alert


This platform:


detect → reproduce → diagnose → patch → verify → deploy


The system forms a **closed-loop production healing system**.