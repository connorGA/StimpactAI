import { NextRequest, NextResponse } from "next/server";

import { createWorkspaceInvite, listWorkspaceInvites } from "@/lib/agent-platform";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ organizationId: string }> },
) {
  try {
    const { organizationId } = await context.params;
    const invites = await listWorkspaceInvites(organizationId);
    return NextResponse.json(invites);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to load invites.";
    return NextResponse.json({ error: { message } }, { status: 400 });
  }
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ organizationId: string }> },
) {
  try {
    const { organizationId } = await context.params;
    const payload = await request.json();
    const invite = await createWorkspaceInvite(organizationId, payload);
    return NextResponse.json(invite, { status: 201 });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to create invite.";
    return NextResponse.json({ error: { message } }, { status: 400 });
  }
}
