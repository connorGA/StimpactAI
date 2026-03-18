# Agent Harness Build Plan

This file defines the implementation plan for the internal harness that STIMPACTAI's future sandbox repair agent will run inside.

This is NOT the repair agent logic itself yet.

This harness provides:
- constrained internal tools
- context management
- two-agent architecture
- git-based recovery discipline
- browser-based end-to-end verification
- developer environment bootstrap
- project feature ground-truth tracking

Cursor should complete ONE task at a time.
Do not skip ahead.
Do not refactor unrelated systems.
Do not implement the full repair agent before the harness is complete.

---

# High-Level Goal

Build a safe, structured, verifiable runtime in which a future coding/fix agent can:
- inspect a repo
- navigate files safely
- edit files with validation
- verify changes through browser automation
- maintain compressed working context
- recover to last-known-good states through git
- operate against a known feature/task ground truth

The harness should be usable by future agent sessions repeatedly across many repos and many bug-fix tasks.

---

# Core Harness Components

The harness has 6 major subsystems:

1. Search and Navigation Tools
2. Stateful File Viewer
3. File Editor with Lint / Syntax Guardrails
4. Context Management Layer
5. Two-Agent Runtime Architecture
6. End-to-End Browser Verification Layer

---

# Harness Monorepo Location

Assume the harness implementation lives inside the agent platform codebase, in a structure like:

agent-platform/
  harness/
    tools/
    runtime/
    context/
    verification/
    profiles/
    schemas/
    prompts/
    git_ops/

shared/
  schemas/
  contracts/

Cursor may adapt filenames if needed, but should preserve clean boundaries between these subsystems.

---

# Phase 1 — Tooling Layer

## Task 1 — Build search/navigation tool interfaces

Implement the internal repo search/navigation tools:

- find_file
- search_file
- search_dir

Requirements:
- each tool must have a strict typed input schema
- each tool must return structured results
- result count must be capped at 50
- if results exceed 50, the tool must NOT dump the full output
- instead it must return:
  - too_many_results = true
  - result_count estimate if possible
  - refinement guidance string
- tools should be designed for agent use, not human CLI use
- output must be compact and deterministic

Expected behavior:
- find_file locates files by name or glob-like query
- search_file searches within a specific file
- search_dir searches recursively within a directory
- tools should support exact text first
- semantic search can be added later, but start with deterministic string search

Implementation notes:
- use ripgrep where useful under the hood
- do not expose raw uncontrolled shell output directly to the agent
- wrap command output into normalized tool response objects

Deliverables:
- tool interface definitions
- implementation of all 3 tools
- structured response models
- unit tests for:
  - <= 50 results
  - > 50 results
  - no results
  - invalid path

Cursor prompt for this task:
"Implement Task 1 from AGENT_HARNESS_TASKS.md only. Build typed internal search/navigation tools named find_file, search_file, and search_dir with deterministic structured outputs and a hard cap of 50 results. If more than 50 results exist, return a refinement-required response instead of dumping results."

---

## Task 2 — Build the stateful file viewer

Implement a stateful file viewer tool for the agent.

Requirements:
- show exactly 100 lines at a time by default
- prepend explicit line numbers to every visible line
- maintain stateful cursor/position per open file session
- support:
  - open file
  - next page
  - previous page
  - jump to line
  - view centered around line
- viewer state must survive across agent turns within the session
- viewer output must be deterministic and compact

Behavior:
- line numbers must be part of the actual visible output
- the agent should not need to calculate line numbers itself
- the viewer should expose:
  - file path
  - current start line
  - current end line
  - total line count if known

Suggested interface:
- open_file(path)
- view_next(path)
- view_prev(path)
- view_at_line(path, line)

Deliverables:
- stateful viewer session manager
- file view response schema
- tests for paging, jumping, boundaries, and invalid files

Cursor prompt for this task:
"Implement Task 2 only. Build a stateful file viewer that shows 100 lines at a time, includes explicit line numbers in every output line, and maintains paging position across interactions."

---

## Task 3 — Build guarded file editing with lint/syntax feedback

Implement the file editor tool.

Requirements:
- edit operation accepts:
  - file path
  - start line
  - end line
  - replacement text
- apply the edit as one atomic operation
- before finalizing the edit, run syntax/lint validation for the modified file
- if validation fails:
  - reject the edit
  - do not persist the change
  - return:
    - validation failure message
    - original affected code
    - attempted replacement
    - linter/syntax output
- if validation succeeds:
  - persist the change
  - return success plus changed region summary

Behavior:
- prioritize syntax correctness first
- linting can be best-effort by language
- if no linter exists for the language, still perform syntax parse validation where possible
- must be able to support Python, JS/TS first
- design for future language adapters

Implementation notes:
- wrap language validators behind an interface:
  - validate_file(path)
- add adapters for:
  - Python
  - JavaScript/TypeScript
- preserve file formatting where possible
- do not allow whole-file blind overwrite as the default path

Deliverables:
- edit tool
- validator interface
- language-specific validators
- tests for:
  - successful edit
  - rejected syntax-breaking edit
  - out-of-range line edits
  - unsupported file type

Cursor prompt for this task:
"Implement Task 3 only. Build a guarded edit tool that accepts file path plus start/end lines and replacement text, validates the file after the proposed edit, rejects invalid edits before persistence, and returns structured validation feedback."

---

# Phase 2 — Context Management

## Task 4 — Build compressed context memory

Implement the harness context manager.

Requirements:
- maintain full internal event history
- maintain active context window separately
- compress observations older than the last 5 turns into one-line summaries
- preserve:
  - recent actions
  - current repo state
  - recent file interactions
  - recent tool outputs
  - current objective
- expose current context packet to the agent runtime
- summaries should be deterministic and short

Behavior:
- turns 1..N-5 should be compressed
- last 5 turns remain detailed
- compressed memory should retain trajectory without flooding the prompt
- context manager should distinguish:
  - observations
  - actions
  - edits
  - verification results
  - git operations

Suggested model:
- raw history store
- compressed memory store
- active working context store

Deliverables:
- context manager service
- compression/summarization format
- tests for turn rollover behavior
- prompt-ready context serializer

Cursor prompt for this task:
"Implement Task 4 only. Build a context management system that preserves detailed memory for the last 5 turns and collapses older observations into concise one-line summaries while keeping the current objective and recent repo state clear."

---

# Phase 3 — Two-Agent Runtime Architecture

## Task 5 — Build the two-agent runtime skeleton

Implement the harness runtime for two agent roles:

1. Initializer Agent
2. Coding Agent

Requirements:
- each agent must have a distinct role definition
- each agent must have a distinct system prompt template
- initializer and coding agent should share tooling/runtime primitives but differ in permissions/objectives
- agent session state should be persisted in structured form
- initializer output should become inputs to later coding sessions

Behavior:
- initializer does environment scaffolding only
- coding agent does implementation/fixes only
- coding agent must consume initializer outputs rather than rediscovering them every session

Deliverables:
- agent role enum/types
- system prompt templates
- runtime session model
- initializer output contract
- coding agent input contract

Cursor prompt for this task:
"Implement Task 5 only. Build the runtime skeleton for a two-agent system with separate Initializer Agent and Coding Agent roles, separate prompt templates, and structured persisted outputs from the initializer for later coding sessions."

---

## Task 6 — Build initializer outputs: init.sh, feature list, git checkpoint protocol

Implement the Initializer Agent output system.

The initializer must produce 3 key outputs:

### A. init.sh
Requirements:
- generate a reliable bootstrap script for the repo
- script should start the local development/test environment reproducibly
- include:
  - dependency install
  - environment setup guidance
  - service start commands
  - test commands if known
- script should be safe and reviewable

### B. feature list JSON
Requirements:
- generate a comprehensive project feature/task ground-truth file
- stored as JSON
- every feature/task initially marked as failing or unverified
- examples:
  - "user can open a new chat"
  - "user can submit login form"
  - "dashboard loads with incident summaries"
- should model end-to-end product capabilities, not just code units
- include fields like:
  - id
  - feature_name
  - description
  - status
  - verification_method
  - last_verified_at
  - notes

Suggested filename:
- `.stimpactai/features.json`

### C. git checkpoint discipline
Requirements:
- initializer must create a baseline commit strategy
- define last-known-good checkpoint semantics
- provide helper operations for:
  - checkpoint
  - revert to checkpoint
  - reset failed attempt
- version control should be part of the runtime discipline, not optional

Deliverables:
- initializer output schema
- feature-list schema
- initial feature JSON generator
- git checkpoint helper layer
- tests for feature JSON validity and git helper behavior

Cursor prompt for this task:
"Implement Task 6 only. Build the Initializer Agent output system that creates init.sh, a comprehensive end-to-end features.json file with all features initially marked unverified or failing, and a git checkpoint/recovery helper layer."

---

# Phase 4 — Verification Discipline

## Task 7 — Build verification state model to prevent false completion

Implement a verification model so the future coding agent cannot mark work complete based only on partial validation.

Requirements:
- define verification states such as:
  - unverified
  - code_changed
  - unit_verified
  - integration_verified
  - browser_verified
  - fully_verified
  - failed_verification
- tasks/features should not be marked complete based only on:
  - passing unit test
  - passing curl call
  - static code inspection
- browser-level verification should be first-class in the model

Behavior:
- each feature/task must store:
  - what verification was attempted
  - what passed
  - what remains
- harness should be able to say:
  - "code compiles but browser verification still required"

Deliverables:
- verification status enums
- feature/task verification state schema
- rules engine preventing premature completion states

Cursor prompt for this task:
"Implement Task 7 only. Build a verification state model that prevents the agent from marking work complete unless the appropriate verification level has been reached, especially distinguishing code/unit verification from browser-level end-to-end verification."

---

## Task 8 — Build browser automation integration layer

Implement browser automation support for end-to-end verification.

Requirements:
- integrate a browser automation tool that the agent can use to:
  - open pages
  - click buttons
  - fill forms
  - submit actions
  - inspect rendered content
  - verify actual user-visible behavior
- support Puppeteer-first
- design the abstraction so Playwright could be added later if needed
- browser automation must be callable as a structured internal tool

Suggested tool capabilities:
- browser_open
- browser_click
- browser_type
- browser_wait_for
- browser_snapshot_dom
- browser_screenshot
- browser_get_url
- browser_assert_text

Deliverables:
- browser tool interface
- Puppeteer-backed implementation
- structured action/result schema
- local test page verification example

Cursor prompt for this task:
"Implement Task 8 only. Build a browser automation integration layer backed by Puppeteer so the future coding agent can verify application behavior through real browser interactions rather than relying only on code-level or API-level checks."

---

## Task 9 — Add Chrome DevTools Protocol-backed inspection tools

Implement CDP-style inspection utilities.

Requirements:
- support:
  - DOM snapshots
  - screenshots
  - browser navigation state capture
  - console error capture
  - network request summaries if feasible
- these tools should complement Puppeteer verification
- output should be structured and compact enough for agent consumption

Suggested tools:
- dom_snapshot
- take_screenshot
- capture_console_logs
- capture_network_summary
- current_page_state

Deliverables:
- inspection tool interfaces
- Puppeteer/CDP integration
- structured response models
- examples and tests

Cursor prompt for this task:
"Implement Task 9 only. Build CDP-backed browser inspection tools for DOM snapshots, screenshots, page state, and console capture so the agent can inspect what a user would actually see and what the browser is reporting."

---

# Phase 5 — Git Recovery and Safety

## Task 10 — Build git recovery helpers

Implement explicit git-based recovery primitives for the harness.

Requirements:
- helper functions for:
  - current branch info
  - create checkpoint commit
  - revert to last-known-good checkpoint
  - discard failed work safely
  - view diff since checkpoint
- git operations must be structured and agent-safe
- agent should not run raw destructive git commands directly

Behavior:
- checkpoint commits must be tagged/labeled clearly
- failed repair attempts should be recoverable quickly
- recovery should be deterministic

Deliverables:
- git_ops module
- structured git action result models
- tests or local integration checks

Cursor prompt for this task:
"Implement Task 10 only. Build safe structured git recovery helpers that let the future coding agent checkpoint known-good states, inspect diffs, and revert failed attempts without relying on raw shell git commands."

---

# Phase 6 — Profiles and Repo-Specific Behavior

## Task 11 — Build repo-specific harness profile support

Implement repo-level harness configuration.

Requirements:
- support a repo-local config file like:
  - `.stimpactai/profile.yml`
- profile should define:
  - install command
  - build command
  - test command
  - start command
  - browser verification entrypoints
  - environment assumptions
  - directories to ignore
  - file types/language hints
- harness must load and validate this profile before agent sessions

Deliverables:
- profile schema
- parser/validator
- default profile behavior
- sample profile docs

Cursor prompt for this task:
"Implement Task 11 only. Build repo-specific harness profile loading from .stimpactai/profile.yml so the runtime knows how to install, run, test, and verify the target project."

---

# Phase 7 — Orchestration Layer

## Task 12 — Build the harness session orchestrator

Implement the orchestration service that wires all harness pieces together.

Requirements:
- initialize session
- restore session state
- route tool calls
- provide prompt context
- persist context changes
- connect feature verification state to tool outputs
- connect git recovery system to coding sessions
- expose clean API entrypoints for future repair agent use

Suggested responsibilities:
- session lifecycle
- tool registry
- state persistence
- role-specific runtime setup
- current objective tracking

Deliverables:
- session orchestrator service
- tool registry
- runtime state model
- API/service entrypoints

Cursor prompt for this task:
"Implement Task 12 only. Build the main harness session orchestrator that manages tool access, context state, role-specific runtime behavior, feature verification state, and git recovery for future agent sessions."

---

# Phase 8 — End-to-End Harness Validation

## Task 13 — Build a harness self-test scenario

Implement one end-to-end harness validation scenario.

Requirements:
- use a small sample repo or test fixture
- run initializer phase
- generate init.sh
- generate features.json
- perform at least one safe edit
- run lint/syntax validation
- perform one browser verification flow
- update verification status correctly
- create and use a git checkpoint
- confirm context manager behavior

This is a proof that the harness works.

Deliverables:
- test fixture repo or fixture module
- end-to-end harness integration test
- documentation for running the self-test locally

Cursor prompt for this task:
"Implement Task 13 only. Build an end-to-end harness self-test that demonstrates initializer setup, feature list generation, guarded editing, browser verification, git checkpointing, and context management on a small test repo."

---

# Constraints and Guardrails

Cursor must follow these rules when implementing the harness:

- do not let the future agent use unrestricted shell output as its primary interface
- do not allow unsafe direct file overwrite flows by default
- do not allow features/tasks to be marked complete without browser-verification support in the model
- do not make git destructive operations available without a structured wrapper
- prefer typed schemas and deterministic tool outputs over loose text blobs

---

# Design Principles

The harness must prioritize:

- safety
- determinism
- recoverability
- verifiability
- compact context
- end-to-end realism over shallow test passing

The central philosophy is:

A coding agent should not operate like a raw shell bot.
It should operate inside a structured environment with bounded tools, compressed memory, git recovery, and browser-visible verification.

---

# Recommended Build Order Summary

1. Search/navigation tools
2. Stateful viewer
3. Guarded editor
4. Context manager
5. Two-agent runtime
6. Initializer outputs
7. Verification state model
8. Puppeteer integration
9. CDP inspection tools
10. Git recovery helpers
11. Repo profile support
12. Session orchestrator
13. Harness self-test

---

# Instruction To Cursor

At the start of each implementation session:
- read ARCHITECTURE.md
- read DEV_GUIDE.md
- read TASKS.md
- read this AGENT_HARNESS_TASKS.md
- work on exactly one task at a time
- list planned files before editing
- do not refactor unrelated modules
- preserve strong typed boundaries between runtime, tools, verification, context, and git layers