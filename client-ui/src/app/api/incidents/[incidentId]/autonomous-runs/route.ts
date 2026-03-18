import { NextResponse } from "next/server";

const AGENT_PLATFORM_API_URL =
  process.env.AGENT_PLATFORM_API_URL ?? "http://127.0.0.1:8000";

type RouteContext = {
  params: Promise<{
    incidentId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { incidentId } = await context.params;

  try {
    const body = await request.text();
    const response = await fetch(
      `${AGENT_PLATFORM_API_URL}/incidents/${incidentId}/autonomous-runs`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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
