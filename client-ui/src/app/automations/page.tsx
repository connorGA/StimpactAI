import Link from "next/link";

import {
  getIncidents,
  getLatestIncidentAutonomousRunDetail,
  getProjectPolicy,
  listProviderIntegrations,
  listRepoProfiles,
} from "@/lib/agent-platform";
import { resolvePrimaryProjectId } from "@/lib/project-context";
import {
  PageHeader,
  SectionCard,
  StatCard,
} from "@/components/dashboard-ui";
export const dynamic = "force-dynamic";

export default async function AutomationsPage() {
  const projectId = await resolvePrimaryProjectId();
  const incidents = await getIncidents({ limit: 6, offset: 0 });
  const [policy, repoProfiles, integrations] = projectId
    ? await Promise.all([
        getProjectPolicy(projectId),
        listRepoProfiles(projectId),
        listProviderIntegrations(projectId),
      ])
    : [null, [], []];
  const latestRuns = await Promise.all(
    incidents.items.slice(0, 4).map(async (incident) => {
      try {
        const detail = await getLatestIncidentAutonomousRunDetail(incident.id);
        return { incident, run: detail.run };
      } catch {
        return { incident, run: null };
      }
    }),
  );
  const playbooks = [
    {
      title: "Autonomous repair",
      summary: "Queues a full repair workflow for an incident using the configured repo profile.",
      status:
        policy && repoProfiles.length > 0 && policy.patch_planner_enabled
          ? "available"
          : "needs setup",
    },
    {
      title: "Sandbox verification",
      summary: "Reproduces the incident and verifies a generated patch inside an isolated runtime.",
      status: repoProfiles.length > 0 ? "available" : "needs setup",
    },
    {
      title: "Provider repository sync",
      summary: "Refreshes the connected repository catalog before a remediation or promotion flow starts.",
      status: integrations.length > 0 ? "available" : "needs setup",
    },
  ] as const;

  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Automations"
        title="Automation catalog and recent remediation activity"
        description="The automation surface now reflects live project policy, repo connectivity, and recent autonomous run activity."
        action={
          <Link
            href="/chat"
            className="vault-button-secondary inline-flex rounded-2xl border border-[rgba(111,158,210,0.2)] px-4 py-2.5 text-sm font-semibold text-[#35547d] transition"
          >
            Open copilot
          </Link>
        }
      />

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="Catalog entries"
          value={String(playbooks.length)}
          detail="Operational automations currently surfaced by the control plane."
        />
        <StatCard
          label="Approval path"
          value={policy?.require_human_approval ? "Human-in-loop" : "Automatic"}
          detail="Current approval mode taken from the persisted project policy."
          tone="yellow"
        />
        <StatCard
          label="Connected repos"
          value={String(repoProfiles.length)}
          detail="Repo profiles available for sandbox and repair execution."
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <SectionCard
          title="Automation catalog"
          description="Live automation availability based on policy and repo connectivity."
        >
          <div className="space-y-4">
            {playbooks.map((playbook) => (
              <div
                key={playbook.title}
                className="rounded-[24px] border border-[rgba(111,158,210,0.14)] bg-white px-5 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-[#17385d]">{playbook.title}</p>
                    <p className="mt-2 text-sm leading-6 text-[#67819f]">
                      {playbook.summary}
                    </p>
                  </div>
                  <span
                    className={`vault-kicker rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${
                      playbook.status === "available"
                        ? "bg-[rgba(67,160,71,0.12)] text-[#2f6f35]"
                        : "bg-[rgba(255,178,83,0.18)] text-[#8f5b09]"
                    }`}
                  >
                    {playbook.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Recent execution history"
          description="Latest autonomous remediation activity for the active incident sample."
        >
          <div className="space-y-3">
            {latestRuns.map(({ incident, run }) => (
              <div
                key={incident.id}
                className="rounded-[22px] border border-[rgba(17,24,39,0.08)] bg-white px-4 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-[#171717]">{incident.title}</p>
                    <p className="mt-1 text-sm text-[#746d66]">
                      {run
                        ? `Latest autonomous run is ${run.status} in phase ${run.phase}.`
                        : "No autonomous execution has been queued for this incident yet."}
                    </p>
                  </div>
                  <Link
                    href={`/incidents/${incident.id}`}
                    className="text-sm font-semibold text-[#35547d] hover:underline"
                  >
                    Open incident
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </main>
  );
}
