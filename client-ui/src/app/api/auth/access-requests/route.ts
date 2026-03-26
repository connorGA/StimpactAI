import { NextRequest, NextResponse } from "next/server";

import { createAccessRequest } from "@/lib/agent-platform";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const accessRequest = await createAccessRequest(payload);
    return NextResponse.json(accessRequest, { status: 201 });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Access request failed.";
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
