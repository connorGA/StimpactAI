import { NextResponse } from "next/server";

import { CURRENT_PROJECT_COOKIE } from "@/lib/project-context";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { project_id?: string | null } | null;
  const projectId = typeof body?.project_id === "string" ? body.project_id.trim() : "";
  const response = NextResponse.json({ ok: true, project_id: projectId || null });
  if (projectId) {
    response.cookies.set(CURRENT_PROJECT_COOKIE, projectId, {
      httpOnly: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 365,
    });
  } else {
    response.cookies.delete(CURRENT_PROJECT_COOKIE);
  }
  return response;
}
