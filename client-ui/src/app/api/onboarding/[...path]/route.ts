import { NextRequest, NextResponse } from "next/server";

const AGENT_PLATFORM_API_URL =
  process.env.AGENT_PLATFORM_API_URL ?? "http://127.0.0.1:8000";

function buildForwardHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  headers.set("Content-Type", "application/json");

  const adminToken = process.env.AGENT_PLATFORM_ADMIN_TOKEN;
  if (adminToken) {
    headers.set("Authorization", `Bearer ${adminToken}`);
  }

  const projectKey = request.headers.get("X-Stimpact-Project-Key");
  if (projectKey) {
    headers.set("X-Stimpact-Project-Key", projectKey);
  }

  return headers;
}

async function proxyOnboardingRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const controlPlanePath = path.join("/");
  const targetUrl = new URL(
    `${AGENT_PLATFORM_API_URL}/control-plane/${controlPlanePath}`,
  );
  targetUrl.search = request.nextUrl.search;

  const init: RequestInit = {
    method: request.method,
    headers: buildForwardHeaders(request),
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const response = await fetch(targetUrl, init);
  const payload = await response.text();

  return new NextResponse(payload, {
    status: response.status,
    headers: {
      "Content-Type":
        response.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxyOnboardingRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxyOnboardingRequest(request, context);
}
