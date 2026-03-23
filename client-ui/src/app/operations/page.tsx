import Link from "next/link";

import { PageHeader, SectionCard, StatCard } from "@/components/dashboard-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { getHealthReadiness, getIncidents, getLatestIncidentAutonomousRunDetail } from "@/lib/agent-platform";
import { countOpenIncidents, formatTimestamp } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export default async function OperationsPage() {
  const incidentList = await getIncidents({ limit: 10, offset: 0 });
  const readiness = await getHealthReadiness().catch(() => null);
  const autonomousPairs = await Promise.all(
    incidentList.items.slice(0, 6).map(async (incident) => {
      try {
        const detail = await getLatestIncidentAutonomousRunDetail(incident.id);
        return [incident.id, detail.run] as const;
      } catch {
        return [incident.id, null] as const;
      }
    }),
  );
  const autonomousLookup = Object.fromEntries(autonomousPairs);
  const activeRepairs = Object.values(autonomousLookup).filter(
    (run) => run && (run.status === "queued" || run.status === "running"),
  ).length;
  const handoffItems = buildHandoffItems(incidentList.items);

  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Run the active response workflow from one place"
        description="This page reserves the final product space for the live operational layers around incidents: handoff coordination, communications, approvals, and escalation management."
      />

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="Active queue"
          value={String(countOpenIncidents(incidentList.items))}
          detail="Open incidents currently in response."
        />
        <StatCard
          label="Active repairs"
          value={String(activeRepairs)}
          detail="Autonomous or queued remediation attempts currently in flight."
          tone="yellow"
        />
        <StatCard
          label="Backend readiness"
          value={readiness?.status ?? "unknown"}
          detail="Operational view of the platform health check."
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <SectionCard
          title="Active response board"
          description="Incident response now includes live autonomous-repair status when available."
        >
          <div className="space-y-3">
            {incidentList.items.slice(0, 6).map((incident) => (
              <div
                key={incident.id}
                className="rounded-[24px] border border-[rgba(111,158,210,0.14)] bg-white px-4 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <Link
                      href={`/incidents/${incident.id}`}
                      className="font-semibold text-[#17385d] hover:underline"
                    >
                      {incident.title}
                    </Link>
                    <p className="mt-1 text-sm text-[#67819f]">
                      {incident.service} • last seen {formatTimestamp(incident.last_seen_at)}
                    </p>
                    <p className="mt-2 text-sm text-[#35547d]">
                      {describeAutonomousStatus(autonomousLookup[incident.id]?.status)}
                    </p>
                  </div>
                  <SeverityBadge severity={incident.severity} />
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <div className="space-y-6">
          <SectionCard
            title="Operator handoff"
            description="Suggested next actions based on the current incident queue."
          >
            <div className="space-y-3">
              {handoffItems.map((item) => (
                <div
                  key={item}
                  className="rounded-2xl bg-[#f8fbff] px-4 py-3 text-sm text-[#35547d]"
                >
                  {item}
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      </div>
    </main>
  );
}

function describeAutonomousStatus(status: string | undefined): string {
  if (status === "running" || status === "queued") {
    return "Autonomous repair is actively working this incident.";
  }
  if (status === "failed") {
    return "Latest autonomous repair attempt failed and needs operator follow-up.";
  }
  if (status === "succeeded") {
    return "Latest autonomous repair attempt completed successfully.";
  }
  return "No autonomous repair has been queued for this incident yet.";
}

function buildHandoffItems(incidents: Awaited<ReturnType<typeof getIncidents>>["items"]): string[] {
  const topIncident = incidents[0];
  if (!topIncident) {
    return [
      "No open incident handoff required right now.",
      "Backend health is stable enough for routine monitoring.",
      "Keep provider integrations and repo profiles current for the next incident.",
    ];
  }
  return [
    `Review ${topIncident.service} incident ownership and confirm the current responder.`,
    `Share the latest event count (${topIncident.event_count}) and environment (${topIncident.environment}) with stakeholders.`,
    `Open the incident detail view to approve or reject the next remediation step.`,
  ];
}
