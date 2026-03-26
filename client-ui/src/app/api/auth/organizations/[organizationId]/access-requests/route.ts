import { NextRequest, NextResponse } from "next/server";

import { listWorkspaceAccessRequests } from "@/lib/agent-platform";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ organizationId: string }> },
) {
  try {
    const { organizationId } = await context.params;
    const requests = await listWorkspaceAccessRequests(organizationId);
    return NextResponse.json(requests);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to load access requests.";
    return NextResponse.json({ error: { message } }, { status: 400 });
  }
}
