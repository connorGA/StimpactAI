import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, sessionCookieOptions } from "@/lib/auth-session";
import { acceptWorkspaceInvite } from "@/lib/agent-platform";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const session = await acceptWorkspaceInvite(payload);
    const response = NextResponse.json({
      user: session.user,
      organization: session.organization,
      role: session.role,
      memberships: session.memberships,
      projects: session.projects,
      subscription: session.subscription,
    });
    response.cookies.set(SESSION_COOKIE_NAME, session.access_token, sessionCookieOptions);
    return response;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Invite acceptance failed.";
    return NextResponse.json(
      {
        error: {
          message,
        },
      },
      { status: 400 },
    );
  }
}
