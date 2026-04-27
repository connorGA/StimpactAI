import "server-only";

import { cookies } from "next/headers";

import type {
  AccessRequest,
  ApproveAccessRequestResponse,
  AutonomousRunQueuedResponse,
  AuthSession,
  CreateInviteResponse,
  GitLabOAuthStartResponse,
  HealthReadiness,
  IncidentClassification,
  IncidentAutonomousRunDetail,
  IncidentChatResponse,
  IncidentDetailResponse,
  IncidentListResponse,
  IncidentPatch,
  IncidentReportingOverview,
  IncidentRootCause,
  IncidentSandboxRunDetail,
  IncidentSandboxRun,
  OrganizationInvite,
  ProjectApiKey,
  ProjectApiKeyCreateResponse,
  ProjectBrowserKey,
  ProjectBrowserKeyCreateResponse,
  ProjectOnboarding,
  ProjectPolicy,
  ProjectSandboxPlanPreview,
  ProjectService,
  ProjectServiceRepairTarget,
  ProviderIntegration,
  ProviderRepository,
  ProjectSummary,
  EscalateNoiseFingerprintResponse,
  ReclassifyFingerprintResponse,
  RepoProfile,
  SandboxRunQueuedResponse,
  SecretRef,
  SuppressedFingerprintListResponse,
  SuppressionSummary,
  TelemetryClassification,
} from "@/lib/types";
import { SESSION_COOKIE_NAME } from "@/lib/auth-session";

const AGENT_PLATFORM_API_URL =
  process.env.AGENT_PLATFORM_API_URL ?? "http://127.0.0.1:8000";

export class AgentPlatformError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AgentPlatformError";
    this.status = status;
  }
}

type FetchOptions = RequestInit & {
  path: string;
};

function buildControlPlaneHeaders(headers?: HeadersInit): HeadersInit {
  const adminToken = process.env.AGENT_PLATFORM_ADMIN_TOKEN;
  if (!adminToken) {
    return headers ?? {};
  }
  return {
    Authorization: `Bearer ${adminToken}`,
    ...headers,
  };
}

async function buildAuthenticatedHeaders(headers?: HeadersInit): Promise<HeadersInit> {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  if (sessionToken) {
    return {
      Authorization: `Bearer ${sessionToken}`,
      ...headers,
    };
  }
  return buildControlPlaneHeaders(headers);
}

async function fetchFromAgentPlatform<T>({
  path,
  headers,
  ...init
}: FetchOptions): Promise<T> {
  const resolvedHeaders = await buildAuthenticatedHeaders(headers);
  const response = await fetch(`${AGENT_PLATFORM_API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...resolvedHeaders,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Agent Platform request failed with status ${response.status}.`;
    try {
      const payload = (await response.json()) as {
        error?: { message?: string };
      };
      if (payload.error?.message) {
        message = payload.error.message;
      }
    } catch {
      // Keep the default fallback message when the response body is not JSON.
    }
    throw new AgentPlatformError(message, response.status);
  }

  return (await response.json()) as T;
}

async function fetchFromControlPlane<T>(path: string, init?: RequestInit): Promise<T> {
  return fetchFromAgentPlatform<T>({
    path,
    ...init,
    headers: init?.headers,
  });
}

export async function getIncidents(params: {
  projectId?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<IncidentListResponse> {
  const searchParams = new URLSearchParams();
  if (params.projectId) {
    searchParams.set("project_id", params.projectId);
  }
  if (params.status) {
    searchParams.set("status", params.status);
  }
  if (params.limit) {
    searchParams.set("limit", String(params.limit));
  }
  if (params.offset) {
    searchParams.set("offset", String(params.offset));
  }

  const query = searchParams.toString();
  return fetchFromAgentPlatform<IncidentListResponse>({
    path: `/incidents${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentReportingOverview(
  projectId?: string,
): Promise<IncidentReportingOverview> {
  const searchParams = new URLSearchParams();
  if (projectId) {
    searchParams.set("project_id", projectId);
  }
  const query = searchParams.toString();
  return fetchFromAgentPlatform<IncidentReportingOverview>({
    path: `/incidents/reporting/overview${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncident(
  incidentId: string,
  options?: { eventLimit?: number },
): Promise<IncidentDetailResponse> {
  const searchParams = new URLSearchParams();
  if (options?.eventLimit) {
    searchParams.set("event_limit", String(options.eventLimit));
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<IncidentDetailResponse>({
    path: `/incidents/${incidentId}${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentClassification(
  incidentId: string,
  options?: { eventLimit?: number },
): Promise<IncidentClassification> {
  const searchParams = new URLSearchParams();
  if (options?.eventLimit) {
    searchParams.set("event_limit", String(options.eventLimit));
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<IncidentClassification>({
    path: `/incidents/${incidentId}/classification${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentRootCause(
  incidentId: string,
  options?: { eventLimit?: number },
): Promise<IncidentRootCause> {
  const searchParams = new URLSearchParams();
  if (options?.eventLimit) {
    searchParams.set("event_limit", String(options.eventLimit));
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<IncidentRootCause>({
    path: `/incidents/${incidentId}/root-cause${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentPatch(
  incidentId: string,
  options?: { eventLimit?: number; refresh?: boolean },
): Promise<IncidentPatch> {
  const searchParams = new URLSearchParams();
  if (options?.eventLimit) {
    searchParams.set("event_limit", String(options.eventLimit));
  }
  if (options?.refresh) {
    searchParams.set("refresh", "true");
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<IncidentPatch>({
    path: `/incidents/${incidentId}/patch${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentSandboxRun(
  incidentId: string,
): Promise<IncidentSandboxRun> {
  return fetchFromAgentPlatform<IncidentSandboxRun>({
    path: `/incidents/${incidentId}/sandbox-run`,
    method: "GET",
  });
}

export async function listIncidentSandboxRuns(
  incidentId: string,
  options?: { limit?: number },
): Promise<IncidentSandboxRun[]> {
  const searchParams = new URLSearchParams();
  if (options?.limit) {
    searchParams.set("limit", String(options.limit));
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<IncidentSandboxRun[]>({
    path: `/incidents/${incidentId}/sandbox-runs${query ? `?${query}` : ""}`,
    method: "GET",
  });
}

export async function getIncidentSandboxRunDetail(
  incidentId: string,
  sandboxRunId: string,
): Promise<IncidentSandboxRunDetail> {
  return fetchFromAgentPlatform<IncidentSandboxRunDetail>({
    path: `/incidents/${incidentId}/sandbox-runs/${sandboxRunId}`,
    method: "GET",
  });
}

export async function listIncidentAutonomousRuns(
  incidentId: string,
): Promise<IncidentAutonomousRunDetail["run"][]> {
  return fetchFromAgentPlatform<IncidentAutonomousRunDetail["run"][]>({
    path: `/incidents/${incidentId}/autonomous-runs`,
    method: "GET",
  });
}

export async function getLatestIncidentAutonomousRunDetail(
  incidentId: string,
): Promise<IncidentAutonomousRunDetail> {
  return fetchFromAgentPlatform<IncidentAutonomousRunDetail>({
    path: `/incidents/${incidentId}/autonomous-runs/latest`,
    method: "GET",
  });
}

export async function createIncidentAutonomousRun(
  incidentId: string,
  body: unknown,
): Promise<AutonomousRunQueuedResponse> {
  return fetchFromAgentPlatform<AutonomousRunQueuedResponse>({
    path: `/incidents/${incidentId}/autonomous-runs`,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function runIncidentSandbox(
  incidentId: string,
  options?: { eventLimit?: number; refreshPatch?: boolean },
): Promise<SandboxRunQueuedResponse> {
  const searchParams = new URLSearchParams();
  if (options?.eventLimit) {
    searchParams.set("event_limit", String(options.eventLimit));
  }
  if (options?.refreshPatch) {
    searchParams.set("refresh_patch", "true");
  }
  const query = searchParams.toString();

  return fetchFromAgentPlatform<SandboxRunQueuedResponse>({
    path: `/incidents/${incidentId}/sandbox-runs${query ? `?${query}` : ""}`,
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function createGlobalIncidentChat(body: unknown): Promise<IncidentChatResponse> {
  return fetchFromAgentPlatform<IncidentChatResponse>({
    path: "/incidents/chat",
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createIncidentDetailChat(
  incidentId: string,
  body: unknown,
): Promise<IncidentChatResponse> {
  return fetchFromAgentPlatform<IncidentChatResponse>({
    path: `/incidents/${incidentId}/chat`,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listSuppressedTelemetry(
  projectId: string,
  options?: { limit?: number },
): Promise<SuppressedFingerprintListResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  return fetchFromAgentPlatform<SuppressedFingerprintListResponse>({
    path: `/incidents/noise?${params.toString()}`,
    method: "GET",
  });
}

export async function getSuppressionSummary(
  projectId: string,
  options?: { windowMinutes?: number },
): Promise<SuppressionSummary> {
  const params = new URLSearchParams({ project_id: projectId });
  if (options?.windowMinutes) {
    params.set("window_minutes", String(options.windowMinutes));
  }
  return fetchFromAgentPlatform<SuppressionSummary>({
    path: `/incidents/noise/summary?${params.toString()}`,
    method: "GET",
  });
}

export async function reclassifyFingerprint(input: {
  projectId: string;
  fingerprint: string;
  classification: TelemetryClassification;
  reason?: string;
}): Promise<ReclassifyFingerprintResponse> {
  return fetchFromAgentPlatform<ReclassifyFingerprintResponse>({
    path: `/incidents/noise/${encodeURIComponent(input.fingerprint)}/reclassify`,
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId,
      classification: input.classification,
      reason: input.reason ?? null,
    }),
  });
}

export async function escalateNoiseFingerprint(input: {
  projectId: string;
  fingerprint: string;
  reason?: string;
}): Promise<EscalateNoiseFingerprintResponse> {
  return fetchFromAgentPlatform<EscalateNoiseFingerprintResponse>({
    path: `/incidents/noise/${encodeURIComponent(input.fingerprint)}/escalate`,
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId,
      reason: input.reason ?? null,
    }),
  });
}

export async function getHealthReadiness(): Promise<HealthReadiness> {
  return fetchFromAgentPlatform<HealthReadiness>({
    path: "/health/ready",
    method: "GET",
  });
}

export async function listProviderIntegrations(
  projectId?: string,
): Promise<ProviderIntegration[]> {
  if (projectId) {
    return fetchFromControlPlane<ProviderIntegration[]>(
      `/control-plane/projects/${encodeURIComponent(projectId)}/provider-integrations`,
      { method: "GET" },
    );
  }
  return fetchFromControlPlane<ProviderIntegration[]>(
    "/control-plane/provider-integrations",
    { method: "GET" },
  );
}

export async function listRepoProfiles(projectId: string): Promise<RepoProfile[]> {
  return fetchFromControlPlane<RepoProfile[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/repo-profiles`,
    { method: "GET" },
  );
}

export async function listProjectServices(projectId: string): Promise<ProjectService[]> {
  return fetchFromControlPlane<ProjectService[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/services`,
    { method: "GET" },
  );
}

export async function listSecretRefs(projectId: string): Promise<SecretRef[]> {
  return fetchFromControlPlane<SecretRef[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/secret-refs`,
    { method: "GET" },
  );
}

export async function getProjectPolicy(projectId: string): Promise<ProjectPolicy> {
  return fetchFromControlPlane<ProjectPolicy>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/policy`,
    { method: "GET" },
  );
}

export async function listProjectApiKeys(projectId: string): Promise<ProjectApiKey[]> {
  return fetchFromControlPlane<ProjectApiKey[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/api-keys`,
    { method: "GET" },
  );
}

export async function createProjectApiKey(
  projectId: string,
  body: { name: string },
): Promise<ProjectApiKeyCreateResponse> {
  return fetchFromControlPlane<ProjectApiKeyCreateResponse>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/api-keys`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function listProjectBrowserKeys(projectId: string): Promise<ProjectBrowserKey[]> {
  return fetchFromControlPlane<ProjectBrowserKey[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/browser-keys`,
    { method: "GET" },
  );
}

export async function createProjectBrowserKey(
  projectId: string,
  body: { name: string; allowed_origins: string[] },
): Promise<ProjectBrowserKeyCreateResponse> {
  return fetchFromControlPlane<ProjectBrowserKeyCreateResponse>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/browser-keys`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function updateProjectBrowserKey(
  projectId: string,
  keyId: string,
  body: { allowed_origins: string[] },
): Promise<ProjectBrowserKey> {
  return fetchFromControlPlane<ProjectBrowserKey>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/browser-keys/${encodeURIComponent(keyId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export async function revokeProjectBrowserKey(
  projectId: string,
  keyId: string,
): Promise<ProjectBrowserKey> {
  return fetchFromControlPlane<ProjectBrowserKey>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/browser-keys/${encodeURIComponent(keyId)}/revoke`,
    {
      method: "POST",
    },
  );
}

export async function revokeProjectApiKey(
  projectId: string,
  keyId: string,
): Promise<ProjectApiKey> {
  return fetchFromControlPlane<ProjectApiKey>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(keyId)}/revoke`,
    {
      method: "POST",
    },
  );
}

export async function updateProjectPolicy(
  projectId: string,
  body: ProjectPolicy,
): Promise<ProjectPolicy> {
  return fetchFromControlPlane<ProjectPolicy>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/policy`,
    {
      method: "PUT",
      body: JSON.stringify({
        autonomy_mode: body.autonomy_mode,
        require_human_approval: body.require_human_approval,
        allow_production_writes: body.allow_production_writes,
        allow_low_risk_autonomy: body.allow_low_risk_autonomy,
        block_during_active_deploys: body.block_during_active_deploys,
        restrict_to_approved_services: body.restrict_to_approved_services,
        require_rollback_plan: body.require_rollback_plan,
        require_post_action_verification: body.require_post_action_verification,
        approved_services: body.approved_services,
        failure_classifier_enabled: body.failure_classifier_enabled,
        root_cause_enabled: body.root_cause_enabled,
        patch_planner_enabled: body.patch_planner_enabled,
        runbook_executor_enabled: body.runbook_executor_enabled,
      }),
    },
  );
}

export async function bootstrapProjectOnboarding(
  projectId: string,
): Promise<ProjectOnboarding> {
  return fetchFromControlPlane<ProjectOnboarding>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/bootstrap`,
    { method: "POST" },
  );
}

export async function getProjectOnboarding(
  projectId: string,
): Promise<ProjectOnboarding> {
  return fetchFromControlPlane<ProjectOnboarding>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/onboarding`,
    { method: "GET" },
  );
}

export async function createProjectSecretRef(
  projectId: string,
  body: {
    project_id: string;
    label: string;
    description?: string | null;
    value: string;
  },
): Promise<SecretRef> {
  return fetchFromControlPlane<SecretRef>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/secret-refs`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function createProjectGitHubIntegration(
  projectId: string,
  body: {
    project_id: string;
    name: string;
    installation_id?: string;
  },
): Promise<ProviderIntegration> {
  return fetchFromControlPlane<ProviderIntegration>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/provider-integrations/github-app`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function startProjectGitLabOAuth(
  projectId: string,
  body: {
    project_id: string;
    name: string;
    gitlab_base_url?: string;
  },
): Promise<GitLabOAuthStartResponse> {
  return fetchFromControlPlane<GitLabOAuthStartResponse>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/provider-integrations/gitlab/oauth/start`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function syncProjectProviderRepositories(
  projectId: string,
  providerIntegrationId: string,
): Promise<{
  integration: ProviderIntegration;
  repositories: ProviderRepository[];
}> {
  return fetchFromControlPlane<{
    integration: ProviderIntegration;
    repositories: ProviderRepository[];
  }>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/provider-integrations/${encodeURIComponent(providerIntegrationId)}/repositories/sync`,
    {
      method: "POST",
    },
  );
}

export async function listProjectProviderRepositories(
  projectId: string,
  providerIntegrationId: string,
): Promise<ProviderRepository[]> {
  return fetchFromControlPlane<ProviderRepository[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/provider-integrations/${encodeURIComponent(providerIntegrationId)}/repositories`,
    {
      method: "GET",
    },
  );
}

export async function createProjectRepoProfile(
  projectId: string,
  body: {
    project_id: string;
    provider_repository_id: string;
    runtime_kind: "generic" | "python" | "node" | "container";
    base_image?: string | null;
    install_command?: string | null;
    startup_commands?: string[];
    reproduce_command: string;
    verify_command: string;
    success_criteria?: string | null;
    network_allowlist?: string[];
    secret_mounts?: Array<{ secret_ref_id: string; mount_as: string }>;
  },
): Promise<RepoProfile> {
  return fetchFromControlPlane<RepoProfile>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/repo-profiles`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function createProjectService(
  projectId: string,
  body: {
    project_id: string;
    name: string;
    slug: string;
    service_type:
      | "frontend"
      | "backend"
      | "fullstack"
      | "api"
      | "worker"
      | "cron"
      | "gateway"
      | "database"
      | "cache"
      | "other";
    repo_profile_id?: string | null;
    owner?: string | null;
    deploy_target?: string | null;
    tracked_branch?: string | null;
    routing_hints?: {
      service_names?: string[];
      path_prefixes?: string[];
      domains?: string[];
      tags?: string[];
    };
    startup_priority?: number;
    sandbox_healthcheck_command?: string | null;
    sandbox_healthcheck_url?: string | null;
    active?: boolean;
    dependencies?: Array<{
      depends_on_service_id: string;
      dependency_kind: "required" | "optional" | "mock";
    }>;
  },
): Promise<ProjectService> {
  return fetchFromControlPlane<ProjectService>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/services`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function updateProjectService(
  projectId: string,
  serviceId: string,
  body: {
    name: string;
    slug: string;
    service_type:
      | "frontend"
      | "backend"
      | "fullstack"
      | "api"
      | "worker"
      | "cron"
      | "gateway"
      | "database"
      | "cache"
      | "other";
    repo_profile_id?: string | null;
    owner?: string | null;
    deploy_target?: string | null;
    tracked_branch?: string | null;
    routing_hints?: {
      service_names?: string[];
      path_prefixes?: string[];
      domains?: string[];
      tags?: string[];
    };
    startup_priority?: number;
    sandbox_healthcheck_command?: string | null;
    sandbox_healthcheck_url?: string | null;
    active?: boolean;
    dependencies?: Array<{
      depends_on_service_id: string;
      dependency_kind: "required" | "optional" | "mock";
    }>;
  },
): Promise<ProjectService> {
  return fetchFromControlPlane<ProjectService>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(serviceId)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

export async function listProjectRepairTargets(projectId: string): Promise<ProjectServiceRepairTarget[]> {
  return fetchFromControlPlane<ProjectServiceRepairTarget[]>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/repair-targets`,
    {
      method: "GET",
    },
  );
}

export async function getProjectServiceRepairTarget(
  projectId: string,
  serviceId: string,
  branchLimit = 20,
): Promise<ProjectServiceRepairTarget> {
  return fetchFromControlPlane<ProjectServiceRepairTarget>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(serviceId)}/repair-target?branch_limit=${encodeURIComponent(String(branchLimit))}`,
    {
      method: "GET",
    },
  );
}

export async function getProjectServiceSandboxPlan(
  projectId: string,
  serviceId: string,
): Promise<ProjectSandboxPlanPreview> {
  return fetchFromControlPlane<ProjectSandboxPlanPreview>(
    `/control-plane/projects/${encodeURIComponent(projectId)}/services/${encodeURIComponent(serviceId)}/sandbox-plan`,
    {
      method: "GET",
    },
  );
}

export async function loginWithPassword(body: {
  email: string;
  password: string;
}): Promise<AuthSession> {
  return fetchFromAgentPlatform<AuthSession>({
    path: "/auth/login",
    method: "POST",
    body: JSON.stringify(body),
    headers: {},
  });
}

export async function signupWorkspace(body: {
  plan: "basic" | "growth" | "scale";
  organization_name: string;
  organization_slug: string;
  full_name: string;
  email: string;
  password: string;
}): Promise<AuthSession> {
  return fetchFromAgentPlatform<AuthSession>({
    path: "/auth/signup",
    method: "POST",
    body: JSON.stringify(body),
    headers: {},
  });
}

export async function acceptWorkspaceInvite(body: {
  invite_token: string;
  full_name: string;
  password: string;
}): Promise<AuthSession> {
  return fetchFromAgentPlatform<AuthSession>({
    path: "/auth/accept-invite",
    method: "POST",
    body: JSON.stringify(body),
    headers: {},
  });
}

export async function getCurrentSession(): Promise<AuthSession> {
  return fetchFromAgentPlatform<AuthSession>({
    path: "/auth/me",
    method: "GET",
  });
}

export async function createAccessRequest(body: {
  organization_slug: string;
  full_name: string;
  email: string;
}): Promise<AccessRequest> {
  return fetchFromAgentPlatform<AccessRequest>({
    path: "/auth/access-requests",
    method: "POST",
    body: JSON.stringify(body),
    headers: {},
  });
}

export async function createWorkspaceProject(body: {
  name: string;
  slug: string;
}): Promise<ProjectSummary> {
  return fetchFromAgentPlatform<ProjectSummary>({
    path: "/auth/projects",
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listWorkspaceInvites(
  organizationId: string,
): Promise<OrganizationInvite[]> {
  return fetchFromAgentPlatform<OrganizationInvite[]>({
    path: `/auth/organizations/${encodeURIComponent(organizationId)}/invites`,
    method: "GET",
  });
}

export async function createWorkspaceInvite(
  organizationId: string,
  body: { email: string; role: "owner" | "admin" | "member" },
): Promise<CreateInviteResponse> {
  return fetchFromAgentPlatform<CreateInviteResponse>({
    path: `/auth/organizations/${encodeURIComponent(organizationId)}/invites`,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listWorkspaceAccessRequests(
  organizationId: string,
): Promise<AccessRequest[]> {
  return fetchFromAgentPlatform<AccessRequest[]>({
    path: `/auth/organizations/${encodeURIComponent(organizationId)}/access-requests`,
    method: "GET",
  });
}

export async function approveWorkspaceAccessRequest(
  organizationId: string,
  accessRequestId: string,
  body: { role: "owner" | "admin" | "member" },
): Promise<ApproveAccessRequestResponse> {
  return fetchFromAgentPlatform<ApproveAccessRequestResponse>({
    path: `/auth/organizations/${encodeURIComponent(organizationId)}/access-requests/${encodeURIComponent(accessRequestId)}/approve`,
    method: "POST",
    body: JSON.stringify(body),
  });
}
