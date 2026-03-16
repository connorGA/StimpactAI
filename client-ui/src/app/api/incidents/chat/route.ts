import { NextRequest, NextResponse } from "next/server";

import {
  AgentPlatformError,
  createGlobalIncidentChat,
} from "@/lib/agent-platform";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as unknown;
    const response = await createGlobalIncidentChat(body);
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
          message: "Unexpected incident chat proxy error.",
        },
      },
      { status: 500 },
    );
  }
}
