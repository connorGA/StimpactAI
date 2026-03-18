export type IncidentStatus = "open" | "resolved";
export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type Environment = "production" | "staging" | "development" | "test";
export type FailureCategory =
  | "application_bug"
  | "authorization_failure"
  | "configuration_error"
  | "database_failure"
  | "dependency_failure"
  | "network_failure"
  | "null_reference"
  | "resource_exhaustion"
  | "timeout"
  | "validation_failure"
  | "unknown";

export type IncidentSummary = {
  id: string;
  project_id: string;
  fingerprint: string;
  service: string;
  environment: Environment;
  title: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  first_seen_at: string;
  last_seen_at: string;
  event_count: number;
  latest_telemetry_id: string;
  created_at: string;
  updated_at: string;
};

export type IncidentEvent = {
  id: string;
  telemetry_id: string;
  event_type: string;
  error_message: string;
  stacktrace: string;
  request_payload: unknown;
  response_payload: unknown;
  payload: unknown;
  occurred_at: string;
  created_at: string;
};

export type IncidentListResponse = {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type IncidentDetailResponse = {
  incident: IncidentSummary;
  events: IncidentEvent[];
};

export type IncidentClassification = {
  incident_id: string;
  category: FailureCategory;
  confidence: number;
  summary: string;
  matched_signals: string[];
  inspected_event_count: number;
};

export type CodeCandidate = {
  file_path: string;
  symbol: string | null;
  match_reason: string;
  matched_terms: string[];
  confidence: number;
};

export type GitSignal = {
  file_path: string;
  commit_sha: string;
  commit_summary: string;
  committed_at: string | null;
  relevance_reason: string;
};

export type CodeSnippet = {
  file_path: string;
  symbol: string | null;
  start_line: number;
  end_line: number;
  content: string;
  match_reason: string;
  confidence: number;
};

export type RootCauseEvidence = {
  suspected_component: string | null;
  evidence_summary: string;
  stack_trace_signals: string[];
  search_terms: string[];
  code_candidates: CodeCandidate[];
  code_snippets: CodeSnippet[];
  git_signals: GitSignal[];
  evidence_confidence: number;
  latest_commit_sha: string | null;
  inspected_event_count: number;
};

export type RootCauseReasoning = {
  root_cause_hypothesis: string;
  reasoning_summary: string;
  alternative_hypotheses: string[];
  confidence: number;
};

export type IncidentRootCause = {
  incident_id: string;
  category: FailureCategory;
  category_summary: string;
  category_confidence: number;
  evidence: RootCauseEvidence;
  reasoning: RootCauseReasoning;
};

export type PatchRunStatus = "generated" | "failed";

export type PatchTargetFile = {
  path: string;
  reason: string;
};

export type IncidentPatch = {
  id: string;
  incident_id: string;
  status: PatchRunStatus;
  patch_summary: string;
  rationale: string;
  target_files: PatchTargetFile[];
  unified_diff: string;
  verification_steps: string[];
  confidence: number;
  model_name: string;
  based_on_commit_sha: string | null;
  diff_line_count: number;
  file_count: number;
  created_at: string;
  updated_at: string;
};

export type SandboxRunStatus = "queued" | "running" | "succeeded" | "failed";

export type IncidentSandboxRun = {
  id: string;
  incident_id: string;
  patch_run_id: string;
  repo_profile_id: string | null;
  async_job_id: string | null;
  status: SandboxRunStatus;
  executor_backend: string;
  external_job_id: string | null;
  install_command: string | null;
  reproduce_command: string;
  verify_command: string;
  reproduction_succeeded: boolean;
  patch_applied: boolean;
  verification_succeeded: boolean;
  summary: string;
  execution_log: string;
  created_at: string;
  updated_at: string;
};

export type SandboxRunStep = {
  id: string;
  sandbox_run_id: string;
  step_name: string;
  status: SandboxRunStatus;
  command: string | null;
  summary: string;
  artifact_id: string | null;
  exit_code: number | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
};

export type SandboxRunAttempt = {
  id: string;
  sandbox_run_id: string;
  async_job_id: string | null;
  attempt_number: number;
  status: SandboxRunStatus;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
};

export type Artifact = {
  id: string;
  incident_id: string | null;
  patch_run_id: string | null;
  sandbox_run_id: string | null;
  artifact_type: string;
  storage_backend: string;
  bucket_name: string;
  object_key: string;
  uri: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string | null;
  created_at: string;
  updated_at: string;
};

export type SandboxRunQueuedResponse = {
  sandbox_run: IncidentSandboxRun;
  async_job_id: string;
  async_job_status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
};

export type IncidentSandboxRunDetail = {
  run: IncidentSandboxRun;
  steps: SandboxRunStep[];
  attempts: SandboxRunAttempt[];
  artifacts: Artifact[];
};

export type AutonomousRunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AutonomousRunPhase =
  | "initializer"
  | "coding"
  | "verification"
  | "recovery"
  | "completed"
  | "failed";

export type AutonomousDecisionAction = "invoke_tool" | "complete" | "fail";

export type AutonomousDecision = {
  summary: string;
  rationale: string | null;
  action: AutonomousDecisionAction;
  selected_tool: string | null;
  arguments: Record<string, unknown>;
  arguments_summary: string | null;
  feature_id: string | null;
  verification_kind: string | null;
};

export type AutonomousLoopState = {
  step_index: number;
  max_steps: number;
  checkpoint_ref: string | null;
  recovery_attempts: number;
  consecutive_failures: number;
  last_tool_name: string | null;
  recent_tool_names: string[];
  last_tool_ok: boolean | null;
  last_tool_result: Record<string, unknown>;
};

export type AutonomousRun = {
  id: string;
  incident_id: string | null;
  repository_root: string;
  objective: string;
  status: AutonomousRunStatus;
  phase: AutonomousRunPhase;
  initializer_session_id: string | null;
  coding_session_id: string | null;
  last_error: string | null;
  loop_state: AutonomousLoopState;
  created_at: string;
  updated_at: string;
};

export type AutonomousRunEvent = {
  id: string;
  run_id: string;
  event_type: string;
  phase: AutonomousRunPhase;
  summary: string;
  decision: AutonomousDecision | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AutonomousRunOutcome = {
  run_id: string;
  incident_id: string | null;
  status: AutonomousRunStatus;
  phase: AutonomousRunPhase;
  objective: string;
  repository_root: string;
  checkpoint_ref: string | null;
  recovery_attempts: number;
  total_steps: number;
  total_decisions: number;
  total_tool_calls: number;
  total_events: number;
  last_error: string | null;
  created_at: string;
  completed_at: string;
};

export type AutonomousArtifactPaths = {
  snapshot_path: string;
  events_path: string;
  outcome_path: string | null;
};

export type IncidentAutonomousRunDetail = {
  run: AutonomousRun;
  events: AutonomousRunEvent[];
  outcome: AutonomousRunOutcome | null;
  artifact_paths: AutonomousArtifactPaths;
};

export type AutonomousRunQueuedResponse = {
  run: AutonomousRun;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type IncidentChatResponse = {
  answer: string;
  referenced_incident_ids: string[];
};
