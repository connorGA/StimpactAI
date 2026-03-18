import "server-only";

import type {
  IncidentClassification,
  IncidentChatResponse,
  IncidentDetailResponse,
  IncidentListResponse,
  IncidentPatch,
  IncidentRootCause,
  IncidentSandboxRunDetail,
  IncidentSandboxRun,
  SandboxRunQueuedResponse,
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
