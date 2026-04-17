import { NextRequest, NextResponse } from "next/server";

import {
  AgentPlatformError,
  getIncidentPatch,
} from "@/lib/agent-platform";

type RouteContext = {
  params: Promise<{
    incidentId: string;
  }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;
  const searchParams = request.nextUrl.searchParams;
  const eventLimit = Number.parseInt(searchParams.get("event_limit") ?? "", 10);
  const refresh = searchParams.get("refresh") === "true";

  try {
    const response = await getIncidentPatch(incidentId, {
      eventLimit: Number.isFinite(eventLimit) && eventLimit > 0 ? eventLimit : undefined,
      refresh,
    });
    return NextResponse.json(response);
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError) {
      return NextResponse.json(
        {
          error: {
            message: caughtError.message,
          },
        },
        { status: caughtError.status },
      );
    }

    return NextResponse.json(
      {
        error: {
          message: "Unexpected incident patch proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
