import {
  PageHeader,
  PreviewNotice,
  SectionCard,
  StatCard,
} from "@/components/dashboard-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { getIncidents } from "@/lib/agent-platform";
import { countOpenIncidents, formatTimestamp } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

const handoffItems = [
  "Primary on-call handoff notes",
  "Stakeholder update timeline",
  "Incident commander checklist",
];

export default async function OperationsPage() {
  const incidentList = await getIncidents({ limit: 10, offset: 0 });

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
          label="Escalation path"
          value="3 layers"
          detail="Ops, engineering, and leadership response lanes."
          tone="yellow"
        />
        <StatCard
          label="Response modules"
          value="Preview"
          detail="Core operational workflows are rendered ahead of backend support."
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <SectionCard
          title="Active response board"
          description="A forward-looking live board using the current incident set as seed data."
        >
          <div className="space-y-3">
            {incidentList.items.slice(0, 6).map((incident) => (
              <div
                key={incident.id}
                className="rounded-[24px] border border-[rgba(111,158,210,0.14)] bg-white px-4 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-[#17385d]">{incident.title}</p>
                    <p className="mt-1 text-sm text-[#67819f]">
                      {incident.service} • last seen {formatTimestamp(incident.last_seen_at)}
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
            description="Planned response-management modules."
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

          <PreviewNotice
            title="Operations features not yet configured"
            items={[
              "Shift handoffs, war-room communications, and approval workflows are still UI-only.",
              "Real escalation routing, paging acknowledgements, and stakeholder comms will be connected later.",
              "Runbook checkpoints and incident command timelines are visual placeholders for now.",
            ]}
          />
        </div>
      </div>
    </main>
  );
}
