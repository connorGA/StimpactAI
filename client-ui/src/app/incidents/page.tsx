import { IncidentCommandCenter } from "@/components/incident-command-center";
import { ProjectSetupState } from "@/components/dashboard-ui";
import {
  getIncidents,
  getIncidentReportingOverview,
  getLatestIncidentAutonomousRunDetail,
  getProjectOnboarding,
  listProjectRepairTargets,
  getSuppressionSummary,
} from "@/lib/agent-platform";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import type {
  IncidentAutonomousRunDetail,
  IncidentSummary,
  ProjectServiceRepairTarget,
  SuppressionSummary,
} from "@/lib/types";

export const dynamic = "force-dynamic";

type IncidentsPageProps = {
  searchParams: Promise<{
    project_id?: string;
  }>;
};

export default async function IncidentsPage({ searchParams }: IncidentsPageProps) {
  const params = await searchParams;
  const projectId = params.project_id?.trim() || (await resolvePrimaryProjectId()) || undefined;
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Incident center"
        title="Create a project before browsing incident history"
        description="Incident history is scoped to a project. Complete onboarding first, then this route will load the ledger, filters, and response status for that project."
      />
    );
  }
  const [onboarding, incidentList, reporting, suppression] = await Promise.all([
    getProjectOnboarding(projectId).catch(() => null),
    getIncidents({ projectId, limit: 50, offset: 0 }),
    getIncidentReportingOverview(projectId),
    getSuppressionSummary(projectId, { windowMinutes: 60 * 24 }).catch<SuppressionSummary | null>(
      () => null,
    ),
  ]);

  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Incident center"
        title="Finish onboarding before browsing incident history"
        description="Incident history stays in onboarding-first mode until the current project has completed repository connection, secrets setup, and service mapping."
      />
    );
  }

  const incidents = incidentList.items;
  const [autonomousRuns, repairTargets] = await Promise.all([
    loadLatestAutonomousRuns(incidents),
    listProjectRepairTargets(projectId).catch<ProjectServiceRepairTarget[]>(() => []),
  ]);

  return (
    <IncidentCommandCenter
      projectId={projectId}
      incidents={incidents}
      reporting={reporting}
      autonomousRuns={autonomousRuns}
      suppression={suppression}
      repairTargets={repairTargets}
    />
  );
}

const MAX_AUTONOMOUS_DETAIL_FETCHES = 8;

async function loadLatestAutonomousRuns(
  incidents: IncidentSummary[],
): Promise<Record<string, IncidentAutonomousRunDetail | null>> {
  const open = incidents.filter((incident) => incident.status === "open");
  const rest = incidents.filter((incident) => incident.status !== "open");
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
