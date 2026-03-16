# Self-Healing Software Platform

## Project Summary

This platform provides **autonomous production remediation** for deployed software systems.

The system detects runtime errors in production, analyzes the root cause using an AI agent, generates a fix, verifies the fix in a sandbox environment, and deploys the patch automatically or with human approval.

The platform is delivered as a **SaaS product** and integrates into customer codebases through a lightweight SDK.

---

# Core System Components

The platform is composed of three major subsystems:

1. Client UI (Incident & Control Interface)
2. Autonomous Agent + Observability Platform
3. Git / CI-CD / Deployment Integration Engine

Each subsystem runs as an independent service but communicates through shared APIs and event streams.

---

# Monorepo Structure


self-healing-platform/

client-ui/
Web application for incident monitoring and control.

agent-platform/
Autonomous fix agent
Observability ingestion
incident orchestration

git-integration/
Git provider integration
CI/CD pipeline orchestration
deployment automation

sdk/
Lightweight client SDK installed in customer applications

infra/
Infrastructure configuration
Kubernetes
Terraform
deployment configs

shared/
shared schemas
event contracts
types


---

# System Architecture Overview

The system operates as a **closed feedback loop**:


production error
↓
SDK captures error context
↓
error sent to platform
↓
incident created
↓
agent investigates
↓
agent reproduces issue in sandbox
↓
patch generated
↓
tests executed
↓
confidence evaluated
↓
patch committed to repo
↓
CI/CD pipeline executes
↓
deployment performed
↓
system monitored
↓
incident resolved


---

# Component 1 — Client UI

This is the **user-facing control plane** of the platform.

It allows engineers to:

- view incidents
- observe agent actions
- inspect generated patches
- approve or reject deployments
- configure autonomy policies
- review system metrics

## Responsibilities

The UI provides visibility into:

- incident timelines
- agent reasoning
- evidence and logs
- code diffs
- deployment status

## Core Pages


Incident Dashboard
Incident Detail / Chat Room
Patch Diff Viewer
Policy Configuration
Metrics / MTTR Dashboard
Agent Activity Logs


## Technology

Suggested stack:


Next.js
React
TypeScript
Tailwind
WebSockets


Realtime events are streamed from the control plane.

---

# Component 2 — Autonomous Agent + Observability Platform

This is the **core intelligence layer**.

It performs the following tasks:

1. Collect runtime errors
2. Create incidents
3. Reproduce failures
4. Diagnose root causes
5. Generate patches
6. Verify fixes
7. Produce deployable artifacts

---

# Observability Layer

Customer applications integrate using the **Self-Heal SDK**.

The SDK captures:


runtime exceptions
stack traces
HTTP request metadata
payload snapshots
response bodies
environment metadata
deployment SHA
feature flags


The SDK sends this data to the platform ingestion API.

The SDK runs in:


frontend applications
backend APIs
worker processes
cron jobs


SDK integration example:


npm install selfheal-sdk

import { SelfHeal } from "selfheal-sdk"

SelfHeal.init({
apiKey: "PROJECT_API_KEY"
})


---

# Incident Ingestion Pipeline

Incoming telemetry flows through the following stages:


Telemetry API
↓
Error normalization
↓
Correlation engine
↓
Incident creation
↓
Agent workflow trigger


Responsibilities:


deduplicate identical failures
group errors into incidents
estimate blast radius
assign severity
trigger investigation


---

# Autonomous Fix Agent

The agent operates as a **multi-stage workflow**, not a single model.

Agent stages:


incident normalization
failure classification
reproduction planning
sandbox provisioning
root cause analysis
patch generation
test generation
verification
confidence scoring
artifact generation


---

# Sandbox Runtime

The agent does not operate directly against production code.

Instead it launches an isolated sandbox.

Sandbox responsibilities:


checkout repository
install dependencies
recreate environment
replay failing request
run services locally
execute tests
apply candidate patch
verify behavior


Sandbox requirements:


container isolation
resource limits
network sandboxing
secrets redaction


Typical implementation:


Kubernetes job
ephemeral container


---

# Root Cause Analysis

The agent uses a combination of:


stack traces
git history
symbol graph
semantic code search
AST parsing


Supporting systems:


code index
vector embeddings
test coverage map


---

# Patch Generation

Patch strategies include:


null guards
schema adjustments
validation fixes
retry/backoff logic
dependency pinning
config rollback


Patch constraints:


minimal diff
limited file scope
no migrations
no auth changes


---

# Verification

Verification must confirm:


original bug reproduced
bug no longer occurs
tests pass
no new regressions
performance acceptable


Verification tools:


unit tests
integration tests
traffic replay
browser tests
static analysis


---

# Confidence Scoring

Confidence score determines deployment behavior.

Factors include:


tests passed
files changed
blast radius
bug reproduction success
risk category
service criticality


---

# Component 3 — Git Integration & Deployment Engine

This component connects the agent output to the customer's development pipeline.

Responsibilities:


create branches
commit patches
open pull requests
run CI pipelines
deploy fixes
rollback if needed


---

# Git Integration

The system integrates via Git provider apps.

Supported providers:


GitHub
GitLab
Bitbucket


Capabilities:


create hotfix branch
commit patch
open PR
trigger CI
read repository metadata


---

# CI/CD Integration

The platform triggers validation pipelines.

Example pipelines:


lint
type checking
unit tests
integration tests
replay tests
security scans


If validation succeeds the deployment engine proceeds.

---

# Deployment Modes

The platform supports multiple remediation modes.

## Mode 1 — Suggestion Only


agent opens PR
engineer reviews
engineer deploys


## Mode 2 — Staged Deployment


agent deploys to staging
engineer approves production


## Mode 3 — Autonomous Canary


agent deploys to small traffic segment
system monitors health
rollout proceeds automatically


## Mode 4 — Full Autonomous Hotfix


agent merges patch
deploys to production
monitors system health
rolls back if necessary


---

# Datastore Architecture

The platform uses multiple logical datastores.

## Postgres (Primary Database) - Supabase

Stores:


incidents
messages
deploy runs
agent runs
policy rules
user accounts


---

## Artifact Storage

Object storage stores large data blobs.

Examples:


logs
payload snapshots
trace dumps
screenshots
patch artifacts


Typical implementation:


S3
Cloudflare R2
GCS


---

## Metrics Store

Stores analytical metrics.

Examples:


incident frequency
MTTR
deployment success rate
agent accuracy


Possible tools:


ClickHouse
BigQuery
TimescaleDB


---

## Code Context Index

Stores searchable code metadata.

Used for agent reasoning.

Data includes:


repository file tree
AST indexes
symbol graphs
code embeddings
test coverage


Possible tools:


pgvector
OpenSearch
Qdrant
Weaviate


---

# Security Model

Security requirements:


payload redaction
secret stripping
sandbox isolation
scoped git permissions
audit logs


The agent must never receive raw production secrets.

---

# Deployment Model

Platform services run in cloud infrastructure.

Suggested architecture:


Kubernetes cluster
API services
worker queues
agent sandbox workers
event streams


---

# Integration Model

Customer integration requires three steps.

## Step 1 — Account creation

Customer creates organization and project.

## Step 2 — SDK installation

Customer installs SDK into application.

## Step 3 — Git integration

Customer connects repository.

Once connected the platform can:


observe runtime errors
generate fixes
deploy patches


---

# Development Principles

The system should prioritize:


deterministic verification
minimal patches
transparent reasoning
human override capability
auditability


The UI must always show **exactly what the agent did and why**.

---

# Product Philosophy

Traditional observability tools stop at:


detect → alert → coordinate


This platform continues the loop:


detect → reproduce → diagnose → patch → verify → deploy → confirm recovery


The system functions as a **self-healing production layer**.