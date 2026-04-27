import { NextRequest, NextResponse } from "next/server";

import {
  AGENT_PLATFORM_API_URL,
  buildAgentPlatformForwardHeaders,
} from "../../../../_agent-platform-proxy";

type RouteContext = {
  params: Promise<{
    incidentId: string;
    sandboxRunId: string;
  }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { incidentId, sandboxRunId } = await context.params;

  try {
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/${incidentId}/sandbox-runs/${sandboxRunId}/events`,
      {
        method: "GET",
        cache: "no-store",
        headers: buildAgentPlatformForwardHeaders(request, {
          accept: "text/event-stream",
        }),
      },
    );

    if (!response.ok || response.body === null) {
      return NextResponse.json(
        {
          error: {
            message: "Sandbox event stream request failed.",
          },
        },
        { status: response.status || 502 },
      );
    }

    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          message: "Unexpected sandbox event stream proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
