import { NextResponse } from "next/server";

import {
  AgentPlatformError,
  getLatestIncidentAutonomousRunDetail,
} from "@/lib/agent-platform";

type RouteContext = {
  params: Promise<{
    incidentId: string;
  }>;
};

export async function GET(_: Request, context: RouteContext) {
  const { incidentId } = await context.params;

  try {
    const response = await getLatestIncidentAutonomousRunDetail(incidentId);
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
          message: "Unexpected autonomous run proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
