import { NextRequest, NextResponse } from "next/server";

import { approveWorkspaceAccessRequest } from "@/lib/agent-platform";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ organizationId: string; accessRequestId: string }> },
) {
  try {
    const { organizationId, accessRequestId } = await context.params;
    const payload = await request.json();
    const response = await approveWorkspaceAccessRequest(
      organizationId,
      accessRequestId,
      payload,
    );
    return NextResponse.json(response);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to approve access request.";
    return NextResponse.json({ error: { message } }, { status: 400 });
  }
}
