import { NextRequest, NextResponse } from "next/server";

import {
  AGENT_PLATFORM_API_URL,
  buildAgentPlatformForwardHeaders,
} from "../../../../_agent-platform-proxy";

type RouteContext = {
  params: Promise<{
    incidentId: string;
    runId: string;
  }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const { incidentId, runId } = await context.params;

  try {
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/${incidentId}/autonomous-runs/${runId}/promote`,
      {
        method: "POST",
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
          message: "Unexpected autonomous promotion proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
