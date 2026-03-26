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

export type IncidentCountBreakdown = {
  label: string;
  count: number;
};

export type IncidentActivityPoint = {
  label: string;
  count: number;
};

export type IncidentReportingOverview = {
  project_id: string | null;
  total_visible_incidents: number;
  open_incidents: number;
  critical_incidents: number;
  total_event_volume: number;
  latest_incident_at: string | null;
  service_counts: IncidentCountBreakdown[];
  environment_counts: IncidentCountBreakdown[];
  severity_counts: IncidentCountBreakdown[];
  recent_incident_activity: IncidentActivityPoint[];
  daily_incident_activity: IncidentActivityPoint[];
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
  repo_profile_id: string | null;
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

export type AutonomousExecutionMode =
  | "investigate_only"
  | "repair_only"
  | "repair_and_propose";

export type AutonomousApprovalStatus =
  | "not_required"
  | "pending"
  | "approved"
  | "rejected";

export type AutonomousPromotionStatus =
  | "not_requested"
  | "ready"
  | "proposed"
  | "blocked";

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

export type AutonomousPolicyDecision = {
  auto_run_allowed: boolean;
  requires_human_approval: boolean;
  allow_writeback: boolean;
  allowed_execution_backends: string[];
  allowed_tool_categories: string[];
  require_browser_verification: boolean;
  max_repair_attempts: number;
  max_retry_budget: number;
  reasons: string[];
};

export type AutonomousRun = {
  id: string;
  incident_id: string | null;
  async_job_id: string | null;
  repo_profile_id: string | null;
  patch_run_id: string | null;
  sandbox_run_id: string | null;
  promotion_branch_name: string | null;
  promotion_url: string | null;
  repository_root: string;
  objective: string;
  status: AutonomousRunStatus;
  phase: AutonomousRunPhase;
  execution_mode: AutonomousExecutionMode;
  approval_status: AutonomousApprovalStatus;
  promotion_status: AutonomousPromotionStatus;
  initializer_session_id: string | null;
  coding_session_id: string | null;
  last_error: string | null;
  policy: AutonomousPolicyDecision;
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
  execution_mode: AutonomousExecutionMode;
  approval_status: AutonomousApprovalStatus;
  promotion_status: AutonomousPromotionStatus;
  checkpoint_ref: string | null;
  recovery_attempts: number;
  total_steps: number;
  total_decisions: number;
  total_tool_calls: number;
  total_events: number;
  last_error: string | null;
  policy: AutonomousPolicyDecision;
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
  async_job_id: string | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type IncidentChatResponse = {
  answer: string;
  referenced_incident_ids: string[];
};

export type AutonomyMode =
  | "observe"
  | "recommend"
  | "supervised_execute"
  | "autonomous";

export type ProjectPolicy = {
  project_id: string;
  autonomy_mode: AutonomyMode;
  require_human_approval: boolean;
  allow_production_writes: boolean;
  allow_low_risk_autonomy: boolean;
  block_during_active_deploys: boolean;
  restrict_to_approved_services: boolean;
  require_rollback_plan: boolean;
  require_post_action_verification: boolean;
  approved_services: string[];
  failure_classifier_enabled: boolean;
  root_cause_enabled: boolean;
  patch_planner_enabled: boolean;
  runbook_executor_enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectApiKey = {
  id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  status: "active" | "revoked";
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectApiKeyCreateResponse = {
  api_key: ProjectApiKey;
  plaintext_key: string;
};

export type ProviderIntegration = {
  id: string;
  provider: "github" | "gitlab";
  name: string;
  status: "active" | "disabled";
  credentials_secret_ref_id: string | null;
  webhook_secret_ref_id: string | null;
  aws_region: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ProviderRepository = {
  id: string;
  provider_integration_id: string;
  provider: "github" | "gitlab";
  external_repository_id: string;
  owner: string;
  name: string;
  default_branch: string;
  clone_url: string;
  created_at: string;
  updated_at: string;
};

export type ProviderIntegrationOnboarding = {
  integration: ProviderIntegration;
  repositories: ProviderRepository[];
};

export type GitLabOAuthStartResponse = {
  integration: ProviderIntegration;
  authorization_url: string;
};

export type SecretRef = {
  id: string;
  project_id: string;
  label: string;
  description: string | null;
  backend: "aws_secrets_manager";
  external_ref: string;
  created_at: string;
  updated_at: string;
};

export type RepoProfileSecretMount = {
  mount_as: string;
  secret_ref: SecretRef;
};

export type RepoProfile = {
  id: string;
  project_id: string;
  provider_repository_id: string;
  runtime_kind: "generic" | "python" | "node" | "container";
  base_image: string | null;
  install_command: string | null;
  startup_commands: string[];
  reproduce_command: string;
  verify_command: string;
  success_criteria: string | null;
  network_allowlist: string[];
  secret_refs: SecretRef[];
  secret_mounts: RepoProfileSecretMount[];
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectServiceType =
  | "frontend"
  | "backend"
  | "api"
  | "worker"
  | "cron"
  | "gateway"
  | "database"
  | "cache"
  | "other";

export type ProjectServiceDependencyKind = "required" | "optional" | "mock";

export type ProjectServiceRoutingHints = {
  service_names: string[];
  path_prefixes: string[];
  domains: string[];
  tags: string[];
};

export type ProjectServiceDependency = {
  depends_on_service_id: string;
  dependency_kind: ProjectServiceDependencyKind;
};

export type ProjectService = {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  service_type: ProjectServiceType;
  repo_profile_id: string | null;
  owner: string | null;
  deploy_target: string | null;
  routing_hints: ProjectServiceRoutingHints;
  startup_priority: number;
  sandbox_healthcheck_command: string | null;
  sandbox_healthcheck_url: string | null;
  active: boolean;
  dependencies: ProjectServiceDependency[];
  created_at: string;
  updated_at: string;
};

export type SandboxPlanService = {
  service: ProjectService;
  repo_profile: RepoProfile | null;
  startup_commands: string[];
  healthcheck_command: string | null;
  healthcheck_url: string | null;
};

export type ProjectSandboxPlanPreview = {
  project_id: string;
  target_service: SandboxPlanService;
  dependency_services: SandboxPlanService[];
  warnings: string[];
};

export type HealthReadiness = {
  status: string;
  checks: {
    database: {
      configured: boolean;
      ready: boolean;
    };
  };
};

export type ProjectOnboarding = {
  project_id: string;
  policy: ProjectPolicy;
  secret_refs: SecretRef[];
  api_keys: ProjectApiKey[];
  integrations: ProviderIntegrationOnboarding[];
  repo_profiles: RepoProfile[];
  project_services: ProjectService[];
  suggested_next_steps: string[];
};

export type SubscriptionPlan = "basic" | "growth" | "scale";
export type MembershipRole = "owner" | "admin" | "member";

export type UserSummary = {
  id: string;
  email: string;
  full_name: string;
  email_verified_at: string | null;
  created_at: string;
  updated_at: string;
};

export type OrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export type OrganizationMembershipSummary = {
  organization: OrganizationSummary;
  role: MembershipRole;
};

export type ProjectSummary = {
  id: string;
  organization_id: string;
  slug: string;
  name: string;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type SubscriptionSummary = {
  id: string;
  organization_id: string;
  plan: SubscriptionPlan;
  status: "trialing" | "active" | "past_due" | "canceled";
  included_projects: number;
  additional_project_price_cents: number;
  seat_policy: "unlimited";
  created_at: string;
  updated_at: string;
};

export type AuthSession = {
  access_token: string;
  user: UserSummary;
  organization: OrganizationSummary;
  role: MembershipRole;
  memberships: OrganizationMembershipSummary[];
  projects: ProjectSummary[];
  subscription: SubscriptionSummary | null;
};

export type OrganizationInvite = {
  id: string;
  organization_id: string;
  email: string;
  role: MembershipRole;
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AccessRequest = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  status: "pending" | "approved" | "rejected";
  reviewed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateInviteResponse = {
  invite: OrganizationInvite;
  invite_token: string;
};

export type ApproveAccessRequestResponse = {
  access_request: AccessRequest;
  invite: OrganizationInvite;
  invite_token: string;
};
