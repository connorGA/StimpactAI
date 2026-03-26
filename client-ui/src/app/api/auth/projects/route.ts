import { NextRequest, NextResponse } from "next/server";

import { createWorkspaceProject } from "@/lib/agent-platform";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const project = await createWorkspaceProject(payload);
    return NextResponse.json(project, { status: 201 });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Project creation failed.";
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
