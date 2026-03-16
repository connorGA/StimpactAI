import Link from "next/link";

import {
  PageHeader,
  PreviewNotice,
  SectionCard,
  StatCard,
} from "@/components/dashboard-ui";

const playbooks = [
  {
    title: "Restart unhealthy service pods",
    summary: "Controlled remediation for crash-looping workloads with approval gates.",
  },
  {
    title: "Route traffic away from degraded region",
    summary: "Traffic-management response pattern for regional instability.",
  },
  {
    title: "Generate rollback recommendation",
    summary: "Incident-informed rollback suggestion based on error concentration.",
  },
];

export default function AutomationsPage() {
  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Automations"
        title="Preview the self-healing and playbook control plane"
        description="This page shows the product direction for guided remediation and automation governance, even before those backend capabilities are fully connected."
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
          label="Playbooks visible"
          value={String(playbooks.length)}
          detail="Automation templates shown in the dashboard preview."
        />
        <StatCard
          label="Approval path"
          value="Human-in-loop"
          detail="Operator approvals remain central to high-risk changes."
          tone="yellow"
        />
        <StatCard
          label="Execution state"
          value="Preview"
          detail="Automation execution and outcomes will be wired later."
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <SectionCard
          title="Automation catalog"
          description="Representative automations the production product will eventually support."
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
                  <span className="vault-kicker rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em]">
                    Planned
                  </span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <PreviewNotice
          title="Automation capabilities still unconfigured"
          items={[
            "Actual playbook execution, dry runs, and rollback orchestration are not connected yet.",
            "Guardrails, approval policy engines, and blast-radius simulation remain roadmap UI.",
            "Execution histories and post-action verification loops will be implemented in later phases.",
          ]}
        />
      </div>
    </main>
  );
}
