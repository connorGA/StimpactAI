import { ChatPanel } from "@/components/chat-panel";
import { ProjectSetupState } from "@/components/dashboard-ui";
import { getIncidents } from "@/lib/agent-platform";
import { countOpenIncidents } from "@/lib/dashboard";
import { resolvePrimaryProjectId } from "@/lib/project-context";

export const dynamic = "force-dynamic";

export default async function ChatPage() {
  const projectId = await resolvePrimaryProjectId();
  if (!projectId) {
    return (
      <ProjectSetupState
        eyebrow="Agent workspace"
        title="Create a project before opening the incident agent"
        description="The agent chat is grounded in the current project’s incident set. Finish onboarding first so the assistant has real incident context to work with."
      />
    );
  }
  const incidentList = await getIncidents({ projectId: projectId ?? undefined, limit: 20, offset: 0 });
  const incidents = incidentList.items;

  return (
    <main className="space-y-8">
      <section className="px-1">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Agent workspace
            </p>
            <h1 className="ops-title mt-3 max-w-4xl text-4xl font-semibold tracking-tight lg:text-[3.1rem]">
              Message a context-aware incident agent with the current working set
            </h1>
            <p className="ops-copy mt-4 max-w-3xl text-sm leading-7">
              The agent page should feel closer to a focused messaging workspace:
              left-hand incident inbox, central conversation, and a narrow context rail.
            </p>
          </div>

          <div className="ops-sheet-muted rounded-[22px] px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8f735c]">
              Context window
            </p>
            <p className="mt-3 text-3xl font-semibold text-[#111827]">
              {incidents.length}
            </p>
            <p className="mt-2 text-sm text-[#667085]">incidents in working set</p>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <section className="ops-sheet rounded-[28px] p-6">
          <p className="ops-kicker text-[11px] font-semibold uppercase">
            Inbox history
          </p>
          <div className="mt-5 border-t border-[rgba(24,24,27,0.08)]">
            {incidents.slice(0, 6).map((incident, index) => (
              <div
                key={incident.id}
                className={`border-b py-4 last:border-b-0 ${
                  index === 0
                    ? "border-[rgba(24,24,27,0.08)] bg-white/22"
                    : "border-[rgba(24,24,27,0.08)]"
                }`}
              >
                <p className="font-medium text-[#111827]">{incident.title}</p>
                <p className="mt-1 text-sm text-[#667085]">
                  {incident.service} • {incident.environment}
                </p>
              </div>
            ))}
          </div>
        </section>

        <ChatPanel
          title="Global incident agent"
          description="Use the agent to summarize the visible incident set, prioritize work, and answer grounded questions from the current operational context."
          endpoint="/api/incidents/chat"
          extraBody={{
            incident_limit: 20,
          }}
          suggestedPrompts={[
            "Summarize the most urgent incidents right now.",
            "What should the next operator focus on first?",
            "Which services appear most impacted in the current incident set?",
          ]}
        />

        <div className="space-y-6">
          <section className="ops-sheet-muted rounded-[28px] p-6">
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Chat focus
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {["triage", "services", "root cause", "status update", "next actions"].map(
                (focus, index) => (
                  <button
                    key={focus}
                    type="button"
                    className={`rounded-full px-3 py-2 text-sm font-medium ${
                      index === 0
                        ? "ops-button text-white"
                        : "ops-button-secondary"
                    }`}
                  >
                    {focus}
                  </button>
                ),
              )}
            </div>
          </section>

          <section className="ops-sheet rounded-[28px] p-6">
            <p className="ops-kicker text-[11px] font-semibold uppercase">
              Passed context
            </p>
            <div className="mt-5 border-t border-[rgba(24,24,27,0.08)]">
              <ContextRow label="Open incidents" value={String(countOpenIncidents(incidents))} />
              <ContextRow label="Visible incidents" value={String(incidents.length)} />
              <ContextRow label="Memory mode" value="Session only" />
              <ContextRow label="Draft status updates" value="Operator draft" />
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-[rgba(24,24,27,0.08)] py-4 last:border-b-0">
      <span className="text-sm text-[#667085]">{label}</span>
      <span className="text-sm font-semibold text-[#111827]">{value}</span>
    </div>
  );
}
