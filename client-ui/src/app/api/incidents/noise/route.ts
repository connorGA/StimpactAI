import { NextRequest, NextResponse } from "next/server";

import { AgentPlatformError, listSuppressedTelemetry } from "@/lib/agent-platform";

export async function GET(request: NextRequest) {
  const projectId = request.nextUrl.searchParams.get("project_id");
  const limitRaw = request.nextUrl.searchParams.get("limit");
  if (!projectId) {
    return NextResponse.json(
      { error: { message: "project_id query parameter is required." } },
      { status: 400 },
    );
  }
  const limit = limitRaw ? Math.max(1, Math.min(200, Number(limitRaw))) : undefined;

  try {
    const data = await listSuppressedTelemetry(projectId, { limit });
    return NextResponse.json(data);
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError) {
      return NextResponse.json(
        { error: { message: caughtError.message }, items: [] },
        { status: caughtError.status },
      );
    }
    return NextResponse.json(
      { error: { message: "Unable to load suppressed telemetry." }, items: [] },
      { status: 500 },
    );
  }
}
