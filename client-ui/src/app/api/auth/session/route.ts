import { NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, sessionCookieOptions } from "@/lib/auth-session";
import { getCurrentSession } from "@/lib/agent-platform";

export async function GET() {
  try {
    const session = await getCurrentSession();
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
  } catch {
    const response = NextResponse.json(
      {
        error: {
          message: "No active session.",
        },
      },
      { status: 401 },
    );
    response.cookies.set(SESSION_COOKIE_NAME, "", {
      ...sessionCookieOptions,
      maxAge: 0,
    });
    return response;
  }
}
