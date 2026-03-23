import "server-only";

import type {
  AutonomousRunQueuedResponse,
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
  ProjectApiKey,
  ProjectOnboarding,
  ProjectPolicy,
  ProviderIntegration,
  ProviderRepository,
  RepoProfile,
  SandboxRunQueuedResponse,
  SecretRef,
} from "@/lib/types";

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

async function fetchFromAgentPlatform<T>({
  path,
  headers,
  ...init
}: FetchOptions): Promise<T> {
  const response = await fetch(`${AGENT_PLATFORM_API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...headers,
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
    headers: buildControlPlaneHeaders(init?.headers),
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

export async function getHealthReadiness(): Promise<HealthReadiness> {
  return fetchFromAgentPlatform<HealthReadiness>({
    path: "/health/ready",
    method: "GET",
  });
}

export async function listProviderIntegrations(
  projectId?: string,
): Promise<ProviderIntegration[]> {
  const searchParams = new URLSearchParams();
  if (projectId) {
    searchParams.set("project_id", projectId);
  }
  const query = searchParams.toString();
  return fetchFromControlPlane<ProviderIntegration[]>(
    `/control-plane/provider-integrations${query ? `?${query}` : ""}`,
    { method: "GET" },
  );
}

export async function listRepoProfiles(projectId: string): Promise<RepoProfile[]> {
  return fetchFromControlPlane<RepoProfile[]>(
    `/control-plane/repo-profiles?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET" },
  );
}

export async function listSecretRefs(projectId: string): Promise<SecretRef[]> {
  return fetchFromControlPlane<SecretRef[]>(
    `/control-plane/secret-refs?project_id=${encodeURIComponent(projectId)}`,
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
