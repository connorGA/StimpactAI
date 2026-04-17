import { NextRequest, NextResponse } from "next/server";

import { AgentPlatformError, reclassifyFingerprint } from "@/lib/agent-platform";
import type { TelemetryClassification } from "@/lib/types";

type RouteContext = { params: Promise<{ fingerprint: string }> };

const ALLOWED: readonly TelemetryClassification[] = [
  "code_bug",
  "user_error",
  "code_ambiguous",
];

export async function POST(request: NextRequest, context: RouteContext) {
  const { fingerprint } = await context.params;
  let body: {
    project_id?: string;
    classification?: string;
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
  const classificationRaw = (body.classification ?? "").trim();
  if (!projectId) {
    return NextResponse.json(
      { error: { message: "project_id is required." } },
      { status: 400 },
    );
  }
  if (!ALLOWED.includes(classificationRaw as TelemetryClassification)) {
    return NextResponse.json(
      {
        error: {
          message: `classification must be one of ${ALLOWED.join(", ")}.`,
        },
      },
      { status: 400 },
    );
  }

  try {
    const data = await reclassifyFingerprint({
      projectId,
      fingerprint,
      classification: classificationRaw as TelemetryClassification,
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
      { error: { message: "Unable to reclassify fingerprint." } },
      { status: 500 },
    );
  }
}
