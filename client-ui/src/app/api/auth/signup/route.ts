import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, sessionCookieOptions } from "@/lib/auth-session";
import { signupWorkspace } from "@/lib/agent-platform";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const session = await signupWorkspace(payload);
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
      error instanceof Error ? error.message : "Signup failed.";
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
