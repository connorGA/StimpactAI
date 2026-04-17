import { NextRequest, NextResponse } from "next/server";

import { AgentPlatformError, getSuppressionSummary } from "@/lib/agent-platform";

export async function GET(request: NextRequest) {
  const projectId = request.nextUrl.searchParams.get("project_id");
  const windowMinutesRaw = request.nextUrl.searchParams.get("window_minutes");
  if (!projectId) {
    return NextResponse.json(
      { error: { message: "project_id query parameter is required." } },
      { status: 400 },
    );
  }
  const windowMinutes = windowMinutesRaw
    ? Math.max(1, Math.min(60 * 24 * 30, Number(windowMinutesRaw)))
    : undefined;

  try {
    const data = await getSuppressionSummary(projectId, { windowMinutes });
    return NextResponse.json(data);
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError) {
      return NextResponse.json(
        { error: { message: caughtError.message } },
        { status: caughtError.status },
      );
    }
    return NextResponse.json(
      { error: { message: "Unable to load suppression summary." } },
      { status: 500 },
    );
  }
}
