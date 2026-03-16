import { NextRequest, NextResponse } from "next/server";

import {
  AgentPlatformError,
  createIncidentDetailChat,
} from "@/lib/agent-platform";

type RouteContext = {
  params: Promise<{
    incidentId: string;
  }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  const { incidentId } = await context.params;

  try {
    const body = (await request.json()) as unknown;
    const response = await createIncidentDetailChat(incidentId, body);
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
          message: "Unexpected incident detail chat proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
