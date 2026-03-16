import "server-only";

import type {
  IncidentChatResponse,
  IncidentDetailResponse,
  IncidentListResponse,
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
