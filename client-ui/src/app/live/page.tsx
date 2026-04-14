import { LiveDashboard } from "@/components/live-workspace-page";
import { ProjectSetupState } from "@/components/dashboard-ui";
import {
  getProjectOnboarding,
  getIncidentReportingOverview,
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
} from "@/lib/agent-platform";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import type { IncidentAutonomousRunDetail, IncidentSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function LivePage() {
  const projectId = await resolvePrimaryProjectId();
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Live workspace"
        title="Create your first project before opening live operations"
        description="The live workspace reads from project-scoped incident data. Finish onboarding first."
      />
    );
  }

  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Live workspace"
        title="Finish onboarding before opening live operations"
        description="Complete provider connection, repositories, secrets, and service mapping first."
      />
    );
  }

  const [incidentList, reporting] = await Promise.all([
    getIncidents({ projectId, limit: 50, offset: 0 }),
    getIncidentReportingOverview(projectId),
  ]);

  const incidents = incidentList.items;
  const autonomousRuns = await loadLatestAutonomousRuns(incidents.slice(0, 12));

  const heartbeats = onboarding.telemetry_heartbeats;
  const services = onboarding.project_services;
  const defaultService =
    heartbeats[0]?.service ?? services[0]?.name ?? "";

  return (
    <LiveDashboard
      projectId={projectId}
      incidents={incidents}
      reporting={reporting}
      autonomousRuns={autonomousRuns}
      sdkDefaultService={defaultService}
    />
  );
}

async function loadLatestAutonomousRuns(
  incidents: IncidentSummary[],
): Promise<Record<string, IncidentAutonomousRunDetail | null>> {
  const pairs = await Promise.all(
    incidents.map(async (incident) => {
      try {
        const detail = await getLatestIncidentAutonomousRunDetail(incident.id);
        return [incident.id, detail] as const;
      } catch {
        return [incident.id, null] as const;
      }
    }),
  );
  return Object.fromEntries(pairs);
}
