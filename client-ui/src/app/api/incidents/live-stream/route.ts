import { NextRequest, NextResponse } from "next/server";

import {
  AGENT_PLATFORM_API_URL,
  buildAgentPlatformForwardHeaders,
} from "../_agent-platform-proxy";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const projectId = searchParams.get("project_id");
  if (!projectId) {
    return NextResponse.json(
      {
        error: {
          message: "project_id is required.",
        },
      },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/live-stream?project_id=${encodeURIComponent(projectId)}`,
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
            message: "Incident live stream request failed.",
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
          message: "Unexpected incident live stream proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
