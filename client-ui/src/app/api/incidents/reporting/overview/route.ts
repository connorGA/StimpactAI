import { NextResponse } from "next/server";

import { AgentPlatformError, getIncidentReportingOverview } from "@/lib/agent-platform";
import { resolvePrimaryProjectId } from "@/lib/project-context";

/** Lightweight reporting snapshot for client UI (e.g. sidebar open-incident badge). */
export async function GET() {
  try {
    const projectId = await resolvePrimaryProjectId();
    if (!projectId) {
      return NextResponse.json({ open_incidents: 0 });
    }
    const reporting = await getIncidentReportingOverview(projectId);
    return NextResponse.json({
      open_incidents: reporting.open_incidents,
      project_id: projectId,
    });
  } catch (caughtError) {
    if (caughtError instanceof AgentPlatformError) {
      return NextResponse.json(
        { error: { message: caughtError.message }, open_incidents: 0 },
        { status: caughtError.status },
      );
    }
    return NextResponse.json(
      { error: { message: "Unable to load reporting overview." }, open_incidents: 0 },
      { status: 500 },
    );
  }
}
