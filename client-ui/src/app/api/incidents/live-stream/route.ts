import { NextResponse } from "next/server";

const AGENT_PLATFORM_API_URL =
  process.env.AGENT_PLATFORM_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
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
        headers: {
          Accept: "text/event-stream",
        },
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
