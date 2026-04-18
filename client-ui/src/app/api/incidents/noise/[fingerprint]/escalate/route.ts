import { NextRequest, NextResponse } from "next/server";

import { AgentPlatformError, escalateNoiseFingerprint } from "@/lib/agent-platform";

type RouteContext = { params: Promise<{ fingerprint: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  const { fingerprint } = await context.params;
  let body: {
    project_id?: string;
    reason?: string | null;
  };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json(
      { error: { message: "Invalid JSON body." } },
      { status: 400 },
    );
  }

  const projectId = (body.project_id ?? "").trim();
  if (!projectId) {
    return NextResponse.json(
      { error: { message: "project_id is required." } },
      { status: 400 },
    );
  }

  try {
    const data = await escalateNoiseFingerprint({
      projectId,
      fingerprint,
      reason: body.reason ?? undefined,
    });
    return NextResponse.json(data);
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError) {
      return NextResponse.json(
        { error: { message: caughtError.message } },
        { status: caughtError.status },
      );
    }
    return NextResponse.json(
      { error: { message: "Unable to escalate fingerprint." } },
      { status: 500 },
    );
  }
}
