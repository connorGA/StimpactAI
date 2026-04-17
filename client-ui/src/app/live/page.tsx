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

  const [onboarding, incidentList, reporting] = await Promise.all([
    getProjectOnboarding(projectId).catch(() => null),
    getIncidents({ projectId, limit: 50, offset: 0 }),
    getIncidentReportingOverview(projectId),
  ]);

  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Live workspace"
        title="Finish onboarding before opening live operations"
        description="Complete provider connection, repositories, secrets, and service mapping first."
      />
    );
  }

  const incidents = incidentList.items;
  const autonomousRuns = await loadLatestAutonomousRuns(incidents);

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

/** Open incidents first (badges + repair state), then recent others. Caps fan-out so the page is not N parallel API calls to the agent platform (was up to 12 every navigation). */
const MAX_AUTONOMOUS_DETAIL_FETCHES = 8;

async function loadLatestAutonomousRuns(
  incidents: IncidentSummary[],
): Promise<Record<string, IncidentAutonomousRunDetail | null>> {
  const open = incidents.filter((i) => i.status === "open");
  const rest = incidents.filter((i) => i.status !== "open");
  const prioritized = [...open, ...rest].slice(0, MAX_AUTONOMOUS_DETAIL_FETCHES);

  const pairs = await Promise.all(
    prioritized.map(async (incident) => {
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
