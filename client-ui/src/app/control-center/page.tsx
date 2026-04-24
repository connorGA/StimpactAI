import Link from "next/link";

import { ControlCenterPolicyForm } from "@/components/control-center-policy-form";
import { DashboardMetricCard } from "@/components/dashboard-metric-cards";
import {
  getCurrentSession,
  getHealthReadiness,
  getProjectPolicy,
  getProjectOnboarding,
  listProjectRepairTargets,
  listProjectApiKeys,
  listProjectServices,
  listRepoProfiles,
} from "@/lib/agent-platform";
import { ServiceRepairTargetPanel } from "@/components/service-repair-target-panel";
import { isProjectOnboardingComplete } from "@/lib/onboarding";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import { ProjectSetupState } from "@/components/dashboard-ui";

export const dynamic = "force-dynamic";

export default async function ControlCenterPage() {
  const session = await getCurrentSession().catch(() => null);
  const projectId = await resolvePrimaryProjectId();

  if (!session) {
    return (
      <main className="mx-auto max-w-[1120px] space-y-4 px-2 pb-12 pt-2">
        <h1 className="text-2xl font-bold text-white">Control center</h1>
        <p className="max-w-lg text-sm text-white/65">
          Sign in to configure project automation policy and repair branches.
        </p>
        <Link
          href="/login"
          className="inline-flex rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white/85 transition hover:bg-white/[0.08]"
        >
          Sign in
        </Link>
      </main>
    );
  }

  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Control center"
        title="Create your first project before opening the control center"
        description="The control center is scoped to a project. Complete onboarding to connect a repository and map services, then tune autonomy and guardrails here."
      />
    );
  }

  const onboarding = await getProjectOnboarding(projectId).catch(() => null);
  if (!onboarding || !isProjectOnboardingComplete(onboarding)) {
    return (
      <ProjectSetupState
        eyebrow="Control center"
        title="Finish onboarding before opening the control center"
        description="Finish provider connection, secrets, and service mapping first. Then you can edit policy, branches, and agent behavior for this project."
      />
    );
  }

  const [policy, repoProfiles, projectServices, apiKeys, repairTargets, readiness] = await Promise.all([
    getProjectPolicy(projectId),
    listRepoProfiles(projectId),
    listProjectServices(projectId),
    listProjectApiKeys(projectId),
    listProjectRepairTargets(projectId).catch(() => []),
    getHealthReadiness().catch(() => null),
  ]);

  const activeKeys = apiKeys.filter((key) => key.status === "active").length;
  const dbOk = readiness?.checks.database.ready ?? false;

  return (
    <main className="mx-auto max-w-[1120px] space-y-5 px-2 pb-12 pt-2">
      <header>
        <h1 className="text-2xl font-bold text-white">Control center</h1>
        <p className="mt-1 text-sm text-white/50">
          End-to-end automation policy and repair targets for the active project.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-5">
        <DashboardMetricCard
          label="Autonomy mode"
          hint="Saved project policy"
          value={formatMode(policy.autonomy_mode)}
        />
        <DashboardMetricCard
          label="Mapped services"
          hint="Services linked to repo profiles"
          value={String(projectServices.length)}
        />
        <DashboardMetricCard
          label="Repo profiles"
          hint="Sandbox / repair profiles"
          value={String(repoProfiles.length)}
        />
        <DashboardMetricCard
          label="Active API keys"
          hint="SDK ingest keys"
          value={String(activeKeys)}
          valueClassName={activeKeys > 0 ? "text-white" : "text-white/45"}
        />
        <DashboardMetricCard
          label="Platform DB"
          hint="Agent platform database"
          value={dbOk ? "Healthy" : "Check"}
          valueClassName={dbOk ? "text-[#4ade80]" : "text-[#ffb253]"}
        />
      </div>

      <ControlCenterPolicyForm projectId={projectId} initialPolicy={policy} />

      <section className="space-y-3">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Repair branches
          </h2>
          <p className="mt-1 text-sm text-white/55">
            Branch when telemetry has no commit SHA. Updates the tracked branch on each service.
          </p>
        </div>
        <ServiceRepairTargetPanel
          projectId={projectId}
          services={projectServices}
          initialTargets={repairTargets}
        />
      </section>
    </main>
  );
}

function formatMode(mode: string): string {
  return mode
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
