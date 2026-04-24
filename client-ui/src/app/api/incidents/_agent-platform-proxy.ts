import { NextRequest } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/auth-session";

export const AGENT_PLATFORM_API_URL =
  process.env.AGENT_PLATFORM_API_URL ?? "http://127.0.0.1:8000";

type ForwardHeaderOptions = {
  accept?: string;
  contentType?: string;
};

export function buildAgentPlatformForwardHeaders(
  request: NextRequest,
  options: ForwardHeaderOptions = {},
): Headers {
  const headers = new Headers();
  headers.set("Content-Type", options.contentType ?? "application/json");

  if (options.accept) {
    headers.set("Accept", options.accept);
  }

  const sessionToken = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (sessionToken) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  } else {
    const adminToken = process.env.AGENT_PLATFORM_ADMIN_TOKEN;
    if (adminToken) {
      headers.set("Authorization", `Bearer ${adminToken}`);
    }
  }

  const projectKey = request.headers.get("X-Stimpact-Project-Key");
  if (projectKey) {
    headers.set("X-Stimpact-Project-Key", projectKey);
  }

  return headers;
}
