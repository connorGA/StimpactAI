import { NextRequest, NextResponse } from "next/server";

import {
  AGENT_PLATFORM_API_URL,
  buildAgentPlatformForwardHeaders,
} from "../../_agent-platform-proxy";

type RouteContext = {
  params: Promise<{
    incidentId: string;
  }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;

  try {
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/${incidentId}/autonomous-runs`,
      {
        method: "GET",
        headers: buildAgentPlatformForwardHeaders(request),
        cache: "no-store",
      },
    );
    const payload = await response.text();
    return new Response(payload, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          message: "Unexpected autonomous run list proxy error.",
        },
      },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;

  try {
    const body = await request.text();
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/${incidentId}/autonomous-runs`,
      {
        method: "POST",
        headers: buildAgentPlatformForwardHeaders(request),
        body,
        cache: "no-store",
      },
    );
    const payload = await response.text();
    return new Response(payload, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          message: "Unexpected autonomous run create proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
